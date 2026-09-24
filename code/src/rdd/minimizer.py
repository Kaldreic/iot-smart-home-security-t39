"""Non-monotone-robust minimisation: seed-finding and suppressor verification around ddmin.

ddmin (Zeller & Hildebrandt 2002) only removes elements and assumes that adding elements cannot undo
a failure. A suppressor, an element whose presence removes the crash, breaks that in two ways: the
full window contains it and does not crash, so ddmin returns ``[]`` at its first query (mode 1); or
ddmin strips it mid-reduction and converges on a different crash than the target (mode 2). Neither can
be detected by the test alone without probing supersets, so ``robust_minimize`` tests the full window;
if it does not crash, searches for a crashing seed by bounded leave-k-out and choose-k probing; runs
ddmin inside the seed, whose subsets are suppressor-free and hence monotone; re-adds each excluded
element to confirm suppressors; and re-tests the recipe before crediting it. The result is a 1-minimal
crashing recipe verified up to single re-addition, not a global minimum; a non-empty minimal trigger
is assumed.

Every phase except the in-seed ddmin probes transitions that a monotone cache answers wrongly, so those
phases take a separate uncached ``raw_test``, which should also have few false negatives. The in-seed
cache must be fresh per call rather than the campaign cache, and the final validation is a single
``raw_test`` call, so its guarantee is only as good as ``raw_test``. ``rdd.pipeline`` does the wiring.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Hashable, Sequence, TypeVar

from .ddmin import ddmin_search

T = TypeVar("T", bound=Hashable)
Test = Callable[[Sequence[T]], bool]


def _in_order(members, elements):
    """The members of ``elements`` whose values are in ``members``, in the caller's order. Used instead
    of ``sorted`` so elements need only be hashable and an order-sensitive oracle sees its sequence."""
    m = members if isinstance(members, (set, frozenset)) else set(members)
    return [e for e in elements if e in m]


@dataclass
class RobustResult:
    """Outcome of one ``robust_minimize`` run.

    ``reproduced`` holds only if ``recipe`` is non-empty and passed final validation on the raw oracle.
    ``suppressors`` are the excluded elements whose re-addition removed the crash, a diagnostic only as
    reliable as ``raw_test``. ``strategy`` is how the seed was found: "full", "tear-down:k",
    "build-up:k", "exhausted" (the bounded candidate set was searched in full) or "none" (the
    ``max_seed_calls`` budget ran out first, also flagged by ``capped``). ``n_calls`` counts every
    ``test`` and ``raw_test`` call."""

    recipe: list
    suppressors: list
    seed: list | None
    strategy: str
    n_calls: int
    capped: bool
    validated: bool        # no default: an unset value must never credit a reproduction

    @property
    def reproduced(self) -> bool:
        # ``is True`` keeps this a strict bool even if a caller constructed the result with a non-bool.
        return bool(self.recipe) and self.validated is True

    @property
    def size(self) -> int | None:
        return len(self.recipe) if self.reproduced else None


def _seed_candidates(elements, *, max_remove, max_build, most_recent_first):
    """Yield ``(strategy, candidate)`` seeds cheapest first and deduplicated: for k = 1, 2, ... the
    leave-k-out complements ("tear-down:k") and then the size-k combinations ("build-up:k"). Tear-down
    leads because a suppressor is the likely reason the full window did not crash. ``most_recent_first``
    only changes which equal-cost seed is found first."""
    n = len(elements)
    full = set(elements)
    order = list(elements)[::-1] if most_recent_first else list(elements)
    seen: set[frozenset] = set()
    for k in range(1, max(max_remove, max_build) + 1):
        tiers = []
        if k <= max_remove:
            tiers.append(("tear-down", True))   # candidate = full - comb
        if k <= max_build and k < n:            # a build-up of size n is the full window, already tested
            tiers.append(("build-up", False))   # candidate = comb
        for name, is_tear in tiers:
            for comb in itertools.combinations(order, k):
                cand = _in_order(full - set(comb), elements) if is_tear else _in_order(comb, elements)
                if not cand:
                    continue
                key = frozenset(cand)
                if key in seen:
                    continue
                seen.add(key)
                yield f"{name}:{k}", cand


def find_seed(elements, raw_test: Test, *, max_remove: int = 2, max_build: int = 3,
              most_recent_first: bool = True, max_seed_calls: int | None = None):
    """Search for a crashing seed when the full window does not crash. Returns ``(seed, strategy,
    calls, capped)``: ``seed`` is the first candidate ``raw_test`` accepts, or ``None`` when the
    ``max_seed_calls`` budget (``capped=True``) or the candidate set ("exhausted") ran out."""
    calls = 0
    for strategy, cand in _seed_candidates(elements, max_remove=max_remove, max_build=max_build,
                                           most_recent_first=most_recent_first):
        if max_seed_calls is not None and calls >= max_seed_calls:
            return None, strategy, calls, True
        calls += 1
        if raw_test(cand):
            return cand, strategy, calls, False
    return None, "exhausted", calls, False


def undoing_change_verify(recipe, elements, raw_test: Test):
    """Re-add each excluded element to ``recipe`` and re-test on the raw oracle. Returns ``(suppressors,
    calls)``; a suppressor is an element whose re-addition removes the crash (Zeller's undoing change).
    Single re-addition only: a pair that suppresses only jointly is not detected."""
    rset = set(recipe)
    suppressors, calls = [], 0
    for e in elements:
        if e in rset:
            continue
        calls += 1
        if not raw_test(_in_order(rset | {e}, elements)):
            suppressors.append(e)
    return suppressors, calls


def robust_minimize(elements: Sequence[T], test: Test, *, raw_test: Test | None = None,
                    identity_check: Test | None = None,
                    max_remove: int = 2, max_build: int = 3, max_seed_calls: int | None = None,
                    verify: bool = True, verify_always: bool = False,
                    most_recent_first: bool = True) -> RobustResult:
    """Seed-find, run ddmin inside the seed, verify suppressors and validate; returns a ``RobustResult``.

    ``test`` answers the crash query for the in-seed ddmin and may be cache-backed. ``raw_test`` answers
    the same query without a cache for every other phase; it defaults to ``test``, which is correct only
    when ``test`` is uncached, since final validation would otherwise consult the same cache.
    ``identity_check``, if given, must also accept the recipe for it to count as validated; it guards
    against converging on a different crash than the target and can only demote a result. ``verify``
    runs the suppressor check only when seed-finding fired; ``verify_always`` runs it on a full seed as
    well, for the case where ddmin could have stripped a suppressor of another crash."""
    elements = list(elements)
    if len(set(elements)) != len(elements):       # the seed search relies on set arithmetic
        raise ValueError("robust_minimize requires DISTINCT elements (a window of indices/packets)")
    raw = raw_test if raw_test is not None else test
    n_calls = 0

    # Phase 0: does the full window crash? Decided on the raw oracle.
    n_calls += 1
    if raw(elements):
        seed, strategy, capped = elements, "full", False
    else:
        # Phase 1: it does not; search for a crashing seed.
        seed, strategy, sc, capped = find_seed(elements, raw, max_remove=max_remove, max_build=max_build,
                                               most_recent_first=most_recent_first,
                                               max_seed_calls=max_seed_calls)
        n_calls += sc
        if seed is None:
            return RobustResult([], [], None, "none" if capped else "exhausted", n_calls, capped,
                                validated=False)

    # Phase 2: ddmin inside the seed, where every subset is suppressor-free and the cached test is sound.
    def counted(subset):
        nonlocal n_calls
        n_calls += 1
        return test(subset)

    recipe, _ = ddmin_search(seed, counted)
    recipe = _in_order(recipe, elements)

    # Phase 3: confirm suppressors on the raw oracle, only when seed-finding fired (or verify_always).
    suppressors = []
    if verify and recipe and (verify_always or strategy != "full"):
        suppressors, vc = undoing_change_verify(recipe, elements, raw)
        n_calls += vc

    # Phase 4: re-test the recipe on the raw oracle before crediting it, since ddmin may have followed a
    # cache false-YES into a non-crashing region. A failing recipe is kept for diagnosis with
    # validated=False. ``is True`` rejects a truthy non-bool on this credit-bearing call (ddmin and the
    # seed search gate on truthiness).
    if recipe:
        n_calls += 1
        validated = raw(recipe) is True
        # Phase 4b: the recipe crashes; confirm it is the target crash. Demote-only.
        if validated and identity_check is not None:
            n_calls += 1
            validated = identity_check(recipe) is True
    else:
        validated = False

    return RobustResult(recipe, suppressors, list(seed), strategy, n_calls, capped, validated=validated)


__all__ = ["robust_minimize", "find_seed", "undoing_change_verify", "RobustResult"]
