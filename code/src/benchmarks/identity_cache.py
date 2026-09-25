"""benchmarks.identity_cache — the cached open-model L3 crash identity shared by the cached-real suites.

``id_l2l3`` is the tool's identity matcher for the real, suppressor and causeswap suites and for the L3 cache
collector (``eval.l3_eval``): the L2 weighted comparator, then, in the uncertain band, the committed
open-model verdict cache (data/llm_cache/l3_verdicts.json), keyed on the hash of the rendered (target dump,
observed dump) text pair. A cache miss is a conservative NO; no live model is called on this path. ``agg`` is
the per-row aggregator the real and live suites share. The synthetic suite uses its own deterministic rule
(``benchmarks.synthetic``) and the live suites call the model (``rdd.LiveL2L3Identity``).
"""

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
L3_BAND_LO = 0.05      # an L2 score below this on a "different" verdict is confidently different;
#                        in [L3_BAND_LO, threshold) it is uncertain and escalates to L3
L3_STATS = {"calls": 0, "hits": 0, "misses": []}
L3_MODEL = ", ".join(sorted({v["model"] for v in L3CACHE.values()
                             if isinstance(v, dict) and "model" in v})) or "none"


def l3_reset() -> None:
    """Zero the L3 counters before a run whose provenance ``l3_provenance`` reports."""
    L3_STATS.update(calls=0, hits=0, misses=[])


def l3_provenance() -> dict:
    """The source breakdown of the L3 decisions since the last ``l3_reset``: each escalation was served from the
    committed cache (a hit) or answered NO by the miss rule. ``live_calls`` is 0 by construction here."""
    return {"source": "cached_open_model", "model": L3_MODEL, "escalations": L3_STATS["calls"],
            "cache_hits": L3_STATS["hits"], "rule_no_fallback": len(L3_STATS["misses"]), "live_calls": 0}


def id_l2l3(target_bug: str, obs) -> bool:                          # RDD: L2, then the cached L3 in the band
    same, score = L2.is_same(target_bug, obs)
    if same:
        return True
    if score < L3_BAND_LO:                                          # confidently different
        return False
    L3_STATS["calls"] += 1                                          # uncertain: escalate
    h = _pair_hash(TARGET_TEXT[target_bug], render_dump(obs))
    if h in L3CACHE:                                                # `in`, as rdd.identity: a stored None is a hit
        v = L3CACHE[h]
        L3_STATS["hits"] += 1
        return isinstance(v, dict) and v.get("same") is True       # strict: a non-dict or non-bool entry
        #                                                             reads as NO
    L3_STATS["misses"].append({"hash": h, "target_bug": target_bug,
                               "target_text": TARGET_TEXT[target_bug], "rep_text": render_dump(obs)})
    return False                                                    # conservative on a cache miss


def agg(rows) -> dict:
    """NaN-safe means over scored rows: genuine, false credit, the size gap on genuine reproductions, and reads."""
    def m(key, pred=lambda r: True):
        v = [r[key] for r in rows if r.get(key) is not None and pred(r)]
        return float(np.mean(v)) if v else float("nan")
    return {"genuine": m("true_reproduced"), "false_credit": m("false_credit"),
            "size_gap_genuine": m("size_gap", lambda r: r["true_reproduced"]), "reads": m("reads")}
