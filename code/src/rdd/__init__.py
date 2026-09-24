"""Robust delta debugging: a bug-reproduction minimiser for noisy wireless-IoT fuzzing oracles.

Given a flaky reproduction target and a reference crash, ``minimize`` recovers a minimal reproducing
packet subset while keeping the chance of crediting a non-reproducing subset small. Modules:

    sprt       truncated sequential probability ratio test over noisy reproduction attempts
    cache      monotone-closure result cache used by ddmin inside the seed
    ddmin      Zeller & Hildebrandt 2002 one-minimisation
    minimizer  seed-finding, ddmin inside the seed, suppressor verification, final validation
    l2, l3     crash identity: a fuzzy comparator and an open-model judge
    identity   ``LiveL2L3Identity``, the L2/L3 cascade with a memoised live judge
    pipeline   ``minimize``, which wires the SPRT oracle and the cache around the minimiser

Device oracles live in the ``emulation`` test-bed and the benchmark runners in ``benchmarks``.
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
