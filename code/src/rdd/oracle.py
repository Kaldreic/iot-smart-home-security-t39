"""The interface the minimiser reduces against.

An ``Oracle`` is a noisy reproduction target; the minimiser calls only ``rep_session``. The other
methods serve benchmark scoring (``truth``, ``ground_truth_minimals``) or the optional identity guard
(``identity_truth``). The protocols are type hints only; oracles are duck-typed at runtime.
"""

from __future__ import annotations

from typing import Callable, Protocol

from .sprt import Rep


class Bug(Protocol):
    window: int          # number of candidate elements (packets) the minimiser reduces over
    crash_sig: str       # crash signature, read by the baseline's reproduction loop
    kind: str            # bug-category label, read only by benchmark scoring


class Oracle(Protocol):
    calls: int           # cumulative device reads

    def rep_session(self, bug: Bug, subset, rng, *, decorrelate: bool = False) -> Callable[[], Rep]:
        """Start a fresh over-the-air session and return a callable yielding one noisy ``Rep`` per call.
        With ``decorrelate=False`` the reps within a session may be correlated."""
        ...

    # Optional. The pipeline looks it up with getattr; when absent, the identity guard is skipped.
    def identity_truth(self, bug: Bug, subset) -> bool:
        """Run ``subset`` once with the channel off and report whether the resulting crash artifact
        matches the target bug's identity."""
        ...

    # Benchmark scoring only; the minimiser never calls these.
    def truth(self, bug: Bug, subset) -> bool:
        """Channel-off ground truth: does ``subset`` reproduce the crash?"""
        ...

    def ground_truth_minimals(self, bug: Bug) -> list:
        """All 1-minimal reproducing subsets, for size-gap scoring."""
        ...
