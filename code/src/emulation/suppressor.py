"""emulation.suppressor — the real non-monotone LL_LENGTH_REQ suppressor target as a HW-free oracle.

crash <=> trigger (bit3) present AND LL_LENGTH_REQ (bit4) absent — a genuine non-monotone real bug (masks
8-15 SIGFPE, 24-31 suppressed). The crash IS bug A's conn-update SIGFPE, so it re-uses bug A's captured dump
(the lengthreq harness installs no SIGFPE handler and prints no backtrace of its own) and bug A's identity (reuses ``emulation.multibug``'s MODEL + MBug); only the non-monotone reachability is
new. The identity matcher (the baseline's exact-id, or the tool's L2/L3) is INJECTED by the benchmark
runner. Device data (the Docker-captured truth table) lives in emulation/data/. Replace this module with a
real radio + device and the RDD tool is unchanged (the benchmark re-wires its oracle)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from emulation.channel import GEChannelParams, L1Channel, OUT2REP, Outcome
from emulation.multibug import MODEL, MBug
from rdd.sprt import Rep

_DATA = Path(__file__).resolve().parent / "data"
# the REAL length_req-suppressor truth, Docker-captured on the vulnerable Zephyr binary (src/emulation/zephyr-targets recipe):
# 5-PDU window, crash iff bit3 (interval=0 trigger) set AND bit4 (LL_LENGTH_REQ) NOT set => non-monotone.
_LR_TRUTH = {int(k): v for k, v in json.loads((_DATA / "truth-lengthreq.json").read_text(encoding="utf-8")).items()}


def lr_which_crash(subset) -> bool:
    return _LR_TRUTH[sum(1 << i for i in subset)]


@dataclass
class LengthReqOracle:
    """The real length_req suppressor: 5-PDU window, crash iff trigger (bit 3) present AND LL_LENGTH_REQ
    (bit 4) absent. The crash IS bug A's conn-update SIGFPE -> emits bug A's real dump + uses bug A's
    identity (same oracle interface as MultibugOracle, so the arms run verbatim)."""

    identity: object
    params: GEChannelParams = field(default_factory=GEChannelParams)
    calls: int = 0

    def truth(self, bug, subset) -> bool:
        return lr_which_crash(subset)

    def rep_session(self, bug, subset, rng, *, decorrelate: bool = False):
        params = replace(self.params, dev_settle=1.0, reset=1.0) if decorrelate else self.params
        ch = L1Channel(params, rng)
        crashes = lr_which_crash(subset)

        def rep():
            self.calls += 1
            out = ch.step(crashes)
            if out is not Outcome.REPRODUCED:
                return OUT2REP[out]
            obs = MODEL.emit("A", rng)                           # the real conn-update crash dump (== bug A)
            return Rep.YES if self.identity("A", obs) else Rep.NO
        return rep

    def ground_truth_minimals(self, bug):
        return [frozenset({3})]                                  # the trigger alone (decoys + length_req removable)


LRBUG = MBug(bug="LR", window=5, crash_sig="bug-LR")
