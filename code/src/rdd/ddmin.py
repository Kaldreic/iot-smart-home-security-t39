"""ddmin (Zeller & Hildebrandt 2002), decoupled from any oracle.

``ddmin_search`` takes the elements and a crash predicate and returns a 1-minimal subset. The robust
minimiser (``rdd.minimizer``) calls it only on a suppressor-free seed, where every tested subset is
monotone.
"""

from __future__ import annotations

from typing import Callable, Hashable, Sequence, TypeVar

T = TypeVar("T", bound=Hashable)


def ddmin_search(
    elements: Sequence[T],
    test: Callable[[Sequence[T]], bool],
) -> tuple[list[T], int]:
    """Find a 1-minimal subset of ``elements`` that satisfies ``test``.

    Returns ``(subset, n_test_calls)``. If the full input fails ``test`` the result is ``([], 1)``;
    otherwise the subset is non-empty and removing any one element makes ``test`` fail. Worst case
    O(n^2) calls, typically O(n log n). A noisy ``test`` just yields a less minimal result.
    """
    n_calls = 0

    def counted(subset: Sequence[T]) -> bool:
        nonlocal n_calls
        n_calls += 1
        return test(subset)

    elements = list(elements)
    if not counted(elements):
        return [], n_calls

    n = 2
    while True:
        # One element cannot be reduced further; the last successful test already confirmed it.
        if len(elements) <= 1:
            return elements, n_calls

        # Split into n roughly equal chunks.
        chunk_size = max(1, len(elements) // n)
        chunks: list[list[T]] = []
        for i in range(n):
            start = i * chunk_size
            end = start + chunk_size if i < n - 1 else len(elements)
            chunks.append(elements[start:end])

        # 1) Try each chunk alone; a chunk equal to the whole set is not a reduction.
        progressed = False
        for chunk in chunks:
            if not chunk or len(chunk) >= len(elements):
                continue
            if counted(chunk):
                elements = chunk
                n = 2
                progressed = True
                break
        if progressed:
            continue

        # 2) Try each complement.
        for chunk in chunks:
            chunk_set = set(chunk)
            complement = [e for e in elements if e not in chunk_set]
            if not complement or len(complement) >= len(elements):
                continue
            if counted(complement):
                elements = complement
                n = max(n - 1, 2)
                progressed = True
                break
        if progressed:
            continue

        # 3) Neither reduces; refine the partition.
        if n >= len(elements):
            # Cannot subdivide further: the current elements are 1-minimal.
            return elements, n_calls
        n = min(n * 2, len(elements))


__all__ = ["ddmin_search"]
