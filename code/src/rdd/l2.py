"""L2 -- the deterministic 'same crash as the target?' comparator.

AirBugCatcher decides reproduction with ``is_same_crash_id`` -- a brittle exact/fuzzy
signature match that (1) misses the SAME crash when it logs slightly differently
run-to-run and (2) false-matches DIFFERENT crashes sharing a coarse id. L2 replaces
it with a deterministic comparator grounded in the crash-triage literature, emitting
a CALIBRATED same-crash similarity in [0,1] -- the score gating the L2/L3 identity decision.

DESIGN: the crash IDENTITY is the **stack** and the **crash site**, not log templates.
Drain *wildcards* the discriminative tokens (file:line, addresses), so a template-Jaccard
signal is non-discriminating; and a unique-per-crash fault token is a label leak. So L2 leads
with the recognised crash-dedup signals and treats templates as a weak fallback:

  * crash site (PRIMARY) -- the stable faulting location (file:line, assert id),
    extracted EXPLICITLY by regex *before* templating erases it. Jaccard of site
    tokens. This also rescues the logs-only device: the site is usually in the text.
  * stack similarity (PRIMARY) -- top-N normalized frames compared by longest-common-
    subsequence ratio (ECHO-style call-stack dedup), which -- unlike an exact
    stack-hash -- survives run-to-run tail truncation / reordering. [ECHO'25;
    AFL/Honggfuzz stack-hash; LCS/Levenshtein triage]
  * fault class (COARSE) -- the fault *type* bucket (hardfault/assert/...), shared
    across many crashes, so only a weak prior, never a unique label.
  * log templates (WEAK fallback) -- IDF-weighted Jaccard of drain3 template ids
    [He+ ICWS'17; loghub]; useful mainly when site+stack are absent. Low weight.

L2's HONEST value (adversarially measured) is NARROW and regime-specific, not a
blanket win. It STRICTLY beats the best simple baseline only where robustness pays:
stack TRUNCATION/reordering (LCS > exact hash), CONFUSABLE same-site crashes (the
stack disambiguates what crash-site alone cannot), and LOGS-ONLY (crash-site
discriminates where a stack-hash has nothing). On clean full-info the stack alone is
near-perfect, so L2 merely TIES a stack-hash and a site-only matcher -- the value is
the UNION of robustness gains across regimes, not a within-regime improvement on
clean data. The CONFUSABLE win is CONDITIONAL on a stack being present on BOTH reps:
if one rep lost its dump the stack abstains and the comparison degrades to logs-only
(site-level), where a shared-site confusable cannot be disambiguated -- an
information-theoretic floor (no stack => no call path to tell same-site crashes
apart), mitigated downstream by multi-rep aggregation since other reps carry stacks. Weights are STACK-PRIMARY: the top-N stack is the canonical crash bucket
[AFL/Honggfuzz/ECHO], so it leads (w_stack 0.55); crash-site is the FALLBACK for
absent/truncated stacks (w_site 0.25), NOT co-equal -- equal weights would let a shared
site OVERRIDE a disambiguating stack on confusables (the stack already knew they
differed), so the stack must lead. Fault class (coarse) and
templates (weak, can slightly hurt clean) are down-weighted (0.05 / 0.15). The
threshold is calibrated (Youden's J) and is NOISE-REGIME dependent -- fit it on
deployment-representative noise. Deterministic: drain3 is a deterministic online
parser under a fixed fit order.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

_OFFSET = re.compile(r"\+0x[0-9a-fA-F]+")
_HEXADDR = re.compile(r"0x[0-9a-fA-F]+")
# stable crash-site tokens: a source location file.<ext>:line across common firmware
# languages (C/C++/Rust/Go/asm/py). NOTE: site extraction is LOG-FORMAT-dependent --
# a raw PC-only crash (no symbolized file:line) carries no stable textual site, so L2
# falls back on the stack there; pass ``site_re`` to tune for a different log format.
# captures (file, line) across the colon form (``X.c:42``), the ESP32 assert form
# (``in X.c at line 42``) and the OnePlus/5G form (``X.c line:42``); _sites normalises to "X.c:42".
_SITE = re.compile(r"\b([\w./\\-]+\.(?:c|h|cc|cpp|cxx|hpp|hh|rs|go|s|asm|py))"
                   r"(?::|\s+at\s+line\s+|\s+line:)(\d+)\b", re.IGNORECASE)
# coarse fault class (a bucket, NOT a unique id); canonicalised in _fault_class so
# surface variants (assert/assertion/asserted; hard fault/hardfault) map to one bucket.
_FAULT = re.compile(r"(hard[ _]?fault|stack[ _]?overflow|assert(?:ion|ed|ing)?|watchdog|"
                    r"null[ _]?deref(?:erence)?|bus[ _]?fault|usage[ _]?fault|mem[ _]?fault|"
                    r"kernel panic|panic|oops)", re.IGNORECASE)
_FAULT_CANON = {"nulldereference": "nullderef", "kernelpanic": "panic"}


def normalize_frame(frame: str) -> str:
    """Drop call offsets and absolute addresses; keep the symbol (ECHO-style norm). For an
    UNSYMBOLISED frame -- a raw return address with no symbol, e.g. an ESP32/ARM backtrace PC
    ``0x4002c7bd`` -- normalising to "" would erase the only available identity, so fall back to
    the raw address (the leaf PC then varies across reruns but the caller-chain PCs are stable,
    which is exactly the LCS signal)."""
    r = _HEXADDR.sub("", _OFFSET.sub("", frame)).strip()
    return r or frame.strip()


def lcs_len(a: tuple, b: tuple) -> int:
    """Length of the longest common subsequence of two frame sequences (O(nm))."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[-1]))
        prev = cur
    return prev[-1]


