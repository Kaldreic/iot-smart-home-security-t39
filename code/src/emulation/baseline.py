"""emulation.baseline — AirBugCatcher's EXACT crash-identity matcher (is_same_crash_id), shared device infra.

The deterministic stack-bucket crash key the baseline arm keys on: the top-K address-normalised frame symbols
(the crash bucket), or the assert site when the report has no stack. Brittle to backtrace truncation/garble --
the false-negative the tool's fuzzy L2/L3 fixes. Shared device/identity infra: reused by the device oracles'
baseline exact-id (emulation.multibug) and the synthetic suite (benchmarks.synthetic), and exercised by
rdd.tests. The AirBugCatcher MINIMISER that uses it as its head-to-head arm lives in benchmarks.baseline."""

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
    """AirBugCatcher's EXACT is_same_crash_id: top-K address-normalized frame symbols (the crash bucket),
    or the assert site when the report has no stack. Exactly what a stack-hash dedup keys on. Brittle to
    backtrace truncation/garble -- the false-negative the tool's fuzzy L2/L3 fixes."""
    norm = tuple(re.sub(r"\+0x[0-9a-fA-F]+$", "", f) for f in obs.stack[:k])
    if norm:
        return ("stack", obs.fault, norm)
    return ("site", obs.fault, getattr(obs, "site", None) or _site_from_log(obs.log_lines))
