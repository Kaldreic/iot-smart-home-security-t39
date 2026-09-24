"""benchmarks.live — the RDD tool as shipped, on a live reproduction campaign against the real Zephyr
controller binary.

The device (the live-binary oracle, the subprocess driver and the per-bug harness paths, windows and truth)
lives in ``emulation.live``; this module captures the real dump live, builds the tool's live L3 identity,
injects it into the device oracle and runs the campaign. Live: the binary's exit code is the crash oracle
(one run per probe), the dump is parsed from its stderr, and every L2 escalation is a live open-model
judgment (``rdd.LiveL2L3Identity``, memoised per distinct dump pair). Modelled: the OTA channel and the
UART/log report noise, as in ``benchmarks.real``. A usage validation, not a controlled comparison: no
baseline arm and no coherence gate, since a live model and a live binary are not bit-reproducible.

  python -m benchmarks.live --bug A --seeds 5 --model llama3.1:8b   # needs the built target + Ollama
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from benchmarks import scoring
from benchmarks.identity_cache import agg as _agg  # noqa: F401  (shared aggregator; re-exported for tests)
from emulation.channel import GEChannelParams
from emulation.dump import DumpModel, DumpParams, parse_base_dump
from emulation.live import (LiveBinaryOracle, _BINARIES, _Bug, _CRASH_RC,  # noqa: F401  (re-exported)
                            _TRUE_MIN, _WINDOW, run_binary)
from rdd.identity import LiveL2L3Identity


def build_live_campaign(bug: str, *, binary=None, band: float = 0.05, model: str = "llama3.1:8b",
                        host=None, params: GEChannelParams | None = None, dump_params: DumpParams | None = None,
                        memo: dict | None = None, judge=None, timeout: float = 10.0):
    """Capture the real dump live from the true-minimal crashing input, then build the live L3 identity (L2 +
    memoised ``judge_ollama``) and the live-binary oracle. Returns (oracle, identity). ``binary`` defaults to
    the bug's harness (``_BINARIES[bug]``); ``judge`` overrides the L3 backend, for testing."""
    binary = Path(binary) if binary is not None else _BINARIES[bug]
    if not binary.exists():
        raise FileNotFoundError(f"target binary not found: {binary} — build it via "
                                "src/emulation/zephyr-targets/scripts/build-multibug.sh")
    crash_rc = _CRASH_RC[bug]
    crashed, text = run_binary(binary, bug, _TRUE_MIN[bug], crash_rc, timeout)
    if not crashed:
        raise RuntimeError(f"true-minimal {sorted(_TRUE_MIN[bug])} did not crash bug {bug} "
                           f"(exit != {crash_rc}) — binary/build mismatch")
    dmodel = DumpModel(base={bug: parse_base_dump(text, bug)}, params=dump_params or DumpParams())
    identity = LiveL2L3Identity({bug: dmodel.clean_obs(bug)}, band=band, model=model, host=host,
                                memo={} if memo is None else memo, judge=judge)
    oracle = LiveBinaryOracle(binary, bug, identity, dmodel, params=params or GEChannelParams(),
                              crash_rc=crash_rc, timeout=timeout)
    return oracle, identity


def run_live(bug: str, seeds: int = 5, *, decorrelate: bool = True, **kw):
    """Run the tool over ``seeds`` live campaigns on the real binary. The L3 memo is shared across seeds (each
    distinct dump pair is judged once). Returns (rows, oracle, identity)."""
    oracle, identity = build_live_campaign(bug, **kw)
    bug_obj = _Bug(bug=bug, window=_WINDOW[bug], crash_sig=f"bug-{bug}")
    rows = []
    for s in range(seeds):
        oracle.calls = 0
        r = dict(scoring.run_tool_campaign(oracle, [bug_obj], random.Random(s), decorrelate=decorrelate)[0])
        r["reads"] = oracle.calls
        rows.append(r)
    return rows, oracle, identity


def main() -> int:
    ap = argparse.ArgumentParser(prog="benchmarks.live",
                                 description="GENUINE off-the-shelf run: the shipped tool on the REAL binary + LIVE L3")
    ap.add_argument("--bug", default="A", choices=list(_WINDOW))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=None)
    ap.add_argument("--binary", default=None, help="override the per-bug harness binary (default: _BINARIES[bug])")
    a = ap.parse_args()
    print(f"=== GENUINE off-the-shelf run — bug {a.bug}, {a.seeds} seeds, LIVE binary + LIVE L3 ({a.model}) ===")
    rows, oracle, identity = run_live(a.bug, a.seeds, binary=a.binary, model=a.model, host=a.host)
    agg = _agg(rows)
    print(f"  genuine={agg['genuine']:.3f}  false_credit={agg['false_credit']:.3f}  "
          f"size_gap_genuine={agg['size_gap_genuine']:.3f}  reads/seed={agg['reads']:.1f}")
    print(f"  LIVE binary executions: {oracle.binary_runs}   "
          f"L3: {identity.stats['l3_live']} LIVE judgments / {identity.stats['l3_memo']} memo reuses / "
          f"{identity.stats['l2_decided']} L2-decided")
    print("  LIVE = real-binary crash truth + dump, and the open-model L3 ;  MODELLED = OTA flakiness + report-noise")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
