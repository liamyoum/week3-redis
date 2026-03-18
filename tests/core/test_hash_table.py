from app.core import HashTable


def _constant_hash(_: str) -> int:
    return 0


def test_get_returns_none_for_missing_key() -> None:
    table = HashTable[str]()

    assert table.get("missing") is None


def test_put_then_get_returns_value() -> None:
    table = HashTable[int]()

    table.put("alpha", 1)

    assert table.get("alpha") == 1


def test_put_overwrites_existing_key_without_growing_size() -> None:
    table = HashTable[str]()

    table.put("alpha", "first")
    table.put("alpha", "second")

    assert table.get("alpha") == "second"
    assert len(table) == 1


def test_delete_returns_true_for_existing_key() -> None:
    table = HashTable[str]()
    table.put("alpha", "value")

    assert table.delete("alpha") is True
    assert len(table) == 0


def test_delete_returns_false_for_missing_key() -> None:
    table = HashTable[str]()

    assert table.delete("missing") is False


def test_deleted_key_returns_none() -> None:
    table = HashTable[str]()
    table.put("alpha", "value")

    table.delete("alpha")

    assert table.get("alpha") is None


def test_items_returns_all_pairs() -> None:
    table = HashTable[int]()
    table.put("alpha", 1)
    table.put("beta", 2)
    table.put("gamma", 3)

    assert set(table.items()) == {("alpha", 1), ("beta", 2), ("gamma", 3)}


def test_collision_chain_supports_multiple_keys() -> None:
    table = HashTable[str](hash_func=_constant_hash)
    table.put("alpha", "a")
    table.put("beta", "b")
    table.put("gamma", "c")

    assert table.get("alpha") == "a"
    assert table.get("beta") == "b"
    assert table.get("gamma") == "c"
    assert len(table) == 3


def test_delete_from_collision_chain_preserves_other_entries() -> None:
    table = HashTable[str](hash_func=_constant_hash)
    table.put("alpha", "a")
    table.put("beta", "b")
    table.put("gamma", "c")

    assert table.delete("beta") is True
    assert table.get("alpha") == "a"
    assert table.get("beta") is None
    assert table.get("gamma") == "c"
    assert len(table) == 2


def test_overwrite_in_collision_chain_keeps_size() -> None:
    table = HashTable[str](hash_func=_constant_hash)
    table.put("alpha", "first")
    table.put("alpha", "second")
    table.put("beta", "value")

    assert table.get("alpha") == "second"
    assert len(table) == 2


def test_resize_preserves_existing_data_and_size() -> None:
    table = HashTable[int](initial_capacity=2)

    for index in range(10):
        table.put(f"key-{index}", index)

    for index in range(10):
        assert table.get(f"key-{index}") == index

    assert len(table) == 10
    assert len(table._buckets) > 2


def test_delete_and_items_work_after_resize() -> None:
    table = HashTable[int](initial_capacity=2)

    for index in range(8):
        table.put(f"key-{index}", index)

    assert table.delete("key-3") is True
    assert table.delete("key-7") is True

    remaining_items = set(table.items())

    assert len(table) == 6
    assert ("key-3", 3) not in remaining_items
    assert ("key-7", 7) not in remaining_items
    assert ("key-0", 0) in remaining_items
    assert ("key-6", 6) in remaining_items
