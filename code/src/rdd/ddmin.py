"""Pure Zeller-Hildebrandt ddmin (1-minimisation).

Decoupled from the surrounding harness and fixtures so the algorithm can be unit-tested with synthetic
oracles. Exposes a single ``ddmin_search`` entry point: callers supply the elements and a crash predicate,
and it returns a 1-minimal subset. The robust pipeline (``rdd.minimizer``) reaches it only on a
suppressor-free seed, so within ``ddmin_search`` every tested subset is monotone.

References:
- Zeller & Hildebrandt, "Simplifying and Isolating Failure-Inducing Input", IEEE TSE 2002.
"""

from __future__ import annotations

from typing import Callable, Hashable, Sequence, TypeVar

T = TypeVar("T", bound=Hashable)


def ddmin_search(
    elements: Sequence[T],
    test: Callable[[Sequence[T]], bool],
) -> tuple[list[T], int]:
    """Find a 1-minimal subset of `elements` that satisfies `test`.

    Standard Zeller-Hildebrandt 1-minimisation. `test(subset)` returns True iff `subset` still reproduces
    the failing condition (in our setting: still reproduces the target crash via the oracle).

    Termination guarantee: if the full input passes the test, the returned subset is non-empty and
    1-minimal — removing any single element no longer reproduces (equivalently, under monotonicity, every
    proper subset fails). Worst-case oracle calls: O(|elements|²);
    typical: O(|elements| · log |elements|).

    Args:
        elements: Initial configuration. Members must be hashable so we can compute set complements.
        test: Predicate over subsets. Must be monotone enough that the algorithm makes progress (no formal
            monotonicity required; a noisy oracle just produces a less-minimal result).

    Returns:
        (minimal_subset, n_test_calls). If the initial `elements` does not pass `test`, returns ([], 1).
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
        # Once down to <=1 element, every chunk is either the full set or empty — there is no further
        # reduction. The most recent successful `counted` already confirmed `elements` reproduces.
        if len(elements) <= 1:
            return elements, n_calls

        # Split `elements` into n roughly-equal chunks.
        chunk_size = max(1, len(elements) // n)
        chunks: list[list[T]] = []
        for i in range(n):
            start = i * chunk_size
            end = start + chunk_size if i < n - 1 else len(elements)
            chunks.append(elements[start:end])

        # 1) Try each chunk alone. Skip non-reducing chunks (whole-set equivalents) so we never re-accept
        # the current state as a step.
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

        # 2) Try each complement. Same non-reducing skip.
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

        # 3) Neither a chunk nor a complement reproduces. Refine.
        if n >= len(elements):
            # Cannot subdivide further — current elements is 1-minimal.
            return elements, n_calls
        n = min(n * 2, len(elements))


__all__ = ["ddmin_search"]
