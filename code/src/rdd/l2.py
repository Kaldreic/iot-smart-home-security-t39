"""L2: a deterministic "same crash as the target?" comparator with a similarity score in [0, 1].

Crash identity is taken from the stack and the crash site, not from log templates, whose
discriminative tokens (file:line, addresses) drain3 wildcards away. Four signals are combined, the
weights renormalised over the signals present: the top-N normalised stack frames by longest-common-
subsequence ratio (0.55), which survives truncation and reordering where an exact stack hash does not;
crash-site tokens extracted by regex before templating (0.25), the fallback for a missing or truncated
stack; a coarse fault class such as hardfault or assert (0.05); and IDF-weighted Jaccard of drain3
template ids (0.15). The stack leads so that a shared site cannot override a stack that already tells
two crashes apart. The threshold depends on the noise regime and should be fitted on representative
noise. Deterministic given a fixed fit order.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

_OFFSET = re.compile(r"\+0x[0-9a-fA-F]+")
_HEXADDR = re.compile(r"0x[0-9a-fA-F]+")
# Crash-site tokens: file.<ext>:line for common firmware languages, in the colon form (``X.c:42``), the
# ESP32 assert form (``in X.c at line 42``) and the ``X.c line:42`` form; _sites normalises all three to
# "X.c:42". A PC-only crash with no symbolised file:line has no textual site, so L2 falls back on the stack.
_SITE = re.compile(r"\b([\w./\\-]+\.(?:c|h|cc|cpp|cxx|hpp|hh|rs|go|s|asm|py))"
                   r"(?::|\s+at\s+line\s+|\s+line:)(\d+)\b", re.IGNORECASE)
# Coarse fault class, a bucket rather than an id; _fault_class folds surface variants
# (assert/assertion/asserted, hard fault/hardfault) into one bucket.
_FAULT = re.compile(r"(hard[ _]?fault|stack[ _]?overflow|assert(?:ion|ed|ing)?|watchdog|"
                    r"null[ _]?deref(?:erence)?|bus[ _]?fault|usage[ _]?fault|mem[ _]?fault|"
                    r"kernel panic|panic|oops)", re.IGNORECASE)
_FAULT_CANON = {"nulldereference": "nullderef", "kernelpanic": "panic"}


def normalize_frame(frame: str) -> str:
    """Drop call offsets and absolute addresses, keeping the symbol. An unsymbolised frame (a bare
    return address) is kept as is, since erasing it would leave no identity at all."""
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
    """What a single rep yields when the device crashes."""

    log_lines: list[str] = field(default_factory=list)  # serial/UART/HCI dump lines
    stack: list[str] = field(default_factory=list)       # backtrace frames, top first
    fault: str = ""                                       # raw fault line or token (optional)


@dataclass(frozen=True)
class CrashSignature:
    sites: frozenset       # crash-site tokens
    top_frames: tuple      # top-N normalised stack frames
    fault_class: str       # coarse fault bucket ("" if none)
    template_ids: frozenset


class L2Comparator:
    def __init__(self, w_site: float = 0.25, w_stack: float = 0.55, w_fault: float = 0.05,
                 w_tmpl: float = 0.15, threshold: float = 0.5, topn: int = 5):
        self.tm = TemplateMiner(config=TemplateMinerConfig())  # explicit config: deterministic, and no drain3.ini lookup warning
        self.w_site, self.w_stack, self.w_fault, self.w_tmpl = w_site, w_stack, w_fault, w_tmpl
        self.threshold, self.topn = threshold, topn
        self._idf: dict = {}
        self._n_docs = 0

    # fit: learn the template vocabulary and IDF weights from a corpus of observations
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
            for f, line in _SITE.findall(ln):
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

    # per-signal similarities; None means the signal is absent and its weight is dropped
    @staticmethod
    def _jaccard(a: frozenset, b: frozenset):
        if not a and not b:
            return None
        return len(a & b) / len(a | b) if (a | b) else None

    @staticmethod
    def _stack_sim(a: tuple, b: tuple):
        # Abstain when either side lacks a stack: a missing dump is missing data, not evidence of a
        # different crash. The cost is that two same-site crashes with one dump missing compare at
        # site level only and may match.
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
        w = (lambda c: self._idf.get(c, 1.0)) if self._idf else (lambda c: 1.0)
        uw = sum(w(c) for c in union)
        return sum(w(c) for c in (a & b)) / uw if uw else None

    def similarity(self, a: CrashSignature, b: CrashSignature) -> float:
        """Weighted combination over the available signals, with the weights renormalised by presence."""
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
