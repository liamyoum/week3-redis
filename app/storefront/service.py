from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.domain.contracts import StoreProtocol
from app.domain.models import StoreRecord
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

DETAIL_KEY = "detail"


class ProductNotFoundError(LookupError):
    """Raised when a requested storefront product is missing."""


class StorefrontService:
    def __init__(
        self,
        store: StoreProtocol,
        catalog: ProductCatalogProtocol,
        snapshot_status_provider: Callable[[], dict[str, Any]],
        origin_delay_ms: int = 0,
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
        self._write_detail_cache(product)
        latency_ms = (time.perf_counter() - started) * 1000
        return ProductDetailResponse(
            product=self._to_product_card(product),
            source="cache",
            origin_source=self._catalog.source_name,
            cache_status="miss",
            latency_ms=latency_ms,
        )

    def reserve_product(self, product_id: str, session_id: str, ttl_ms: int) -> ReserveResponse:
        product = self._load_from_origin(product_id)
        namespace = self._detail_namespace(product_id)
        hold_key = f"{namespace}:{DETAIL_KEY}"
        record = self._write_detail_cache(product, ttl_ms=ttl_ms)
        return ReserveResponse(
            product_id=product_id,
            session_id=session_id,
            hold_key=hold_key,
            ttl_ms=ttl_ms,
            expires_at_ms=record.expires_at_ms or 0,
        )

    def purchase_product(self, product_id: str, quantity: int) -> PurchaseResponse:
        product = self._require_product(product_id)
        current_stock = product.stock
        if quantity > current_stock:
            raise ValueError("Not enough stock remaining for this drop.")
        remaining_stock = current_stock - quantity
        updated_product = self._sync_origin_stock(product_id, remaining_stock)
        self._write_detail_cache(updated_product)
        return PurchaseResponse(
            product_id=product_id,
            quantity=quantity,
            stock=remaining_stock,
        )

    def restock_product(self, product_id: str, quantity: int) -> PurchaseResponse:
        product = self._require_product(product_id)
        next_stock = product.stock + quantity
        updated_product = self._sync_origin_stock(product_id, next_stock)
        self._write_detail_cache(updated_product)
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
        snapshot_exists, snapshot_size, snapshot_updated_at_ms = self._file_state(snapshot_path)
        aof_exists, aof_size, aof_updated_at_ms = self._file_state(aof_path)
        return StoreStateResponse(
            origin_source=self._catalog.source_name,
            origin_delay_ms=self._origin_delay_ms,
            product_count=len(self._catalog.list_products()),
            snapshot_path=snapshot_path if isinstance(snapshot_path, str) else None,
            snapshot_exists=snapshot_exists,
            snapshot_size_bytes=snapshot_size,
            snapshot_updated_at_ms=snapshot_updated_at_ms,
            aof_path=aof_path if isinstance(aof_path, str) else None,
            aof_exists=aof_exists,
            aof_size_bytes=aof_size,
            aof_updated_at_ms=aof_updated_at_ms,
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
        return ProductCardResponse(
            id=product.id,
            name=product.name,
            tagline=product.tagline,
            description=product.description,
            image_url=product.image_url,
            price=product.price,
            stock=product.stock,
            accent_color=product.accent_color,
            badge=product.badge,
            emoji=product.emoji,
            cache_namespace=self._detail_namespace(product.id),
        )

    def _product_from_cache_payload(self, product_id: str, payload: Any) -> ProductRecord:
        if not isinstance(payload, dict):
            raise ValueError("Invalid cache payload.")
        return ProductRecord(
            id=product_id,
            name=str(payload["name"]),
            tagline=str(payload["tagline"]),
            description=str(payload["description"]),
            image_url=str(payload["image_url"]),
            price=int(payload["price"]),
            stock=int(payload["stock"]),
            accent_color=str(payload["accent_color"]),
            badge=str(payload["badge"]),
            emoji=str(payload["emoji"]),
        )

    def _sync_origin_stock(self, product_id: str, stock: int) -> ProductRecord:
        updated = self._catalog.update_stock(product_id, stock)
        if updated is not None:
            return updated
        return self._require_product(product_id)

    def _write_detail_cache(
        self,
        product: ProductRecord,
        ttl_ms: int | None = None,
    ) -> StoreRecord:
        namespace = self._detail_namespace(product.id)
        effective_ttl_ms = ttl_ms
        if effective_ttl_ms is None:
            cached_record = self._store.get(DETAIL_KEY, namespace=namespace)
            if cached_record is not None and cached_record.expires_at_ms is not None:
                remaining_ttl_ms = cached_record.expires_at_ms - self._default_now_ms()
                if remaining_ttl_ms > 0:
                    effective_ttl_ms = remaining_ttl_ms
        return self._store.set(
            key=DETAIL_KEY,
            value_str=json.dumps(product.to_cache_payload(), separators=(",", ":")),
            ttl_ms=effective_ttl_ms,
            namespace=namespace,
        )

    @staticmethod
    def _default_now_ms() -> int:
        return time.time_ns() // 1_000_000

    @staticmethod
    def _file_state(raw_path: Any) -> tuple[bool, int, int | None]:
        if not isinstance(raw_path, str) or not raw_path:
            return False, 0, None
        path = Path(raw_path)
        if not path.exists():
            return False, 0, None
        stat = path.stat()
        return True, stat.st_size, int(stat.st_mtime * 1000)

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
