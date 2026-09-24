"""benchmarks.identity_cache — the shared cached open-model L3 crash-identity (the reproducibility freeze).

The honest home for the RDD tool's L2 + Frugal-gated cached-L3 identity matcher used across the cached-real
suites (real, suppressor, causeswap) and the L3-cache collector (eval.l3_eval): the L2 weighted comparator,
the COMMITTED open-model L3 verdict cache (data/llm_cache/l3_verdicts.json — the freeze that makes the real-anchor
headline LIVE-FREE), and the provenance accounting. Also the generic per-row aggregator the float-metric
suites (real/live) share. The SYNTHETIC suite uses a separate deterministic no-LLM rule (benchmarks.synthetic),
and the live scenario calls the model live (benchmarks.scenario) — neither uses this module."""

from __future__ import annotations

import numpy as np

import json
from pathlib import Path

from emulation.multibug import BUGS, MODEL
from rdd.identity import L2Matcher
from rdd.l3 import _pair_hash, render_dump

_DATA = Path(__file__).resolve().parent / "data"

L2 = L2Matcher({b: MODEL.clean_obs(b) for b in BUGS})
TARGET_TEXT = {b: render_dump(MODEL.clean_obs(b)) for b in BUGS}
_VPATH = _DATA / "llm_cache" / "l3_verdicts.json"
L3CACHE = json.loads(_VPATH.read_text(encoding="utf-8")) if _VPATH.exists() else {}
L3_BAND_LO = 0.05      # L2 score below this on a "different" verdict = confidently different (trust L2);
#                        in [L3_BAND_LO, threshold) = uncertain -> escalate to L3 (FrugalGPT gate)
L3_STATS = {"calls": 0, "hits": 0, "misses": []}
L3_MODEL = ", ".join(sorted({v["model"] for v in L3CACHE.values()
                             if isinstance(v, dict) and "model" in v})) or "none"


def l3_reset() -> None:
    """Zero the L3 source counters before a run whose L3 provenance we attribute (``l3_provenance``)."""
    L3_STATS.update(calls=0, hits=0, misses=[])


def l3_provenance() -> dict:
    """The SOURCE breakdown of the L3 decisions since the last ``l3_reset``: every L2-uncertain escalation
    is served from the COMMITTED open-model cache (a HIT) or the conservative-NO RULE (a MISS); no live
    model call, so the cached-real headline is LIVE-FREE (``live_calls`` == 0) and reproduces from the cache."""
    return {"source": "cached_open_model", "model": L3_MODEL, "escalations": L3_STATS["calls"],
            "cache_hits": L3_STATS["hits"], "rule_no_fallback": len(L3_STATS["misses"]), "live_calls": 0}


def id_l2l3(target_bug: str, obs) -> bool:                          # RDD: L2 + Frugal-gated cached L3
    same, score = L2.is_same(target_bug, obs)
    if same:
        return True
    if score < L3_BAND_LO:                                          # confidently different -> trust L2
        return False
    L3_STATS["calls"] += 1                                          # uncertain -> L3
    h = _pair_hash(TARGET_TEXT[target_bug], render_dump(obs))
    v = L3CACHE.get(h)
    if v is not None:
        L3_STATS["hits"] += 1
        return isinstance(v, dict) and v.get("same") is True       # strict + corrupt-safe: a non-dict/non-bool
        #                                                             entry degrades to NO, never a false credit
    L3_STATS["misses"].append({"hash": h, "target_bug": target_bug,
                               "target_text": TARGET_TEXT[target_bug], "rep_text": render_dump(obs)})
    return False                                                    # conservative on a cache miss


def agg(rows) -> dict:
    """Generic per-row aggregator for the float-metric suites (real/live): NaN-safe means of genuine,
    false-credit, the size gap on genuine reproductions, and device reads."""
    def m(key, pred=lambda r: True):
        v = [r[key] for r in rows if r.get(key) is not None and pred(r)]
        return float(np.mean(v)) if v else float("nan")
    return {"genuine": m("true_reproduced"), "false_credit": m("false_credit"),
            "size_gap_genuine": m("size_gap", lambda r: r["true_reproduced"]), "reads": m("reads")}
