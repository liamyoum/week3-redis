from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.dependencies import get_storefront_service
from app.domain.schemas import (
    InvalidateResponse,
    ProductDetailResponse,
    ProductListResponse,
    PurchaseRequest,
    PurchaseResponse,
    ReserveRequest,
    ReserveResponse,
    StoreStateResponse,
)
from app.storefront.service import ProductNotFoundError, StorefrontService

router = APIRouter(tags=["storefront"])
StorefrontDep = Annotated[StorefrontService, Depends(get_storefront_service)]


@router.get("/store/products", response_model=ProductListResponse)
def list_products(storefront: StorefrontDep) -> ProductListResponse:
    return storefront.list_products()


@router.get("/store/products/{product_id}/direct", response_model=ProductDetailResponse)
def get_direct_product(
    storefront: StorefrontDep,
    product_id: str = Path(min_length=1),
) -> ProductDetailResponse:
    try:
        return storefront.get_direct_product(product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        ) from exc


@router.get("/store/products/{product_id}/cached", response_model=ProductDetailResponse)
def get_cached_product(
    storefront: StorefrontDep,
    product_id: str = Path(min_length=1),
) -> ProductDetailResponse:
    try:
        return storefront.get_cached_product(product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        ) from exc


@router.post("/store/products/{product_id}/reserve", response_model=ReserveResponse)
def reserve_product(
    payload: ReserveRequest,
    storefront: StorefrontDep,
    product_id: str = Path(min_length=1),
) -> ReserveResponse:
    try:
        return storefront.reserve_product(product_id, payload.session_id, payload.ttl_ms)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        ) from exc


@router.post("/store/products/{product_id}/purchase", response_model=PurchaseResponse)
def purchase_product(
    payload: PurchaseRequest,
    storefront: StorefrontDep,
    product_id: str = Path(min_length=1),
) -> PurchaseResponse:
    try:
        return storefront.purchase_product(product_id, payload.quantity)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/store/products/{product_id}/restock", response_model=PurchaseResponse)
def restock_product(
    payload: PurchaseRequest,
    storefront: StorefrontDep,
    product_id: str = Path(min_length=1),
) -> PurchaseResponse:
    try:
        return storefront.restock_product(product_id, payload.quantity)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        ) from exc


@router.post("/store/products/{product_id}/invalidate", response_model=InvalidateResponse)
def invalidate_product(
    storefront: StorefrontDep,
    product_id: str = Path(min_length=1),
) -> InvalidateResponse:
    try:
        version = storefront.invalidate_product(product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        ) from exc
    namespace = storefront.detail_namespace(product_id)
    return InvalidateResponse(namespace=namespace, version=version)


@router.get("/store/state", response_model=StoreStateResponse)
def get_store_state(storefront: StorefrontDep) -> StoreStateResponse:
    return storefront.get_state()
