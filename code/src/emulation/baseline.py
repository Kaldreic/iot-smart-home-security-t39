"""emulation.baseline — AirBugCatcher's exact crash-identity matcher, shared device infrastructure.

``exact_crash_id`` reproduces is_same_crash_id: the crash key is the top-K
address-normalised frame symbols (the crash bucket), or the assert site when the
report carries no stack. It is brittle to backtrace truncation and garble -- the
false negative the tool's fuzzy L2/L3 fixes. The matcher is reused by the device
oracles' baseline exact-id (emulation.multibug) and the synthetic suite
(benchmarks.synthetic), and exercised by rdd.tests. The AirBugCatcher minimiser
that uses it as its head-to-head arm lives in benchmarks.baseline.
"""

from __future__ import annotations

import re
from pathlib import Path

from rdd.observation import DumpObs


def _site_from_log(log_lines):
    for ln in log_lines:
        m = re.search(r"(\S+\.c):(\S+)", ln)            # file.c:NNN  (or :?? when garbled)
        if m:
            return f"{Path(m.group(1)).name}:{m.group(2)}"
    return None


def exact_crash_id(obs: DumpObs, k: int = 5):
    """The exact is_same_crash_id key: the top-K address-normalised frame symbols, or the assert site when
    the report has no stack -- what a stack-hash dedup keys on."""
    norm = tuple(re.sub(r"\+0x[0-9a-fA-F]+$", "", f) for f in obs.stack[:k])
    if norm:
        return ("stack", obs.fault, norm)
    return ("site", obs.fault, getattr(obs, "site", None) or _site_from_log(obs.log_lines))
