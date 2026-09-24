"""emulation.live — the real Zephyr controller binary as a live, hardware-free oracle.

Drives the host-native ``unit_testing`` (ztest) ELF via ``subprocess``: a
packet-window subset is injected as a HARNESS_SUBSET bitmask, the binary's exit
code is the crash truth (captured live per probe), and on a crash its stderr is
the real backtrace, parsed via ``emulation.dump.parse_base_dump``. The OTA
conditions the host build lacks -- radio flakiness (the L1 channel) and UART/log
report noise (the dump variation) -- are modelled. The identity matcher (the
tool's live-L3 cascade, or the baseline's exact-id in B1/B3) is injected by the benchmark runner, so the tool runs
verbatim. The harness binaries live under the gitignored ``upstream/zephyr-cve/``
build area. Replacing this module with a real radio and device leaves the RDD
tool unchanged; the benchmark re-wires its oracle.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from emulation.channel import GEChannelParams, L1Channel, Outcome
from emulation.dump import DumpModel
from emulation.multibug import TRUE_MIN as _MB_TRUE_MIN, WINDOW as _WINDOW  # noqa: F401  (_WINDOW is re-exported: benchmarks read live._WINDOW)
from rdd.sprt import Rep

_HERE = Path(__file__).resolve().parent
# upstream/ is the gitignored third-party area at the code area root (code/), a sibling
# of src/ -- so from this module (code/src/emulation/live.py) it is two levels up, not one.
_UP = Path(os.environ.get("HARNESS_WS", _HERE.parent.parent / "upstream" / "zephyr-cve"))   # as the build scripts
_BINARIES = {"A": _UP / "build-multibug" / "testbinary",   # the 6 real bugs live in 5 harness binaries:
             "B": _UP / "build-cis" / "testbinary",        #   A,C share build-multibug; B is the CIS harness,
             "C": _UP / "build-multibug" / "testbinary",   #   D the PHY harness, E the data-length harness,
             "D": _UP / "build-phy" / "testbinary",        #   F the cis-create-established harness. (Routing
             "E": _UP / "build-dle" / "testbinary",        #    them all to build-multibug silently breaks
             "F": _UP / "build-cisc" / "testbinary"}       #    B, D, E and F.)
_OUT2REP = {Outcome.NOT_REPRODUCED: Rep.NO, Outcome.INVALID: Rep.INVALID}
_TRUE_MIN = {b: v[0] for b, v in _MB_TRUE_MIN.items()}   # multibug's [frozenset] list-form -> a bare frozenset per bug
_CRASH_RC = {"A": 136, "B": 136, "C": 255, "D": 255, "E": 255, "F": 255}    # exit code when this bug fires
#                                                          (empirically: the SIGFPE handler exits 136; assert 255)


@dataclass(frozen=True)
class _Bug:
    bug: str
    window: int
    crash_sig: str = ""


def run_binary(binary, bug: str, subset, crash_rc: int, timeout: float = 10.0):
    """Inject ``subset`` (PDU-window indices, as a HARNESS_SUBSET bitmask) into the binary and return
    ``(crashed, dump_text)``: crashed iff the exit code is this bug's crash code, dump_text its output. A
    binary that hangs past ``timeout`` is killed and counted as not crashed (a hang is not the target crash,
    the same crash-detection timeout AirBugCatcher's PoC runner applies), never raised as an exception."""
    mask = sum(1 << i for i in subset)
    try:
        r = subprocess.run([str(binary)], env={**os.environ, "HARNESS_BUG": bug, "HARNESS_SUBSET": str(mask)},
                           capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT: {binary} produced no exit within {timeout}s (HARNESS_BUG={bug}, HARNESS_SUBSET={mask})"
    text = r.stderr.decode(errors="replace") + r.stdout.decode(errors="replace")
    return r.returncode == crash_rc, text


class LiveBinaryOracle:
    """Drives the binary live: a subset runs it, the exit code is the crash truth, and on a crash its stderr is
    the real backtrace. The OTA flakiness (L1 channel) and report noise (dump variation) are modelled.
    ``identity`` is the live-L3 cascade (``rdd.LiveL2L3Identity``); ``dmodel`` varies the live-captured dump."""

    def __init__(self, binary, bug: str, identity, dmodel: DumpModel, *,
                 params: GEChannelParams | None = None, crash_rc: int | None = None, timeout: float = 10.0):
        self.binary = Path(binary)
        self.bug = bug
        self.identity = identity
        self.model = dmodel
        self.params = params or GEChannelParams()
        self.crash_rc = crash_rc if crash_rc is not None else _CRASH_RC[bug]
        self.timeout = timeout
        self.calls = 0           # device reads this campaign (reset per seed by run_live)
        self.binary_runs = 0     # cumulative live binary executions

    def _run(self, subset):
        self.binary_runs += 1
        return run_binary(self.binary, self.bug, subset, self.crash_rc, self.timeout)

    def truth(self, bug, subset) -> bool:                  # channel-off real-binary truth (live); scoring only
        crashed, _ = self._run(subset)
        return crashed

    def rep_session(self, bug, subset, rng, *, decorrelate: bool = False):
        crashed, _ = self._run(subset)                     # one live binary run per subset (truth is determinate;
        params = replace(self.params, dev_settle=1.0, reset=1.0) if decorrelate else self.params  # the channel
        ch = L1Channel(params, rng)                        # supplies the per-attempt OTA flakiness)

        def rep():
            self.calls += 1
            out = ch.step(crashed)                         # modelled OTA flakiness: is the crash observed?
            if out is not Outcome.REPRODUCED:
                return _OUT2REP[out]
            obs = self.model.emit(bug.bug, rng)            # observed -> a noisy version of the live real dump
            return Rep.YES if self.identity(bug.bug, obs) else Rep.NO   # L2 -> on the residual band, live L3
        return rep

    def ground_truth_minimals(self, bug):
        return [_TRUE_MIN[bug.bug]]
