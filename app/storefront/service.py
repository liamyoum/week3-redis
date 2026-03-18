from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.domain.contracts import StoreProtocol
from app.domain.schemas import (
    ProductCardResponse,
    ProductDetailResponse,
    ProductListResponse,
    PurchaseResponse,
    ReserveResponse,
    StoreStateResponse,
)
from app.persistence.aof import AofRepository
from app.storefront.catalog import ProductCatalogProtocol, ProductRecord

INVENTORY_NAMESPACE = "storefront-inventory"
DETAIL_KEY = "detail"


class ProductNotFoundError(LookupError):
    """Raised when a requested storefront product is missing."""


class StorefrontService:
    def __init__(
        self,
        store: StoreProtocol,
        catalog: ProductCatalogProtocol,
        snapshot_status_provider: Callable[[], dict[str, Any]],
        origin_delay_ms: int = 120,
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._snapshot_status_provider = snapshot_status_provider
        self._origin_delay_ms = origin_delay_ms

    def list_products(self) -> ProductListResponse:
        products = [self._to_product_card(product) for product in self._catalog.list_products()]
        return ProductListResponse(origin_source=self._catalog.source_name, products=products)

    def get_direct_product(self, product_id: str) -> ProductDetailResponse:
        started = time.perf_counter()
        product = self._load_from_origin(product_id)
        latency_ms = (time.perf_counter() - started) * 1000
        return ProductDetailResponse(
            product=self._to_product_card(product),
            source="direct",
            origin_source=self._catalog.source_name,
            cache_status="bypass",
            latency_ms=latency_ms,
        )

    def get_cached_product(self, product_id: str) -> ProductDetailResponse:
        namespace = self._detail_namespace(product_id)
        started = time.perf_counter()
        cached_record = self._store.get(DETAIL_KEY, namespace=namespace)
        if cached_record is not None:
            try:
                payload = json.loads(cached_record.value_str)
                product = self._product_from_cache_payload(product_id, payload)
            except (ValueError, TypeError, json.JSONDecodeError):
                self._store.delete(DETAIL_KEY, namespace=namespace)
            else:
                latency_ms = (time.perf_counter() - started) * 1000
                return ProductDetailResponse(
                    product=self._to_product_card(product),
                    source="cache",
                    origin_source=self._catalog.source_name,
                    cache_status="hit",
                    latency_ms=latency_ms,
                )

        product = self._load_from_origin(product_id)
        self._store.set(
            key=DETAIL_KEY,
            value_str=json.dumps(product.to_cache_payload(), separators=(",", ":")),
            namespace=namespace,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        return ProductDetailResponse(
            product=self._to_product_card(product),
            source="cache",
            origin_source=self._catalog.source_name,
            cache_status="miss",
            latency_ms=latency_ms,
        )

    def reserve_product(self, product_id: str, session_id: str, ttl_ms: int) -> ReserveResponse:
        namespace = self._detail_namespace(product_id)
        cache_record = self._store.get(DETAIL_KEY, namespace=namespace)
        if cache_record is None:
            product = self._load_from_origin(product_id)
            payload = json.dumps(product.to_cache_payload(), separators=(",", ":"))
        else:
            payload = cache_record.value_str
        hold_key = f"{namespace}:{DETAIL_KEY}"
        record = self._store.set(
            key=DETAIL_KEY,
            value_str=payload,
            ttl_ms=ttl_ms,
            namespace=namespace,
        )
        return ReserveResponse(
            product_id=product_id,
            session_id=session_id,
            hold_key=hold_key,
            ttl_ms=ttl_ms,
            expires_at_ms=record.expires_at_ms or 0,
        )

    def purchase_product(self, product_id: str, quantity: int) -> PurchaseResponse:
        product = self._require_product(product_id)
        current_stock = self._ensure_inventory(product)
        if quantity > current_stock:
            raise ValueError("Not enough stock remaining for this drop.")
        remaining_stock = self._store.decr(
            key=self._inventory_key(product_id),
            amount=quantity,
            namespace=INVENTORY_NAMESPACE,
        )
        return PurchaseResponse(
            product_id=product_id,
            quantity=quantity,
            stock=remaining_stock,
        )

    def restock_product(self, product_id: str, quantity: int) -> PurchaseResponse:
        product = self._require_product(product_id)
        self._ensure_inventory(product)
        next_stock = self._store.incr(
            key=self._inventory_key(product_id),
            amount=quantity,
            namespace=INVENTORY_NAMESPACE,
        )
        return PurchaseResponse(
            product_id=product_id,
            quantity=quantity,
            stock=next_stock,
        )

    def invalidate_product(self, product_id: str) -> int:
        self._require_product(product_id)
        return self._store.invalidate_namespace(self._detail_namespace(product_id))

    def detail_namespace(self, product_id: str) -> str:
        return self._detail_namespace(product_id)

    def get_state(self) -> StoreStateResponse:
        status = self._snapshot_status_provider()
        snapshot_path = status.get("path")
        aof_path = status.get("aof_path")
        snapshot_exists, snapshot_size = self._file_state(snapshot_path)
        aof_exists, aof_size = self._file_state(aof_path)
        return StoreStateResponse(
            origin_source=self._catalog.source_name,
            origin_delay_ms=self._origin_delay_ms,
            product_count=len(self._catalog.list_products()),
            snapshot_path=snapshot_path if isinstance(snapshot_path, str) else None,
            snapshot_exists=snapshot_exists,
            snapshot_size_bytes=snapshot_size,
            aof_path=aof_path if isinstance(aof_path, str) else None,
            aof_exists=aof_exists,
            aof_size_bytes=aof_size,
            snapshot_payload=self._read_snapshot_payload(snapshot_path),
            aof_events=self._read_aof_events(aof_path),
        )

    def _load_from_origin(self, product_id: str) -> ProductRecord:
        self._sleep_for_origin()
        return self._require_product(product_id)

    def _require_product(self, product_id: str) -> ProductRecord:
        product = self._catalog.get_product(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product

    def _sleep_for_origin(self) -> None:
        time.sleep(self._origin_delay_ms / 1000)

    def _to_product_card(self, product: ProductRecord) -> ProductCardResponse:
        stock = self._ensure_inventory(product)
        return ProductCardResponse(
            id=product.id,
            name=product.name,
            tagline=product.tagline,
            description=product.description,
            image_url=product.image_url,
            price=product.price,
            stock=stock,
            accent_color=product.accent_color,
            badge=product.badge,
            emoji=product.emoji,
            cache_namespace=self._detail_namespace(product.id),
        )

    def _ensure_inventory(self, product: ProductRecord) -> int:
        key = self._inventory_key(product.id)
        record = self._store.get(key, namespace=INVENTORY_NAMESPACE)
        if record is None:
            self._store.set(
                key=key,
                value_str=str(product.stock),
                namespace=INVENTORY_NAMESPACE,
            )
            return product.stock
        try:
            return int(record.value_str)
        except ValueError:
            self._store.set(
                key=key,
                value_str=str(product.stock),
                namespace=INVENTORY_NAMESPACE,
            )
            return product.stock

    def _product_from_cache_payload(self, product_id: str, payload: Any) -> ProductRecord:
        if not isinstance(payload, dict):
            raise ValueError("Invalid cache payload.")
        product = self._require_product(product_id)
        return ProductRecord(
            id=product_id,
            name=str(payload["name"]),
            tagline=str(payload["tagline"]),
            description=str(payload["description"]),
            image_url=str(payload["image_url"]),
            price=int(payload["price"]),
            stock=product.stock,
            accent_color=str(payload["accent_color"]),
            badge=str(payload["badge"]),
            emoji=str(payload["emoji"]),
        )

    @staticmethod
    def _file_state(raw_path: Any) -> tuple[bool, int]:
        if not isinstance(raw_path, str) or not raw_path:
            return False, 0
        path = Path(raw_path)
        if not path.exists():
            return False, 0
        return True, path.stat().st_size

    @staticmethod
    def _read_snapshot_payload(raw_path: Any) -> dict[str, object] | None:
        if not isinstance(raw_path, str) or not raw_path:
            return None
        path = Path(raw_path)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_aof_events(raw_path: Any) -> list[dict[str, object]]:
        if not isinstance(raw_path, str) or not raw_path:
            return []
        path = Path(raw_path)
        if not path.exists():
            return []
        repository = AofRepository(path)
        return [dict(event) for event in repository.load_all()]

    @staticmethod
    def _detail_namespace(product_id: str) -> str:
        return f"storefront-product:{product_id}"

    @staticmethod
    def _inventory_key(product_id: str) -> str:
        return f"inventory:{product_id}"
