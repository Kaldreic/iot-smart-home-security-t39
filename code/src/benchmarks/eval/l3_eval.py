"""benchmarks.eval.l3_eval — the offline L3 judging campaign and the judge evaluation.

The L3 judge is an open model (Ollama, ``rdd.l3.judge_ollama``) at temperature 0 with a fixed seed. The
benchmark's reproducibility rests on the committed verdict cache, which the in-loop oracle reads, not on
live-model determinism: GPU inference is not bit-deterministic on borderline cross-bug pairs, so the ``eval``
cross-rejection varies slightly run to run, and ``l3_judge_eval.json`` freezes one run so the number
re-scores offline. Two modes:

  python -m benchmarks.eval.l3_eval judge --model llama3.1:8b --seeds 30
      Collect every L2-uncertain dump pair the real and suppressor benchmarks hit, judge each with the model,
      iterating to a fixed point (a fuller cache changes the minimiser's control flow and exposes new pairs),
      and write data/llm_cache/l3_verdicts.json. Use --seeds 30 to match the anchor, then run
      `benchmarks.run coherence`.

  python -m benchmarks.eval.l3_eval eval --model llama3.1:8b
      Judge a synthetic set of L2-residual and cross-bug pairs and score the judge's recovery and rejection.

Run with Ollama serving the model.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from emulation.dump import DumpModel
from rdd.identity import L2Matcher
from rdd.l3 import _pair_hash, judge_ollama, render_dump

_HERE = Path(__file__).resolve().parent
_DATA = _HERE.parent / "data"


def collect_cases(seeds: int = 30, base_cache: dict | None = None) -> list[dict]:
    """Run the tool over the real bugs and the suppressor and return every L2-uncertain dump pair not already in
    ``base_cache`` (the pairs the judge still has to decide); deterministic, so the hashes match the
    benchmark's runtime lookups. With ``base_cache=None`` the cache is cleared and every uncertain pair is
    collected; with the verdicts judged so far, those pairs hit and the changed control flow exposes any new
    pairs, which is what lets the campaign iterate to a fixed point."""
    from benchmarks import scoring

    from .. import real
    from emulation import suppressor
    from benchmarks import identity_cache as idc
    saved = dict(idc.L3CACHE)
    idc.L3CACHE.clear()
    if base_cache:
        idc.L3CACHE.update(base_cache)                         # judged pairs hit; only new pairs miss
    idc.L3_STATS.update(calls=0, hits=0, misses=[])
    real._run(scoring.run_tool_campaign, idc.id_l2l3, list(real.BUGS), list(range(seeds)), decorrelate=True)
    for s in range(seeds):                                     # the suppressor reuses idc.id_l2l3 -> same L3_STATS
        o = suppressor.LengthReqOracle(identity=idc.id_l2l3)
        scoring.run_tool_campaign(o, [suppressor.LRBUG], random.Random(s), decorrelate=True)
    idc.L3CACHE.clear()
    idc.L3CACHE.update(saved)                                  # restore the global cache
    seen, uniq = set(), []
    for c in idc.L3_STATS["misses"]:
        if c["hash"] not in seen:
            seen.add(c["hash"])
            uniq.append({"hash": c["hash"], "target_bug": c["target_bug"],
                         "target_text": c["target_text"], "rep_text": c["rep_text"]})
    return uniq


def judge_cases(cases: list[dict], *, model: str, host: str | None = None) -> dict:
    """Judge each case with the open model; returns ``{hash: {same, conf, model[, parse_error]}}``."""
    kw = {"model": model} if host is None else {"model": model, "host": host}
    out: dict[str, dict] = {}
    for c in cases:
        v = judge_ollama(c["target_text"], c["rep_text"], **kw)
        rec = {"same": v["same"], "conf": v["conf"], "model": model}
        if "parse_error" in v:
            rec["parse_error"] = v["parse_error"]
        out[c["hash"]] = rec
    return out


def gen_cases(model: DumpModel, n_same: int = 20, n_cross: int = 20, seed: int = 1) -> list[dict]:
    """A synthetic set of same-bug pairs L2 missed (residuals) and cross-bug pairs, for scoring the judge
    independently of the benchmark run."""
    rng = random.Random(seed)
    bugs = list(model.base)
    l2 = L2Matcher({b: model.clean_obs(b) for b in bugs})
    target_text = {b: render_dump(model.clean_obs(b)) for b in bugs}
    cases: list[dict] = []
    for b in bugs:
        got = tries = 0
        while got < n_same and tries < n_same * 400:
            tries += 1
            obs = model.emit(b, rng)
            same, score_ = l2.is_same(b, obs)
            if not same:
                cases.append({"kind": "same_residual", "target_bug": b, "rep_bug": b,
                              "target_text": target_text[b], "rep_text": render_dump(obs),
                              "l2_score": round(score_, 3), "truth_same": True})
                got += 1
    for b in bugs:
        for o in [x for x in bugs if x != b]:
            for _ in range(max(1, n_cross // max(1, len(bugs) - 1))):
                obs = model.emit(o, rng)
                same, score_ = l2.is_same(b, obs)
                cases.append({"kind": "cross", "target_bug": b, "rep_bug": o,
                              "target_text": target_text[b], "rep_text": render_dump(obs),
                              "l2_score": round(score_, 3), "truth_same": False})
    rng.shuffle(cases)
    seen, uniq = set(), []                                      # de-dup by hash so score() counts unique pairs
    for c in cases:
        h = _pair_hash(c["target_text"], c["rep_text"])
        if h in seen:
            continue
        seen.add(h)
        c["hash"], c["id"] = h, len(uniq)
        uniq.append(c)
    return uniq


def score(cases: list[dict], verdicts: dict[str, dict]) -> dict:
    """``verdicts``: hash -> {same, conf}. Returns the judge's residual recovery and cross-bug rejection."""
    def rate(kind, want):
        sel = [c for c in cases if c["kind"] == kind]
        hit = sum(1 for c in sel if verdicts.get(c["hash"], {}).get("same") == want)
        return hit, len(sel)
    rec_hit, rec_n = rate("same_residual", True)
    rej_hit, rej_n = rate("cross", False)
    judged = sum(1 for c in cases if c["hash"] in verdicts)
    return {"l3_residual_recovery": rec_hit / rec_n if rec_n else float("nan"),
            "l3_cross_rejection": rej_hit / rej_n if rej_n else float("nan"),
            "n_residual": rec_n, "n_cross": rej_n, "n_judged": judged, "n_cases": len(cases)}


