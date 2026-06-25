"""rdd.oracle — the structural interface the tool reduces against.

RDD (and the AirBugCatcher ``baseline``) operate against any object that behaves like an ``Oracle``: a
noisy reproduction target the minimiser can query, plus — for benchmark *scoring* only — the channel-off
ground truth (``truth`` / ``ground_truth_minimals``), which the minimiser itself never consults. Concrete
oracles (synthetic populations, the real Zephyr target) live in the ``emulation`` test-bed; the tool depends
only on this protocol, never on a concrete oracle. Type-hint level only — oracles are duck-typed at runtime.
"""

from __future__ import annotations

from typing import Callable, Protocol

from .sprt import Rep


class Bug(Protocol):
    window: int          # |candidate set| — the elements (packets) the minimiser reduces over
    crash_sig: str       # the bug's crash signature (read by the baseline's reproduction loop)
    kind: str            # bug-category label (read by benchmarks.scoring.score_bug — benchmark scoring only)


class Oracle(Protocol):
    calls: int           # cumulative device reads (the overhead currency RDD and the baseline pay)

    def rep_session(self, bug: Bug, subset, rng, *, decorrelate: bool = False) -> Callable[[], Rep]:
        """A fresh OTA session: returns a callable that yields one (noisy) reproduction verdict per call,
        with within-session reps optionally correlated (``decorrelate=False``)."""
        ...

    # --- OPTIONAL real-artifact hook (getattr-probed by the pipeline; absent -> the cause-swap guard is off) ---
    def identity_truth(self, bug: Bug, subset) -> bool:
        """Mode-2 cause-swap guard for the final-validation: run ``subset`` once channel-off and confirm its
        REAL crash artifact matches the TARGET bug's identity. Absent on an oracle -> the guard is skipped."""
        ...

    # --- benchmark scoring only (the minimiser never sees these) ---
    def truth(self, bug: Bug, subset) -> bool:
        """Channel-off ground truth: does ``subset`` provably reproduce the crash?"""
        ...

    def ground_truth_minimals(self, bug: Bug) -> list:
        """The set of true 1-minimal reproducing subsets (for size-gap scoring)."""
        ...
