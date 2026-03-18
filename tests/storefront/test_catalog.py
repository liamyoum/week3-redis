from app.storefront.catalog import ProductRecord


def test_product_record_falls_back_to_default_image_url() -> None:
    product = ProductRecord.from_document(
        {
            "id": "legacy-product",
            "name": "Legacy",
            "tagline": "old",
            "description": "stored before image support",
            "price": 10,
            "stock": 3,
            "accent_color": "#ffffff",
            "badge": "old",
            "emoji": "📦",
        }
    )

    assert product.image_url == "https://picsum.photos/seed/legacy-product/900/700"


def test_product_record_cache_payload_keeps_stock() -> None:
    product = ProductRecord(
        id="stocked-product",
        name="Stocked",
        tagline="ready",
        description="cache payload should stay self-contained",
        image_url="https://example.com/item.png",
        price=10,
        stock=7,
        accent_color="#ffffff",
        badge="badge",
        emoji="📦",
    )

    payload = product.to_cache_payload()

    assert payload["stock"] == 7
