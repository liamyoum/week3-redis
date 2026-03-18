from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


@dataclass(frozen=True, slots=True)
class ProductRecord:
    id: str
    name: str
    tagline: str
    description: str
    image_url: str
    price: int
    stock: int
    accent_color: str
    badge: str
    emoji: str

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> ProductRecord:
        product_id = str(document["id"])
        return cls(
            id=product_id,
            name=str(document["name"]),
            tagline=str(document["tagline"]),
            description=str(document["description"]),
            image_url=str(document.get("image_url", _default_image_url(product_id))),
            price=int(document["price"]),
            stock=int(document["stock"]),
            accent_color=str(document["accent_color"]),
            badge=str(document["badge"]),
            emoji=str(document["emoji"]),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tagline": self.tagline,
            "description": self.description,
            "image_url": self.image_url,
            "price": self.price,
            "stock": self.stock,
            "accent_color": self.accent_color,
            "badge": self.badge,
            "emoji": self.emoji,
        }

    def to_cache_payload(self) -> dict[str, Any]:
        return self.to_document()


class ProductCatalogProtocol(Protocol):
    @property
    def source_name(self) -> str:
        ...

    def list_products(self) -> list[ProductRecord]:
        ...

    def get_product(self, product_id: str) -> ProductRecord | None:
        ...

    def update_stock(self, product_id: str, stock: int) -> ProductRecord | None:
        ...

    def close(self) -> None:
        ...


def load_seed_products(seed_path: str | Path) -> list[ProductRecord]:
    payload = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Seed product payload must be a list.")
    return [ProductRecord.from_document(item) for item in payload]


class SeedProductCatalog:
    def __init__(self, products: Sequence[ProductRecord], source_name: str = "seed") -> None:
        self._products = {product.id: product for product in products}
        self._order = [product.id for product in products]
        self._source_name = source_name

    @property
    def source_name(self) -> str:
        return self._source_name

    def list_products(self) -> list[ProductRecord]:
        return [self._products[product_id] for product_id in self._order]

    def get_product(self, product_id: str) -> ProductRecord | None:
        return self._products.get(product_id)

    def update_stock(self, product_id: str, stock: int) -> ProductRecord | None:
        product = self._products.get(product_id)
        if product is None:
            return None
        updated = ProductRecord(
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
        )
        self._products[product_id] = updated
        return updated

    def close(self) -> None:
        return None


class MongoProductCatalog:
    def __init__(
        self,
        uri: str,
        database_name: str,
        collection_name: str,
        seed_products: Sequence[ProductRecord],
    ) -> None:
        self._client: MongoClient[dict[str, Any]] = MongoClient(
            uri,
            serverSelectionTimeoutMS=1500,
        )
        self._collection: Collection[dict[str, Any]] = self._client[database_name][collection_name]
        self._seed_products = list(seed_products)
        self._ensure_seeded()

    @property
    def source_name(self) -> str:
        return "mongo"

    def list_products(self) -> list[ProductRecord]:
        documents = list(self._collection.find({}, {"_id": False}).sort("price", 1))
        return [ProductRecord.from_document(document) for document in documents]

    def get_product(self, product_id: str) -> ProductRecord | None:
        document = self._collection.find_one({"id": product_id}, {"_id": False})
        if document is None:
            return None
        return ProductRecord.from_document(document)

    def update_stock(self, product_id: str, stock: int) -> ProductRecord | None:
        document = self._collection.find_one_and_update(
            {"id": product_id},
            {"$set": {"stock": stock}},
            projection={"_id": False},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return ProductRecord.from_document(document)

    def close(self) -> None:
        self._client.close()

    def _ensure_seeded(self) -> None:
        self._client.admin.command("ping")
        self._collection.create_index("id", unique=True)
        seed_ids = [product.id for product in self._seed_products]
        self._collection.delete_many({"id": {"$nin": seed_ids}})
        for product in self._seed_products:
            document = product.to_document()
            stock = document.pop("stock")
            existing = self._collection.find_one({"id": product.id}, {"_id": False, "stock": True})
            update_fields = dict(document)
            if existing is None or "stock" not in existing:
                update_fields["stock"] = stock
            self._collection.update_one(
                {"id": product.id},
                {"$set": update_fields},
                upsert=True,
            )


def build_product_catalog(
    mongo_uri: str,
    database_name: str,
    collection_name: str,
    seed_path: str | Path,
) -> ProductCatalogProtocol:
    seed_products = load_seed_products(seed_path)
    if not mongo_uri:
        return SeedProductCatalog(seed_products)

    try:
        return MongoProductCatalog(
            uri=mongo_uri,
            database_name=database_name,
            collection_name=collection_name,
            seed_products=seed_products,
        )
    except PyMongoError:
        return SeedProductCatalog(seed_products, source_name="seed-fallback")


def _default_image_url(product_id: str) -> str:
    return f"https://picsum.photos/seed/{product_id}/900/700"
