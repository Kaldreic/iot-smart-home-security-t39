"""A non-monotone-ROBUST minimiser: seed-finder + undoing-change verification around ddmin.

WHY. ddmin (Zeller-Hildebrandt, TSE 2002) is a SUBTRACTIVE 1-minimiser: it assumes the maximal
configuration fails and only ever REMOVES elements. Its guarantees rest on MONOTONICITY -- "once a
failure occurs, one cannot make it disappear by adding more 'undoing' changes". A non-monotone
SUPPRESSOR -- an element whose PRESENCE removes the crash, exactly Zeller's "undoing change" -- breaks
that assumption in two distinct ways:

  * MODE 1 (seed-bail).  The maximal config (full window) CONTAINS the suppressor, so it does not
    crash, so ddmin's precondition test(seed)=FAIL is violated and ddmin returns [] on its first
    query -- it never even starts.  (This is the regime the ddmin-only ablation loses on.)
  * MODE 2 (wrong-cause local minimum).  Given a failing seed, ddmin can STRIP a suppressor mid-
    reduction and converge on a valid-but-different 1-minimal (Zeller's <A></A><B> -> <A>): still a
    crash, but not the intended cause.

THEORY SAYS this has no free oracle-only fix.  Detecting an undoing change "cannot use test alone (this
would require testing up to 2^|c| SUPERSETS of the minimized test case)" (Zeller-Hildebrandt 2002), and
the GLOBAL minimal-failing-subset problem is NP-complete REGARDLESS of monotonicity (HDD, Misherghi &
Su, ICSE 2006, Thm 3.5: reduction from Hitting Set).  So we do NOT promise a global minimum.  We promise
a 1-minimal crashing PoC that is additionally VERIFIED non-suppressed up to bounded superset re-addition
-- a bounded, honest upgrade over ddmin's silent failure.  (We assume a NON-EMPTY minimal trigger: a
vacuous crash where the empty input already fails is out of scope, consistent with ddmin's "every
PROPER subset passes" contract.)

WHAT THIS UNIT DOES (oracle-agnostic: ``test(subset) -> bool`` is the SAME crash predicate ddmin
consumes, so the SPRT two-tier oracle, the L2/L3 crash-identity matcher, and final-validation all still
wrap it unchanged):

  0. If ``test(full)`` already crashes -> hand straight to ddmin.  NO seed-finding overhead on the
     monotone majority (it still pays one maximal-element probe + the raw final-validation).  This
     one-probe monotonicity check is a lightweight cousin of PMA (Tao & Xue, EASE 2025), which instead
     treats monotonicity as a measured CONFIDENCE rather than a single max-element signal.
  1. Else SEED-FIND (Mode 1).  The maximal config does not crash though a crash is believed to exist,
     so SEARCH for a crashing subset by bounded COMPLEMENT/SUPERSET probing -- the only test-based move
     the theory sanctions:
       * TEAR-DOWN (leave-k-out): remove k elements from the full window; a crashing complement proves
         the removed k CONTAIN the suppressor(s).  Finds LARGE minimals with FEW suppressors.
       * BUILD-UP (combinations of size t, most-recent-first): the baseline's increasing-cardinality
         enumeration reused as a seed-finder -- finds SMALL minimals regardless of suppressor count.
     Probes are issued CHEAPEST-COST-FIRST, deduplicated, and bounded by (max_remove, max_build,
     max_seed_calls).  Two distinct []-outcomes, never silent: the BUDGET FLOOR (max_seed_calls hit
     before a crash) -> [] with capped=True; genuine EXHAUSTION of the bounded candidate set -> [] with
     strategy="exhausted", capped=False (proof of absence within the bound).  The UNION of the two
     tiers dominates both the baseline enumeration (small-M / suppressor-robust but cardinality-capped)
     and bare ddmin (large-M but suppressor-fragile).
  2. ddmin WITHIN the found seed.  The seed excludes the suppressor(s); ddmin only removes and never
     re-adds, so every subset it tests is suppressor-free => that subspace is MONOTONE => ddmin's
     1-minimality holds intact.  (This is the precise sense in which the weakness is NOT structural: the
     suppressor bites only at the seed.)
  3. UNDOING-CHANGE VERIFICATION (Mode 2 + soundness).  Re-add each EXCLUDED element e to the converged
     recipe R and re-test: if ``test(R ∪ {e})`` is FALSE, e is a CONFIRMED suppressor (its presence
     undoes the crash).  This (a) certifies R is non-suppressed up to single re-addition, (b) reports
     the suppressor set (a real diagnostic -- e.g. a Zephyr length_req LLCP collision), and (c) is the
     hook where an L2/L3 identity check catches a Mode-2 cause-swap.  Single re-addition is an honest
     limit (a strictly-pairwise suppressor needs 2-re-addition).

THE CACHE CAVEAT (load-bearing for the pipeline wiring).  The monotone-closure cache's two
inferences -- superset-of-YES => YES and subset-of-NO => NO -- are SOUND ONLY UNDER MONOTONICITY (Zeller
2002 Sec. VII derives the cache FROM the monotony assumption).  The seed-finder and the verifier
deliberately probe the NON-monotone transitions those closures get wrong (a subset of a non-crashing
superset that DOES crash; a superset of a crashing recipe that does NOT).  So they MUST run on the RAW,
UNCACHED oracle.  Only Phase 2 (ddmin inside the suppressor-free seed) may use the cache.  This unit
takes a separate ``raw_test`` for exactly that split; it defaults to ``test`` (correct when ``test`` is
already uncached, as in the standalone tests).  ``raw_test`` should also be LOW-false-NEGATIVE: a single
crashing complement (the one leave-1-out that removes the lone suppressor) must not be skipped on a
flaky NO.  Two more obligations the pipeline meets: (i) the in-seed ddmin's cache must be a FRESH cache
scoped to the found seed, NOT the campaign cache (whose full-window NO would, by downward closure,
wrongly prune the seed's suppressor-free sublattice); (ii) every guarantee is only as reliable as
``raw_test`` -- final-validation is a SINGLE ``raw(recipe)`` call, so it blocks false credit only when
``raw_test`` is TRUSTWORTHY (truthful, as in the deterministic tests, or an SPRT-trusted oracle whose p0
brackets the worst non-crasher per-rep false-YES).  Likewise the suppressor list is best-effort until
each re-addition is an SPRT-trusted decision.

NOVELTY.  No published reducer combines {adaptive statistical / SPRT resampling oracle + non-monotone
robustness + unbounded-cardinality minimisation}.  The flaky-oracle field DETERMINISES-then-reduces
(Choi-Zeller record/replay, ISSTA 2002), FILTERS non-reproducible failures (libFuzzer/ClusterFuzz), or
ABORTS (Hypothesis's ``Flaky``); none resamples in-loop.  FIC/FIC_BS (Zhang & Zhang, ISSTA 2011) assume
"no new inducing combination introduced when a value changes" -- the exact suppressor violation; ELA
needs known per-position safe values; PMA (EASE 2025) detects non-monotonicity for EFFICIENCY only.
This unit is oracle-agnostic, so it inherits any of those as the ``test`` it is handed.

Run: ``python -m rdd.tests.test_rdd``  (after `pip install -e .`)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Hashable, Sequence, TypeVar

from .ddmin import ddmin_search

T = TypeVar("T", bound=Hashable)
Test = Callable[[Sequence[T]], bool]


def _in_order(members, elements):
    """Subset of ``elements`` (in the CALLER's original order) whose values are in ``members``.  Used
    everywhere instead of ``sorted(...)`` so the unit works on non-orderable (only-hashable) elements --
    real packet objects -- and preserves sequence order for an order-sensitive oracle."""
    m = members if isinstance(members, (set, frozenset)) else set(members)
    return [e for e in elements if e in m]


@dataclass
class RobustResult:
    """The outcome of one robust-minimise run.

    ``recipe`` is the converged candidate subset ([] iff none found).  A result counts as a reproduction
    (``reproduced``) ONLY if ``recipe`` is non-empty AND it passed the RAW final-validation
    (``validated``) -- so a reproduced recipe always genuinely crashes the raw oracle, even if the
    in-seed ddmin ran on a cache that lied.  ``suppressors`` are the elements CONFIRMED (by re-addition)
    to undo the crash -- a best-effort DIAGNOSTIC, only as reliable as ``raw_test`` (under a flaky raw
    oracle it can fabricate/miss; an SPRT-trusted raw oracle is the fix).  ``seed`` is the
    crashing seed ddmin reduced.  ``strategy`` records how the seed was obtained ("full" | "tear-down:k"
    | "build-up:k" | "exhausted" | "none").  ``n_calls`` counts every ``test``/``raw_test`` call (maximal
    gate + seed-find + ddmin + verify + final-validation).  ``capped`` is True iff the seed search hit
    its ``max_seed_calls`` bound WITHOUT finding a crash -- so [] is a budget floor, not a proof that no
    crashing subset exists (reported, never silent); "exhausted" is the distinct proof-of-absence
    within the (max_remove, max_build) bound."""

    recipe: list
    suppressors: list
    seed: list | None
    strategy: str
    n_calls: int
    capped: bool
    validated: bool        # REQUIRED (no default): fail-closed -- an unset validated must never credit a
    #                        reproduction, so external construction cannot accidentally pass it True

    @property
    def reproduced(self) -> bool:
        # a reproduction REQUIRES the converged recipe to pass raw final-validation -- this is what makes
        # "reproduced => the recipe genuinely crashes the raw oracle" hold even under a lying cache.
        # ``is True`` keeps the property a STRICT bool (honours the -> bool hint) even if an external
        # constructor passes a non-bool validated; internally validated is always a strict bool.
        return bool(self.recipe) and self.validated is True

    @property
    def size(self) -> int | None:
        return len(self.recipe) if self.reproduced else None


def _seed_candidates(elements, *, max_remove, max_build, most_recent_first):
    """Yield (strategy, candidate_subset) seeds CHEAPEST-COST-FIRST, deduplicated.

    For each cardinality k = 1, 2, ... we emit TEAR-DOWN(k) (remove k of n -> complement) before
    BUILD-UP(k) (choose k of n).  Both tiers cost C(n, k), so ascending k is ascending cost; tear-down
    leads because, once the maximal element has failed, a suppressor is the likely cause and removing it
    is the targeted move.  ``most_recent_first`` mirrors AirBugCatcher's locality heuristic (packets
    closer to the crash first); it changes only WHICH equal-cost seed is found first, never correctness.
    """
    n = len(elements)
    full = set(elements)
    order = list(elements)[::-1] if most_recent_first else list(elements)
    seen: set[frozenset] = set()
    for k in range(1, max(max_remove, max_build) + 1):
        tiers = []
        if k <= max_remove:
            tiers.append(("tear-down", True))   # candidate = full - comb
        if k <= max_build and k < n:            # build-up of size n == full (already tested) -> skip
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
    """Find a crashing seed when the maximal element does NOT crash (Mode 1).

    Returns ``(seed, strategy, calls, capped)``.  ``seed`` is the first candidate ``raw_test`` accepts
    (None if none within budget); ``capped`` is True iff the bound was hit before a crash was found.
    Uses ONLY ``raw_test`` -- it probes the non-monotone transitions a monotone cache mis-answers."""
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
    """Re-add each excluded element to ``recipe`` and re-test on the RAW oracle.

    Returns ``(suppressors, calls)``: an excluded ``e`` is a CONFIRMED suppressor iff ``recipe ∪ {e}``
    does NOT crash (its presence undoes the crash -- Zeller's undoing change).  Single re-addition only;
    a strictly-pairwise suppressor (neither element alone suppresses) is out of scope and disclosed."""
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
    """Non-monotone-robust 1-minimisation: seed-find -> ddmin-in-seed -> undoing-change verify.

    A drop-in around ``ddmin_search`` that survives non-monotone suppressors.  ``test`` answers the crash
    query (may be cache-accelerated -- used only for the monotone in-seed ddmin).  ``raw_test`` answers
    the same query WITHOUT a monotone cache (used for the maximal check, the seed search, the
    verification, AND the Phase-4 final-validation -- the non-monotone-sensitive probes); defaults to
    ``test``.  That default is correct ONLY when ``test`` is uncached: if ``test`` is CACHE-BACKED you
    MUST pass an uncached ``raw_test``, else Phase-4 validates the recipe against the SAME lying cache --
    a SILENT false credit.  (The pipeline always passes an explicit uncached/SPRT raw_test.)

    ``identity_check`` (optional) is the Mode-2 CAUSE-SWAP guard: a predicate that returns True iff the
    recipe reproduces the TARGET crash's IDENTITY (not merely SOME crash).  ``raw_test`` answers "does this
    crash?"; on a MULTI-cause target a recipe can converge onto a DIFFERENT crash present in the window and
    pass ``raw_test`` -- a wrong-bug credit (a correctness failure distinct from a non-crashing false
    credit).  When supplied, the converged recipe must ALSO pass ``identity_check`` (on the REAL crash
    artifact, channel-off) to be ``validated``.  It can only DEMOTE a reproduction (under-credit), never
    promote one, so it is fail-closed and cannot raise false credit.  ``None`` (the default, and correct for
    a single-cause oracle whose ``raw_test`` is already target-specific) leaves behaviour unchanged.

    ``verify`` runs the undoing-change check ONLY when seed-finding actually fired (``strategy !=
    "full"``) -- i.e. only when a suppressor was demonstrably in play -- so the monotone majority pays
    NO verification overhead (and, in the single-cause model, a "full" seed provably contains no
    suppressor, so this loses nothing).  ``verify_always=True`` forces it even on a full seed, for the
    general MULTI-cause Mode-2 case (a suppressor of a DIFFERENT crash that ddmin could strip).  See the
    module docstring for the cache caveat and the bounded-cost / honest-limit disclosures."""
    elements = list(elements)
    if len(set(elements)) != len(elements):       # distinct-elements precondition -- fail LOUD, never
        raise ValueError("robust_minimize requires DISTINCT elements (a window of indices/packets)")
    raw = raw_test if raw_test is not None else test
    n_calls = 0

    # Phase 0: maximal-element monotonicity gate (raw -- it decides whether to seed-find).  A one-probe
    # check: if the maximal element already fails, the suppressor-free majority needs no robustness
    # machinery (cf. PMA, EASE 2025, which instead treats monotonicity as a measured confidence).
    n_calls += 1
    if raw(elements):
        seed, strategy, capped = elements, "full", False
    else:
        # Phase 1: the maximal element does not crash -> SEED-FIND via bounded complement/superset probing.
        seed, strategy, sc, capped = find_seed(elements, raw, max_remove=max_remove, max_build=max_build,
                                               most_recent_first=most_recent_first,
                                               max_seed_calls=max_seed_calls)
        n_calls += sc
        if seed is None:
            return RobustResult([], [], None, "none" if capped else "exhausted", n_calls, capped,
                                validated=False)

    # Phase 2: ddmin INSIDE the suppressor-free seed (monotone subspace -> cached test is sound here).
    def counted(subset):
        nonlocal n_calls
        n_calls += 1
        return test(subset)

    recipe, _ = ddmin_search(seed, counted)
    recipe = _in_order(recipe, elements)

    # Phase 3: undoing-change verification on the RAW oracle (probes superset transitions).
    # Gated on seed-finding having fired -- the monotone majority (strategy == "full") pays nothing,
    # unless verify_always forces the general multi-cause Mode-2 check.
    suppressors = []
    if verify and recipe and (verify_always or strategy != "full"):
        suppressors, vc = undoing_change_verify(recipe, elements, raw)
        n_calls += vc

    # Phase 4: RAW final-validation of the converged recipe -- the safety net every sibling minimiser
    # has (the pipeline's raw final-validation).  ddmin ran on the possibly-CACHED
    # ``test``; a cache false-YES can let it converge into a non-crashing cone, so confirm on the RAW
    # oracle before crediting a reproduction.  A recipe that fails is KEPT (for diagnosis) but
    # validated=False -> reproduced=False, so a non-crashing recipe is NEVER credited.  (raw_test must
    # be reliable: an SPRT decision in the pipeline, exact for the deterministic standalone tests.)  ``is True``
    # below is IDENTITY-strict on this credit-bearing call: it rejects a truthy non-bool to block a
    # non-bool false credit AND enforce the Callable[...,bool] contract -- ASYMMETRIC with ddmin/seed-find,
    # which gate on truthiness, so a non-bool oracle is fail-closed (UNDER-credited) here, never credited.
    if recipe:
        n_calls += 1
        validated = raw(recipe) is True                        # identity-strict: a truthy non-bool != credit
        # Phase 4b: Mode-2 cause-swap guard (the (c) hook). raw() confirms the recipe CRASHES; identity_check
        # confirms it is the TARGET crash, not a DIFFERENT crash present in the window. Fail-closed (`is True`)
        # and DEMOTE-only -> can never raise false credit; skipped when no recipe / no identity_check.
        if validated and identity_check is not None:
            n_calls += 1
            validated = identity_check(recipe) is True
    else:
        validated = False                                      # empty recipe -> nothing validated (consistent)

    return RobustResult(recipe, suppressors, list(seed), strategy, n_calls, capped, validated=validated)


__all__ = ["robust_minimize", "find_seed", "undoing_change_verify", "RobustResult"]
