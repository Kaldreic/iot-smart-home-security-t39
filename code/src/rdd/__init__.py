"""RDD — Robust Delta-Debugging.

A non-monotone-robust bug-reproduction minimiser for noisy wireless-IoT fuzzing oracles. Given a flaky
reproduction target and a reference crash, RDD recovers a minimal reproducing packet subset (PoC) that
classical delta-debugging (the AirBugCatcher ``baseline``) misses, at far lower false-credit — by wrapping
the reduction in statistical-testing-in-the-loop:

    channel  — the L1 Gilbert–Elliott OTA-flakiness model (in the ``emulation`` test-bed, not an rdd module)
    sprt     — a truncated SPRT reproduction oracle + monotone result cache
    l2 / l3  — fuzzy L2 + a single open-model LLM judge (L3): crash-identity (is this the *same* bug?)
    minimiser— the robust delta-debugging core: seed-find → ddmin-in-seed → undoing-change verify →
               raw final-validation (non-monotone-/suppressor-robust)
    pipeline — the wired tool: SPRT-trusted probes, in-seed cache, final-validation

``LiveL2L3Identity`` is the off-the-shelf
crash-identity to wire in (L2 + a LIVE, memoised open-model L3). Concrete device oracles live in the
``emulation`` test-bed and the benchmark runners in ``benchmarks``; this package is the self-contained, importable tool.
"""

from __future__ import annotations

from .identity import LiveL2L3Identity
from .minimizer import RobustResult, robust_minimize
from .pipeline import RDDResult, minimize
from .sprt import Rep, SPRTConfig

__all__ = [
    "minimize", "RDDResult",
    "robust_minimize", "RobustResult", "LiveL2L3Identity",
    "SPRTConfig", "Rep",
]
