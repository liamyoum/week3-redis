from app.domain.contracts import StoreProtocol


def get_store() -> StoreProtocol:
    raise NotImplementedError("Store dependency is not configured in the seed PR.")
