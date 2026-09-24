"""The crash-report (dump) VARIATION model.

The signature-space analogue of the L1 channel. The L1 channel models whether a bug FIRES
(YES/NO/INVALID flakiness); this models how its crash REPORT varies *when* it fires. On a real device
the same bug emits a DIFFERENT dump each time — ASLR addresses, a backtrace truncated by a UART/log
buffer, frames lost to a watchdog mid-dump, interleaved log lines, occasionally a severely garbled
report. The bug identity is fixed (the crash SITE is deterministic); only the REPORT varies.

Why it matters: AirBugCatcher's `is_same_crash_id` is an EXACT match, so report variation makes it MISS
same-bug reproductions (false negatives → it stops at max_try). Our L2 (fuzzy: stack-LCS + site) sees
through structural variation; L3 (LLM) handles the severely garbled tail. The BASE dumps are REAL,
captured from the real binary (the committed dump logs ``emulation/data/logs/dump-bug-*.txt``); only the
per-rep VARIATION is modelled — and every variation models a concrete real-device effect (named below).
One disclosed exception: the committed Bug-B log is an abbreviated transcript whose frame lines carry no
bracketed return address, so ``parse_base_dump`` yields a header-only report (no stack) for B and the
variation model has no frames to perturb there (see code/README.md, "Known limitations").

Output: ``rdd.observation.DumpObs`` — field-compatible with the L2 ``CrashObservation``;
``to_crash_observation`` adapts it to the real L2. The ground-truth bug id is carried by the oracle, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from rdd.observation import DumpObs

# ----------------------------------------------------------------- parsed base dump

@dataclass(frozen=True)
class Frame:
    sym: str | None     # resolved symbol (e.g. "ull_conn_update_parameters") or None if address-only
    off: str            # offset within sym/module (e.g. "0xdc"); STABLE across runs of one build
    module: str         # "testbinary" / "libc.so.6" / "linux-gate.so.1"


@dataclass(frozen=True)
class BaseDump:
    bug: str                       # "A".."F" (or a synthetic bNNNN id)
    fault: str                     # coarse fault token ("SIGFPE", "ASSERTION FAIL [ntf]")
    site: str | None               # canonical file:line if the report carries one (asserts do)
    frames: tuple[Frame, ...]      # backtrace, top-first (empty for a site-only assert report)
    header: tuple[str, ...]        # non-frame log lines the report leads with


_FRAME_RE = re.compile(r"^(?P<path>[^()]+)\((?P<inner>[^)]*)\)\s*\[(?P<addr>0x[0-9a-fA-F]+)\]")  # `\s*`: live glibc emits `) [0x..]`, the captured logs `)[0x..]`
_ASSERT_RE = re.compile(r"(?P<fault>ASSERTION FAIL[^@]*?)\s*@\s*(?P<path>\S+):(?P<line>\d+)")
_SIGHDR_RE = re.compile(r"sig=(?P<sig>[A-Z]+)")
# signal-handler scaffolding frames that are an artefact of OUR handler, not the fault path:
_SCAFFOLD = ("__kernel_sigreturn", "linux-gate")


def parse_base_dump(text: str, bug: str) -> BaseDump:
    """Parse a captured real dump (Bug A backtrace OR Bug C assert message) into a BaseDump."""
    lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    fault, site, header, frames = "UNKNOWN", None, [], []
    for ln in lines:
        ma = _ASSERT_RE.search(ln)
        if ma:                                    # Bug C: assert message carries fault + site
            fault = ma.group("fault").strip()
            site = f"{Path(ma.group('path')).name}:{ma.group('line')}"
            header.append(ln)
            continue
        mh = _SIGHDR_RE.search(ln)
        if mh:                                    # Bug A: "=== CRASH sig=SIGFPE ==="
            fault = mh.group("sig")
            header.append(ln)
            continue
        mf = _FRAME_RE.match(ln)
        if mf:
            inner = mf.group("inner")
            module = Path(mf.group("path").strip()).name.split("(")[0]
            if "+" in inner:
                sym_part, off = inner.rsplit("+", 1)
                sym = sym_part or None
            else:
                sym, off = (inner or None), "0x0"
            if sym and any(s in sym for s in _SCAFFOLD):
                continue                          # drop sigreturn/linux-gate scaffolding
            frames.append(Frame(sym=sym, off=off, module=module))
        elif "===" not in ln:
            header.append(ln)
    # drop the leading handler frame(s) before the real fault site (first named controller frame), then
    # CANONICALISE every FOREIGN-module frame's offset to 0x0. Only the testbinary controller frames are
    # build-reproducible; a foreign frame's symbol offset is the running system's libc (e.g.
    # __libc_start_main+0x8e on one glibc vs +0x8c on another), which would otherwise leak into the L3
    # dump-hash and make the frozen-cache replay non-portable across machines. The frame is KEPT (only its
    # offset is zeroed), so the dump-variation model -- which draws one jittered address PER frame -- sees an
    # unchanged frame count and the noise realisation (hence every committed number) is preserved; only the
    # libc-dependent offset text changes. L2 already ignores these (it keys on the top-N controller frames and
    # normalises offsets); this extends the same libc-invariance to the L3 path.
    first_named = next((i for i, f in enumerate(frames) if f.sym and f.module.startswith("testbinary")), 0)
    frames = [f if f.module.startswith("testbinary") else replace(f, off="0x0") for f in frames[first_named:]]
    return BaseDump(bug=bug, fault=fault, site=site, frames=tuple(frames), header=tuple(header))


# ----------------------------------------------------------------- the variation model

@dataclass(frozen=True)
class DumpParams:
    """Each knob models a concrete real-device crash-report effect. Defaults = a moderate operating
    point; sweep them to stress L2/L3. (Probabilities are per-emit.)"""
    p_truncate: float = 0.35      # UART/log-buffer cutoff: drop a tail of the backtrace
    trunc_keep_min: int = 2       # keep at least this many top frames when truncating
    p_lose_top: float = 0.20      # watchdog/handler couldn't unwind the top: drop 1-2 TOP frames
    p_perturb: float = 0.15       # an inlined/tail-called frame appears or vanishes mid-stack
    p_lognoise: float = 0.40      # other subsystems interleave a log line into the report
    p_garble: float = 0.08        # severe: only 1-2 frames survive AND the site token is corrupted
    addr_jitter: bool = True      # ASLR: the absolute [0xADDR] differs every run (offsets stay)


_NOISE = (
    "bt: hci_core: rx buf 0x%x", "bt: conn: peer disconnected (reason 0x13)",
    "os: thread 0x%x: stack usage 0x%x", "net: l2cap: tx queue flushed",
    "bt: smp: pairing failed", "ll: scheduler: slot overrun ticks=0x%x",
)


@dataclass
class DumpModel:
    base: dict[str, BaseDump]                       # bug id -> BaseDump
    params: DumpParams = field(default_factory=DumpParams)

    @classmethod
    def from_logs(cls, logdir, params: DumpParams | None = None, bugs=("A", "C")) -> "DumpModel":
        logdir = Path(logdir)
        base = {b: parse_base_dump((logdir / f"dump-bug-{b.lower()}.txt").read_text(encoding="utf-8"), b)
                for b in bugs}
        return cls(base=base, params=params or DumpParams())

    def clean_obs(self, bug: str) -> "DumpObs":
        """The un-varied base report as a DumpObs (the canonical recorded crash = the match target)."""
        bd = self.base[bug]
        stack = [(f"{f.sym}+{f.off}" if f.sym else f"fn+{f.off}") for f in bd.frames]
        return DumpObs(log_lines=list(bd.header), stack=stack, fault=bd.fault)

    def _addr(self, rng) -> str:
        return f"0x{rng.randrange(0x40000000, 0x70000000):08x}" if self.params.addr_jitter else "0x0"

    def _render_frame(self, f: Frame, rng) -> str:
        inner = (f"{f.sym}+{f.off}" if f.sym else f"+{f.off}")
        return f"/work/build-multibug/{f.module}({inner})[{self._addr(rng)}]"

    def emit(self, bug: str, rng) -> DumpObs:
        """Emit ONE varied report for ``bug`` as a DumpObs."""
        p, bd = self.params, self.base[bug]
        frames = list(bd.frames)

        if frames and rng.random() < p.p_lose_top:          # top frames not unwound
            frames = frames[rng.randint(1, 2):]
        if frames and rng.random() < p.p_perturb:           # inlined/extra frame churn
            i = rng.randrange(len(frames))
            if rng.random() < 0.5 and len(frames) > p.trunc_keep_min:
                del frames[i]
            else:
                frames.insert(i, Frame(sym=None, off=f"0x{rng.randrange(0x10000):x}", module="testbinary"))
        if frames and rng.random() < p.p_truncate:          # buffer cutoff
            keep = rng.randint(p.trunc_keep_min, max(p.trunc_keep_min, len(frames)))
            frames = frames[:keep]

        garbled = rng.random() < p.p_garble
        if garbled:                                         # severe: stack gutted
            frames = frames[:rng.randint(1, 2)]

        # build the L2-shaped observation
        stack = [(f"{f.sym}+{f.off}" if f.sym else f"fn+{f.off}") for f in frames]
        log = list(bd.header)
        if garbled:
            log = [re.sub(r":\d+", ":??", ln) for ln in log]
        log += [self._render_frame(f, rng) for f in frames]
        if rng.random() < p.p_lognoise:                     # interleave unrelated subsystem logs
            n = _NOISE[rng.randrange(len(_NOISE))]
            n = n % tuple(rng.randrange(0x10000) for _ in range(n.count("%x")))
            log.insert(rng.randint(0, len(log)), n)
        fault = bd.fault if not garbled or rng.random() < 0.5 else "FAULT"
        return DumpObs(log_lines=log, stack=stack, fault=fault)
