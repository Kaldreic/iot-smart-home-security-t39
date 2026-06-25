"""rdd.identity — the crash-IDENTITY layer: "is this crash dump the SAME bug as the target?"

Two matchers over varied crash dumps; only the matcher differs:

- ``exact_crash_id`` (the AirBugCatcher baseline, ``emulation.baseline``): the top-K address-normalised stack-frame
  bucket (the canonical AFL/Honggfuzz crash key), falling back to the assert site when there is no stack.
  Robust to ASLR addresses, but BRITTLE to backtrace truncation / top-frame loss / frame churn: any of
  those changes the top-K bucket, so the SAME bug reads as a DIFFERENT crash -> a false negative -> the
  baseline stops retrying (max_try) and loses the reproduction.
- ``L2Matcher`` (RDD): the ``L2Comparator`` (stack LCS 0.55 + site 0.25 + fault + drain3 templates), which
  tolerates truncation/reorder/addresses and uses the site as a fallback.

The residual L2 misses (severe garble) are what L3 (``rdd.l3``) adjudicates. (drain3 dependency.)

``LiveL2L3Identity`` is the DEPLOYABLE end of that cascade — the off-the-shelf identity a user runs on a
real campaign: L2 fuzzy match, and on the uncertain band a LIVE open-model L3 judgment (memoized). The
benchmark's reproducible path instead reads a pre-warmed verdict cache; this one fires the model live.
"""

from __future__ import annotations

import json
from pathlib import Path

from .observation import DumpObs
from .l3 import _pair_hash, judge_ollama, render_dump


class L2Matcher:
    """Fuzzy crash identity (RDD) via the L2Comparator."""

    def __init__(self, base_obs: dict[str, DumpObs], threshold: float = 0.5):
        from .l2 import L2Comparator
        self.l2 = L2Comparator(threshold=threshold)
        cobs = {b: o.to_crash_observation() for b, o in base_obs.items()}
        self.l2.fit(list(cobs.values()))
        self.sig = {b: self.l2.signature(c) for b, c in cobs.items()}

    def is_same(self, target_bug: str, obs: DumpObs):
        same, s = self.l2.same_crash(obs.to_crash_observation(), self.sig[target_bug])
        return bool(same), float(s)


class LiveL2L3Identity:
    """The DEPLOYABLE L2->L3 crash-identity a user runs on a real fuzzing campaign. A drop-in identity
    callable -- ``identity(target_bug, obs) -> bool`` -- that the RDD pipeline uses verbatim.

    The FrugalGPT cascade, live: L2 (cheap, fuzzy) decides the confident cases; only the UNCERTAIN band
    (L2 says "different" but with similarity >= ``band``) escalates to a LIVE open-model L3 judgment via
    ``judge_ollama``. Each escalated pair is judged ONCE and MEMOISED (an identical crash pair seen again
    in the campaign is not re-queried). This is exactly the benchmark's in-loop logic, except the miss
    branch fires the model live instead of reading a pre-warmed cache -- so it works off-the-shelf on
    crashes never seen before.

    Soundness mirrors the backend: a connection error to Ollama PROPAGATES (loud -- a broken judge must
    not silently degrade the whole campaign), while a garbled/non-bool model reply yields a conservative
    ``same=False`` (memoised) -- never a false match (``v["same"] is True``). ``stats`` counts L2-decided
    vs live-L3 vs memo-hit reads. ``memo`` may be pre-loaded from / saved to disk to reuse verdicts across
    campaigns (``from_memo_file`` / ``save_memo``)."""

    def __init__(self, base_obs: dict[str, DumpObs], *, band: float = 0.05, model: str = "llama3.1:8b",
                 host: str | None = None, memo: dict | None = None, judge=None, threshold: float = 0.5):
        self.l2 = L2Matcher(base_obs, threshold=threshold)
        self.target_text = {b: render_dump(o) for b, o in base_obs.items()}
        self.band = band
        self.model = model
        self.host = host
        self.memo: dict = memo if memo is not None else {}
        self._judge = judge or judge_ollama
        self.stats = {"l2_decided": 0, "l3_live": 0, "l3_memo": 0}

    def __call__(self, target_bug: str, obs: DumpObs) -> bool:
        same, score = self.l2.is_same(target_bug, obs)
        if same:
            self.stats["l2_decided"] += 1
            return True
        if score < self.band:                                       # confidently different -> trust L2
            self.stats["l2_decided"] += 1
            return False
        h = _pair_hash(self.target_text[target_bug], render_dump(obs))   # uncertain band -> escalate to L3
        if h in self.memo:                                          # `in`, not get()-is-None: an explicit None
            self.stats["l3_memo"] += 1                              # entry is a HIT (-> conservative NO below),
            v = self.memo[h]                                        # not silently re-judged live
        else:
            self.stats["l3_live"] += 1                              # a genuine LIVE model query
            kw = {"model": self.model} if self.host is None else {"model": self.model, "host": self.host}
            v = self._judge(self.target_text[target_bug], render_dump(obs), **kw)
            self.memo[h] = v
        return isinstance(v, dict) and v.get("same") is True        # strict + corrupt-safe: a garbled/foreign
        #                                                             memo entry degrades to NO, never crash/false-credit

    def save_memo(self, path) -> None:
        """Persist the verdict memo so a later campaign can reuse it (and stays reproducible given it)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.memo, indent=1) + "\n")

    @classmethod
    def from_memo_file(cls, base_obs: dict[str, DumpObs], path, **kw) -> "LiveL2L3Identity":
        """Construct with a memo pre-loaded from ``path`` (empty if absent) -- live-fills the rest."""
        p = Path(path)
        memo = json.loads(p.read_text()) if p.exists() else {}
        return cls(base_obs, memo=memo, **kw)