def _judge_to_fixed_point(model: str, host, seeds: int, max_iters: int = 10, seed_cache: dict | None = None):
    """Iterate collect -> judge until a pass exposes no new pair; a single pass leaves the pairs a fuller cache
    exposes unjudged (they would read as conservative NO). Returns ``(verdicts, cases_by_hash, converged)``
    and does no file I/O. ``seed_cache`` pre-loads verdicts whose pairs then hit and are never re-judged, so
    the committed cache can be grown with new bugs while prior verdicts are preserved byte-exact."""
    accumulated: dict[str, dict] = dict(seed_cache) if seed_cache else {}
    preserved = set(accumulated)
    cases_by_hash: dict[str, dict] = {}
    converged = False
    for it in range(1, max_iters + 1):
        cases = collect_cases(seeds, base_cache=accumulated)
        new = [c for c in cases if c["hash"] not in accumulated]
        if not new:
            converged = True
            break
        accumulated.update(judge_cases(new, model=model, host=host))
        for c in new:
            cases_by_hash[c["hash"]] = c
        print(f"  iter {it}: +{len(new)} new L2-residual pairs judged ({len(accumulated)} total, "
              f"{len(preserved)} preserved)")
    return accumulated, cases_by_hash, converged


def _judge_campaign(model: str, host, seeds: int, max_iters: int = 10, seed_cache: dict | None = None):
    """Judge to a fixed point and persist the verdict cache the benchmark reads. With ``seed_cache`` the cache is
    grown incrementally: prior verdicts preserved, only new pairs judged."""
    accumulated, cases_by_hash, converged = _judge_to_fixed_point(model, host, seeds, max_iters, seed_cache)
    if not converged:                                          # never silently truncate coverage
        left = len(collect_cases(seeds, base_cache=accumulated))
        print(f"  WARNING: did NOT reach a fixed point in {max_iters} iters -- {left} residual pairs left "
              "UNCACHED (runtime gets conservative NO -> under-credit). Raise max_iters and re-run.")
    n_same = sum(1 for v in accumulated.values() if v["same"])
    n_err = sum(1 for v in accumulated.values() if "parse_error" in v)
    cache = _DATA / "llm_cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "l3_verdicts.json").write_text(json.dumps(accumulated, indent=1) + "\n", encoding="utf-8")
    cases_out = dict(cases_by_hash)                            # the newly-judged cases (provenance)
    cp = _DATA / "l3_cases.json"
    if seed_cache and cp.exists():                            # incremental: keep prior cases for preserved verdicts
        for c in json.loads(cp.read_text(encoding="utf-8")):
            if c["hash"] in accumulated and c["hash"] not in cases_out:
                cases_out[c["hash"]] = c
    (_DATA / "l3_cases.json").write_text(json.dumps(list(cases_out.values()), indent=1) + "\n", encoding="utf-8")
    print(f"judged with {model}: {len(accumulated)} pairs ({'a FIXED POINT' if converged else 'NOT converged'}), "
          f"{n_same} 'same', {n_err} parse-errors -> data/llm_cache/l3_verdicts.json")
    print("  now run `python -m benchmarks.run coherence` to verify the real anchor reproduces from the "
          "regenerated cache (collect with --seeds 30 to match the gate)")


def _eval_judge(model: str, host):
    from .. import real                                         # the same bug set the benchmark runs
    cases = gen_cases(real.MODEL)
    verdicts = judge_cases(cases, model=model, host=host)
    sc = score(cases, verdicts)
    ref = _DATA / "reference" / "l3_judge_eval.json"           # committed so the score re-derives offline
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(json.dumps({"model": model, "bugs": list(real.BUGS), "score": sc,
                               "cases": cases, "verdicts": verdicts}, indent=1) + "\n", encoding="utf-8")
    print(f"L3 judge eval ({model}, bugs={''.join(real.BUGS)}): {json.dumps(sc)} -> data/reference/l3_judge_eval.json")


def main():
    ap = argparse.ArgumentParser(prog="benchmarks.eval.l3_eval")
    ap.add_argument("mode", choices=["judge", "eval"],
                    help="judge: populate the benchmark's L3 cache; eval: score the judge's recall/rejection")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=None)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--seed-committed", action="store_true",
                    help="incremental: preserve the committed l3_verdicts.json byte-exact, judge only NEW pairs")
    a = ap.parse_args()
    if a.mode == "judge":
        seed = None
        if a.seed_committed:
            vp = _DATA / "llm_cache" / "l3_verdicts.json"
            seed = json.loads(vp.read_text(encoding="utf-8")) if vp.exists() else {}
            print(f"--seed-committed: preserving {len(seed)} committed verdicts; judging only NEW pairs")
        _judge_campaign(a.model, a.host, a.seeds, seed_cache=seed)
    else:
        _eval_judge(a.model, a.host)


if __name__ == "__main__":
    main()
