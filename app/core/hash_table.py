from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

ValueT = TypeVar("ValueT")

FNV_64_OFFSET_BASIS = 14695981039346656037
FNV_64_PRIME = 1099511628211
DEFAULT_CAPACITY = 8
DEFAULT_MAX_LOAD_FACTOR = 0.75


def fnv1a_64(key: str) -> int:
    hash_value = FNV_64_OFFSET_BASIS

    for byte in key.encode("utf-8"):
        hash_value ^= byte
        hash_value = (hash_value * FNV_64_PRIME) & 0xFFFFFFFFFFFFFFFF

    return hash_value


@dataclass(slots=True)
class _Node(Generic[ValueT]):
    key: str
    value: ValueT
    next: _Node[ValueT] | None = None


class HashTable(Generic[ValueT]):
    def __init__(
        self,
        initial_capacity: int = DEFAULT_CAPACITY,
        max_load_factor: float = DEFAULT_MAX_LOAD_FACTOR,
        hash_func: Callable[[str], int] | None = None,
    ) -> None:
        if initial_capacity < 1:
            raise ValueError("initial_capacity must be at least 1")
        if max_load_factor <= 0:
            raise ValueError("max_load_factor must be greater than 0")

        self._buckets: list[_Node[ValueT] | None] = [None] * initial_capacity
        self._size = 0
        self._max_load_factor = max_load_factor
        self._hash_func = hash_func or fnv1a_64

    def put(self, key: str, value: ValueT) -> None:
        index = self._bucket_index(key)
        node = self._buckets[index]

        while node is not None:
            if node.key == key:
                node.value = value
                return
            node = node.next

        if self._projected_load_factor() > self._max_load_factor:
            self._resize()
            index = self._bucket_index(key)

        self._buckets[index] = _Node(key=key, value=value, next=self._buckets[index])
        self._size += 1

    def get(self, key: str) -> ValueT | None:
        node = self._find_node(key)
        return None if node is None else node.value

    def delete(self, key: str) -> bool:
        index = self._bucket_index(key)
        node = self._buckets[index]
        previous: _Node[ValueT] | None = None

        while node is not None:
            if node.key == key:
                if previous is None:
                    self._buckets[index] = node.next
                else:
                    previous.next = node.next

                self._size -= 1
                return True

            previous = node
            node = node.next

        return False

    def items(self) -> Iterable[tuple[str, ValueT]]:
        return self._iter_items()

    def __len__(self) -> int:
        return self._size

    def _find_node(self, key: str) -> _Node[ValueT] | None:
        index = self._bucket_index(key)
        node = self._buckets[index]

        while node is not None:
            if node.key == key:
                return node
            node = node.next

        return None

    def _bucket_index(self, key: str) -> int:
        return self._hash_func(key) % len(self._buckets)

    def _projected_load_factor(self) -> float:
        return (self._size + 1) / len(self._buckets)

    def _resize(self) -> None:
        old_items = list(self._iter_items())
        self._buckets = [None] * (len(self._buckets) * 2)
        self._size = 0

        for key, value in old_items:
            self.put(key, value)

    def _iter_items(self) -> Iterator[tuple[str, ValueT]]:
        for bucket in self._buckets:
            node = bucket
            while node is not None:
                yield (node.key, node.value)
                node = node.next
