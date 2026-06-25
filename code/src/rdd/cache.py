"""Opportunistic oracle: the monotone-closure cache (tier 1).

This is the cheap, deterministic, hardware-free path of the two-tier oracle. It
answers a ddmin reproduction query --- "does this packet subset still reproduce
the target bug?" --- *only* when the answer is forced by the monotone closure of
what has already been observed, and defers (returns ``None``) otherwise so the
caller can escalate to the accurate path.

Formal model
------------
The reproduction predicate ``R(S) = "subset S reproduces the target"`` is assumed
*monotone increasing* over the subset lattice: adding packets to a reproducer
keeps it a reproducer (``R(S) and S ⊆ T  ⇒  R(T)``). Under that assumption the
observed points force answers on a whole region: superset-of-YES ⇒ True,
subset-of-NO ⇒ False, else unknown. We keep the two frontiers as antichains
(minimal observed YES / maximal observed NO) plus an exact memo --- the
S-set/G-set boundary of a version space over a monotone Boolean function
(Mitchell 1982; the monotone-reuse rule of cached delta debugging).

Two safeguards keep the cached answers sound:

* **Monotone-consistent answers.** A directly-observed memo can disagree with the
  frontier closure (a noisy or non-monotone observation). Answers therefore come
  purely from the frontiers, which maintain the invariant "no YES ⊆ any NO" by
  evicting a contradicted frontier element on the next trustworthy observation
  --- so the cache never answers S→False with a subset→True.
* **Trust-gating.** A wrong-but-trusted YES propagates upward forever and is never
  re-escalated, so an untrustworthy read (YES *or* NO --- e.g. a split multi-trial
  vote) is **not recorded at all**: the caller uses it for the current ddmin step,
  but it is not cached, so it re-escalates next time.

Neither safeguard makes a wrong-but-trusted observation recoverable on its own (a
covered wrong fact answers forever), so final-validation of the converged recipe
--- a single accurate re-test --- is the essential safety net. The two error modes
are asymmetric: a false-NO usually only bloats the recipe (or, on the full window,
makes ddmin return ``[]``), whereas a false-YES lets ddmin shrink into a
non-reproducing cone and return a recipe that does not reproduce --- a silent
correctness failure, the more severe harm. Both directions are trust-gated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


def _as_subset(subset: Iterable[int]) -> frozenset[int]:
    return subset if isinstance(subset, frozenset) else frozenset(subset)


@dataclass
class MonotoneOracleCache:
    """Tier-1 oracle answering reproduction queries from the monotone closure.

    One instance per crash-group target: ``R`` is a *different* monotone function
    for each target, so frontiers must not be shared across targets.
    """

    _yes: list[frozenset[int]] = field(default_factory=list)  # minimal YES antichain
    _no: list[frozenset[int]] = field(default_factory=list)  # maximal NO antichain
    # _exact is kept ONLY for same-point-flip detection in observe(); it is never
    # an answer source. Answers come purely from the frontiers, which maintain
    # "no YES ⊆ any NO" and are therefore monotone-consistent by construction.
    _exact: dict[frozenset[int], bool] = field(default_factory=dict)

    def query(self, subset: Iterable[int]) -> bool | None:
        """Return ``True``/``False`` if forced by the frontier closure, else
        ``None``. Answers are monotone-consistent (the frontiers never hold a
        YES ⊆ NO pair)."""
        s = _as_subset(subset)
        if any(y <= s for y in self._yes):        # s ⊇ a confirmed reproducer
            return True
        if any(s <= n for n in self._no):         # s ⊆ a confirmed non-reproducer
            return False
        return None

    def observe(self, subset: Iterable[int], reproduced: bool, *, trustworthy: bool = True) -> None:
        """Record an accurate-path (or campaign-seed) result.

        Only *trustworthy* results are recorded; an untrustworthy read is a no-op
        (used for the current ddmin step by the caller but not cached, so it
        re-escalates next time). An identical re-measurement is idempotent.
        """
        if not trustworthy:
            return
        s = _as_subset(subset)
        prev = self._exact.get(s)
        if prev is not None and prev == reproduced:
            return
        self._exact[s] = reproduced
        # A same-point re-measurement flip is not a cross-point monotonicity
        # violation: drop the stale frontier entry first.
        if prev is not None and prev != reproduced:
            self._yes = [y for y in self._yes if y != s]
            self._no = [n for n in self._no if n != s]
        if reproduced:
            self._observe_yes(s)
        else:
            self._observe_no(s)

    def _observe_yes(self, s: frozenset[int]) -> None:
        # s reproduces yet sits under frontier NO(s): self-heal by evicting them,
        # so the cache never answers NO over a confirmed reproducer.
        if any(s <= n for n in self._no):
            self._no = [n for n in self._no if not (s <= n)]
        self._insert_minimal(s)

    def _observe_no(self, s: frozenset[int]) -> None:
        # A NO above a confirmed YES is a real violation; never propagate it (the
        # downward NO direction would prune the reproducer's cone).
        if any(y <= s for y in self._yes):
            return
        self._insert_maximal(s)

    def _insert_minimal(self, s: frozenset[int]) -> None:
        if any(y <= s for y in self._yes):        # a smaller YES already dominates s
            return
        self._yes = [y for y in self._yes if not (s <= y)]    # drop larger YESes
        self._yes.append(s)

    def _insert_maximal(self, s: frozenset[int]) -> None:
        if any(s <= n for n in self._no):         # a larger NO already dominates s
            return
        self._no = [n for n in self._no if not (n <= s)]      # drop smaller NOs
        self._no.append(s)


__all__ = ["MonotoneOracleCache"]
