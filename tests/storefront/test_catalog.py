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
