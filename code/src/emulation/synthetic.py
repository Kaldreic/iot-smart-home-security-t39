"""emulation.synthetic — the mega-scale synthetic Zephyr-anchored target as a hardware-free oracle.

The DEVICE side of the statistical-power benchmark: a synthetic controller fault, real-anchored (crash
dumps composed from the REAL Zephyr controller symbol space POOL/FILES/FAULTS), driven through the locked
L1 channel + the dump-variation model. ``which_crash`` is the channel-off truth (crash iff the minimal
subset is present AND no suppressor is). The identity matcher (the exact-id baseline or the deterministic
L2/L3 rule) is INJECTED by the benchmark runner, so the arms run verbatim. The benchmark
(``benchmarks.synthetic``) generates the heterogeneous bug POPULATION and composes the per-population dump
model (``base_dump``) + per-bug channel (``sev_channel``) from these device primitives. Replace this module
with real hardware (a real radio + target device) and the RDD tool is unchanged (the benchmark re-wires its oracle)."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from emulation.channel import GEChannelParams, L1Channel, OUT2REP, Outcome
from emulation.dump import BaseDump, DumpModel, Frame
from rdd.sprt import Rep

# Zephyr controller symbols — MOST verbatim from subsys/bluetooth/controller/ll_sw/ull_llcp_*.c +
# ull_conn.c (grepped); a few are paraphrased in the same naming style. They are identity tokens only
# (the same set for both arms), so the handful of non-verbatim names does not affect any score.
POOL = ["cu_ntf", "cu_update_conn_parameters", "cu_prepare_update_ind", "cu_check_conn_parameters",
        "rp_cu_check_instant", "rp_cu_st_wait_instant", "rp_cu_execute_fsm", "llcp_rp_cu_run",
        "lp_cu_st_wait_instant", "lp_cu_ntf_complete", "lp_cu_execute_fsm", "llcp_lp_cu_run",
        "ull_conn_update_parameters", "ull_cp_run", "event_prepare", "lr_act_run", "lr_st_active",
        "rr_act_run", "rr_st_active", "llcp_lr_run", "llcp_rr_run", "cc_ntf_established",
        "cc_prepare_cis_ind", "enc_setup_lll", "encode_enc_req", "feature_filter", "dle_remote_valid",
        "decode_conn_param_req_rsp_common", "force_md_cnt_calc", "pu_check_update_ind", "phy_rsp_send",
        "ull_llcp_init", "llcp_tx_alloc", "ull_cp_priv_pdu_decode", "cp_set_state", "proc_ctx_release",
        "lp_enc_st_wait_rx", "rp_enc_state_machine", "llcp_lp_enc_run", "lp_pu_tx", "rp_pu_check_instant",
        "ull_cp_cc_offset_calc", "cis_offset_get", "chm_update_check", "lp_chmu_st_wait_instant"]
FILES = ["ull_llcp_conn_upd.c", "ull_llcp_cc.c", "ull_llcp_enc.c", "ull_llcp_phy.c",
         "ull_llcp_common.c", "ull_llcp_local.c", "ull_llcp_remote.c", "ull_conn.c", "ull_llcp.c",
         "ull_llcp_chmu.c"]
FAULTS = ["SIGFPE", "ASSERTION FAIL", "SEGV"]
_BASE = GEChannelParams()


@dataclass(frozen=True)
class SynthBug:
    bid: str
    window: int
    minimal: frozenset
    suppressors: tuple
    distance: str           # "near" | "mid" | "far" (of the latest trigger from the most-recent slot)
    shape: str              # "stack" | "deep" | "short" | "site"
    fault: str
    site_fn: str
    site_file: str
    sev: float              # per-bug channel-severity multiplier on the L1 false-negative
    k: int
    crash_sig: str = ""
    kind: str = "crash"


def base_dump(bug: SynthBug) -> BaseDump:
    """The real-anchored base crash dump this synthetic target emits for ``bug`` (the benchmark composes a
    per-population DumpModel from these). Deterministic in ``bug.bid`` (needs PYTHONHASHSEED=0 to repeat)."""
    rng = random.Random(hash(bug.bid) & 0xFFFFFFFF)
    if bug.shape == "site":
        line = rng.randint(120, 880)
        msg = f"{bug.fault} [{bug.site_fn}] @ /work/zephyr/.../{bug.site_file}:{line}"
        return BaseDump(bug.bid, f"{bug.fault} [{bug.site_fn}]", f"{bug.site_file}:{line}", (), (msg, msg))
    depth = {"deep": 14, "stack": 9, "short": 3}[bug.shape]
    frames = [Frame(bug.site_fn, f"0x{rng.randint(0, 0xff):x}", "testbinary")]
    for _ in range(depth - 1):
        fn = rng.choice(POOL + [None, None])
        frames.append(Frame(fn, f"0x{rng.randint(0, 0x20000):x}", "testbinary"))
    return BaseDump(bug.bid, bug.fault, None, tuple(frames), (f"=== CRASH sig={bug.fault} ===",))


def which_crash(bug: SynthBug, subset) -> bool:
    s = frozenset(subset)
    return bug.minimal <= s and not any(p in s for p in bug.suppressors)


def sev_channel(sev: float) -> GEChannelParams:
    """The device's per-bug L1 channel for a severity multiplier (scales the OTA false-negative rates)."""
    cl = lambda x: float(min(0.95, max(0.0, x)))               # noqa: E731
    return replace(_BASE, p_fn_good=cl(_BASE.p_fn_good * sev), p_fn_bad=cl(_BASE.p_fn_bad * sev))


@dataclass
class LargeOracle:
    """The synthetic target oracle; the identity matcher is INJECTED so the arms run verbatim."""
    identity: object        # (bug, obs) -> bool: the eval's matcher (exact-id baseline or the L2/L3 rule)
    model: DumpModel
    params: GEChannelParams
    calls: int = 0

    def truth(self, bug, subset) -> bool:
        return which_crash(bug, subset)

    def rep_session(self, bug, subset, rng, *, decorrelate: bool = False):
        params = replace(self.params, dev_settle=1.0, reset=1.0) if decorrelate else self.params
        ch = L1Channel(params, rng)
        crashes = which_crash(bug, subset)

        def rep():
            self.calls += 1
            out = ch.step(crashes)
            if out is not Outcome.REPRODUCED:
                return OUT2REP[out]
            obs = self.model.emit(bug.bid, rng)
            return Rep.YES if self.identity(bug, obs) else Rep.NO
        return rep

    def ground_truth_minimals(self, bug):
        return [bug.minimal]
