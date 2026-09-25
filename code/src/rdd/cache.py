"""Monotone-closure cache: the free tier of the two-tier reproduction oracle.

The reproduction predicate is assumed monotone: if a subset reproduces, so does every superset. The
cache keeps the minimal observed reproducers and the maximal observed non-reproducers as antichains
and answers a query only when the closure forces it (superset of a YES, subset of a NO); otherwise it
returns ``None`` and the caller runs the SPRT. This is the monotone-reuse rule of Zeller & Hildebrandt
2002. Two rules keep the answers sound: only trustworthy observations are recorded (a capped or
unhealthy SPRT verdict is not), because a wrong YES would propagate to every superset and never be
re-tested; and the frontiers never hold a YES that is a subset of a NO, so a NO above a confirmed YES
is rejected and a YES below a stored NO evicts it. Neither rule recovers from a wrong but trusted
observation, which is why the minimiser re-tests the converged recipe on the uncached oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


def _as_subset(subset: Iterable[int]) -> frozenset[int]:
    return subset if isinstance(subset, frozenset) else frozenset(subset)


@dataclass
class MonotoneOracleCache:
    """One instance per target bug: the reproduction predicate differs per target, so frontiers must
    not be shared."""

    _yes: list[frozenset[int]] = field(default_factory=list)  # minimal observed reproducers
    _no: list[frozenset[int]] = field(default_factory=list)  # maximal observed non-reproducers
    # _exact only detects a re-measurement of the same point in observe(); answers come from the frontiers.
    _exact: dict[frozenset[int], bool] = field(default_factory=dict)

    def query(self, subset: Iterable[int]) -> bool | None:
        """``True`` or ``False`` when the frontier closure forces the answer, else ``None``."""
        s = _as_subset(subset)
        if any(y <= s for y in self._yes):        # superset of a confirmed reproducer
            return True
        if any(s <= n for n in self._no):         # subset of a confirmed non-reproducer
            return False
        return None

    def observe(self, subset: Iterable[int], reproduced: bool, *, trustworthy: bool = True) -> None:
        """Record a trusted SPRT verdict. An untrustworthy result is ignored, so the caller
        may use it for the current step but the point is re-tested next time. Re-recording the same
        value is a no-op."""
        if not trustworthy:
            return
        s = _as_subset(subset)
        prev = self._exact.get(s)
        if prev is not None and prev == reproduced:
            return
        self._exact[s] = reproduced
        # A flipped re-measurement of the same point is not a cross-point violation: drop the stale entry.
        if prev is not None and prev != reproduced:
            self._yes = [y for y in self._yes if y != s]
            self._no = [n for n in self._no if n != s]
        if reproduced:
            self._observe_yes(s)
        else:
            self._observe_no(s)

    def _observe_yes(self, s: frozenset[int]) -> None:
        # A reproducer below stored NOs evicts them, so the cache never answers NO over a confirmed YES.
        if any(s <= n for n in self._no):
            self._no = [n for n in self._no if not (s <= n)]
        self._insert_minimal(s)

    def _observe_no(self, s: frozenset[int]) -> None:
        # A NO above a confirmed YES would prune the reproducer's cone; never record it.
        if any(y <= s for y in self._yes):
            return
        self._insert_maximal(s)

    def _insert_minimal(self, s: frozenset[int]) -> None:
        if any(y <= s for y in self._yes):        # a smaller YES already dominates s
            return
        self._yes = [y for y in self._yes if not (s <= y)]    # drop the larger YESes
        self._yes.append(s)

    def _insert_maximal(self, s: frozenset[int]) -> None:
        if any(s <= n for n in self._no):         # a larger NO already dominates s
            return
        self._no = [n for n in self._no if not (n <= s)]      # drop the smaller NOs
        self._no.append(s)


__all__ = ["MonotoneOracleCache"]
