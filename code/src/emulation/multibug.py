"""emulation.multibug — the real Zephyr controller target as a hardware-free oracle.

Composes the channel, the dump-variation model and the channel-off truth table
into the reproduction oracle the minimisers drive: inject a packet subset,
``which_crash`` gives the binary's channel-off truth, the L1 Gilbert-Elliott
channel decides whether the crash is observed on this OTA attempt, and if it is,
a varied crash dump is emitted. The identity matcher (the baseline's exact-id or
the tool's L2/L3) is injected by the benchmark runner. Replacing this module with
a real radio and device leaves the RDD tool unchanged; the benchmark re-wires its
oracle. Device data (the truth table and the captured base dumps) lives in
emulation/data/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from emulation.baseline import exact_crash_id
from emulation.channel import GEChannelParams, L1Channel, OUT2REP, Outcome
from emulation.dump import DumpModel
from rdd.sprt import Rep

_DATA = Path(__file__).resolve().parent / "data"
LOGS = _DATA / "logs"          # the captured base dumps (device data)

TRUTH = json.loads((_DATA / "truth-multibug.json").read_text(encoding="utf-8"))     # {"A":..,..,"F":..} channel-off truth
WINDOW = {"A": 8, "B": 8, "C": 5, "D": 5, "E": 5, "F": 5}
TRUE_MIN = {"A": [frozenset({7})], "B": [frozenset({7})],           # channel-off exhaustive minimals
            "C": [frozenset({3, 4})], "D": [frozenset({3, 4})],
            "E": [frozenset({3, 4})], "F": [frozenset({3, 4})]}
BUGS = tuple(b for b in TRUTH if b in WINDOW)
MODEL = DumpModel.from_logs(LOGS, bugs=BUGS)              # the real captured base dumps


def which_crash(bug: str, subset) -> str | None:
    return TRUTH[bug][str(sum(1 << i for i in subset))]


@dataclass(frozen=True)
class MBug:
    bug: str
    window: int
    crash_sig: str


def _mbug(b: str) -> MBug:
    return MBug(bug=b, window=WINDOW[b], crash_sig=f"bug-{b}")


def id_exact(target_bug: str, obs) -> bool:                         # baseline: AirBugCatcher exact id
    return exact_crash_id(obs) == exact_crash_id(MODEL.clean_obs(target_bug))


@dataclass
class MultibugOracle:
    """The oracle interface; the identity matcher is injected so the arms run verbatim."""
    identity: object
    params: GEChannelParams = field(default_factory=GEChannelParams)
    calls: int = 0

    def truth(self, bug, subset) -> bool:                          # channel-off, identity-free truth
        return which_crash(bug.bug, subset) == bug.bug

    def rep_session(self, bug, subset, rng, *, decorrelate: bool = False):
        params = replace(self.params, dev_settle=1.0, reset=1.0) if decorrelate else self.params
        ch = L1Channel(params, rng)
        crashes = which_crash(bug.bug, subset) == bug.bug

        def rep():
            self.calls += 1
            out = ch.step(crashes)
            if out is not Outcome.REPRODUCED:                      # OTA: crash not observed this attempt
                return OUT2REP[out]
            obs = MODEL.emit(bug.bug, rng)                         # observed -> a varied report
            return Rep.YES if self.identity(bug.bug, obs) else Rep.NO
        return rep

    def ground_truth_minimals(self, bug):
        return TRUE_MIN[bug.bug]