@dataclass
class CrashObservation:
    """What a single wireless rep yields when the device crashes."""

    log_lines: list[str] = field(default_factory=list)  # serial/UART/HCI dump lines
    stack: list[str] = field(default_factory=list)       # backtrace frames, top-first
    fault: str = ""                                       # raw fault line/token (optional)


@dataclass(frozen=True)
class CrashSignature:
    sites: frozenset       # stable crash-site tokens
    top_frames: tuple      # top-N normalized stack frames
    fault_class: str       # coarse fault bucket ("" if none)
    template_ids: frozenset


class L2Comparator:
    def __init__(self, w_site: float = 0.25, w_stack: float = 0.55, w_fault: float = 0.05,
                 w_tmpl: float = 0.15, threshold: float = 0.5, topn: int = 5):
        self.tm = TemplateMiner(config=TemplateMinerConfig())  # explicit defaults (deterministic; silences the drain3.ini lookup warning)
        self.w_site, self.w_stack, self.w_fault, self.w_tmpl = w_site, w_stack, w_fault, w_tmpl
        self.threshold, self.topn = threshold, topn
        self._idf: dict = {}
        self._n_docs = 0

    # -- training: learn the template vocabulary + IDF from a corpus of observations --
    def fit(self, observations) -> "L2Comparator":
        obs_list = list(observations)
        for obs in obs_list:
            for line in obs.log_lines:
                self.tm.add_log_message(line)
        df: dict = {}
        for obs in obs_list:
            for cid in self._template_ids(obs.log_lines):
                df[cid] = df.get(cid, 0) + 1
        self._n_docs = len(obs_list)
        self._idf = {cid: math.log((self._n_docs + 1) / (c + 0.5)) for cid, c in df.items()}
        return self

    def _template_ids(self, lines) -> frozenset:
        ids = set()
        for line in lines:
            m = self.tm.match(line)
            if m is not None:
                ids.add(m.cluster_id)
        return frozenset(ids)

    @staticmethod
    def _sites(lines) -> frozenset:
        out = set()
        for ln in lines:
            for f, line in _SITE.findall(ln):       # (file, line) across :/at line/line: forms
                out.add(f"{f}:{line}")
        return frozenset(out)

    @staticmethod
    def _fault_class(lines, fault) -> str:
        for text in [fault, *lines]:
            m = _FAULT.search(text or "")
            if m:
                raw = re.sub(r"[ _]", "", m.group(1).lower())
                if raw.startswith("assert"):
                    return "assert"            # assert/assertion/asserted -> one bucket
                return _FAULT_CANON.get(raw, raw)
        return ""

    def signature(self, obs: CrashObservation) -> CrashSignature:
        return CrashSignature(
            self._sites(obs.log_lines),
            tuple(normalize_frame(f) for f in obs.stack[:self.topn]),
            self._fault_class(obs.log_lines, obs.fault),
            self._template_ids(obs.log_lines))

    # ---- per-signal similarities (None => signal absent on both -> abstain) ----
    @staticmethod
    def _jaccard(a: frozenset, b: frozenset):
        if not a and not b:
            return None
        return len(a & b) / len(a | b) if (a | b) else None

    @staticmethod
    def _stack_sim(a: tuple, b: tuple):
        # abstain if EITHER side lacks a stack: a missing dump is missing DATA (fall back
        # on site/fault), not evidence of a different crash -- scoring it 0.0 would let
        # the stack-primary weight wrongly veto a same-crash pair where one rep lost its
        # dump. DUAL COST (disclosed): an abstaining stack also cannot VETO a different-
        # crash same-site confusable, so a mixed (one-dump-missing) confusable degrades to
        # logs-only and may false-match -- an information-theoretic floor, not a bug.
        if not a or not b:
            return None
        denom = max(len(a), len(b))
        return lcs_len(a, b) / denom if denom else None

    @staticmethod
    def _fault_sim(a: str, b: str):
        if not a and not b:
            return None
        return 1.0 if a == b else 0.0

    def _tmpl_sim(self, a: frozenset, b: frozenset):
        if not a and not b:
            return None
        union = a | b
        if not union:
            return None
        w = (lambda c: self._idf.get(c, 1.0)) if self._idf else (lambda c: 1.0)
        uw = sum(w(c) for c in union)
        return sum(w(c) for c in (a & b)) / uw if uw else None

    def similarity(self, a: CrashSignature, b: CrashSignature) -> float:
        """Weighted combine over AVAILABLE signals (weights renormalised by presence)."""
        parts = [(self.w_site, self._jaccard(a.sites, b.sites)),
                 (self.w_stack, self._stack_sim(a.top_frames, b.top_frames)),
                 (self.w_fault, self._fault_sim(a.fault_class, b.fault_class)),
                 (self.w_tmpl, self._tmpl_sim(a.template_ids, b.template_ids))]
        num = sum(w * s for w, s in parts if s is not None)
        den = sum(w for w, s in parts if s is not None)
        return num / den if den else 0.0

    def same_crash(self, obs: CrashObservation, target: CrashSignature):
        score = self.similarity(self.signature(obs), target)
        return (score >= self.threshold, score)
