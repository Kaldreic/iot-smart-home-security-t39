"""rdd.l3 — the L3 crash-identity judge surface used in-loop.

The FrugalGPT tail of the cascade fires only on the L2 RESIDUAL (the ~3-6% severely-garbled reports L2
abstains on — e.g. a Bug-A stack gutted to one frame, or an assert with the line corrupted to ":??"); a
cached OPEN-model verdict (``judge_ollama``, deterministic) is then looked up by the pair hash. This module
provides the JUDGE backend (``judge_ollama`` -- a local open model via Ollama) + the two in-loop primitives
the oracle needs: ``render_dump`` (the crash report as the judge reads it) and ``_pair_hash`` (the
verdict-cache key). The offline case-collection + judging that DRIVES ``judge_ollama`` to populate the
cache lives in ``benchmarks/eval/l3_eval.py``, not in the deployable tool.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request

_OLLAMA_HOST = "http://localhost:11434"
_JUDGE_SYSTEM = (
    "You are a crash-triage judge. Two crash reports come from the same wireless-firmware fuzzing campaign. "
    "Decide whether they describe the SAME underlying bug -- the same crashing fault at the same root-cause "
    "site -- despite surface noise: truncated or reordered backtraces, a lost top frame, address "
    "randomisation (0x... values differ), and garbled or interleaved log lines. They are the SAME bug if the "
    "fault type and crash site/cause match through the noise; DIFFERENT if the root cause clearly differs. "
    'Respond ONLY with JSON: {"same": <true|false>, "confidence": <number 0.0-1.0>}.'
)


def _coerce_same(s) -> bool:
    """Read the model's ``same`` verdict, failing CLOSED. A JSON bool is taken as-is; a STRING is matched
    against an explicit affirmative allow-list (so ``"false"``/``"no"``/``"different"``/``"0"`` -> False,
    NOT the ``True`` that a raw ``bool("false")`` would wrongly give); a number is True only if ``== 1``;
    anything else (null/object/array) -> False. So a garbled reply can only make the judge UNDER-credit,
    never spuriously MATCH -- preserving the "never a false match" guarantee against a weak open model."""
    if isinstance(s, bool):
        return s
    if isinstance(s, (int, float)):
        return s == 1
    if isinstance(s, str):
        return s.strip().lower() in {"true", "yes", "same", "match"}
    return False


def judge_ollama(target_text: str, rep_text: str, *, model: str = "llama3.1:8b",
                 host: str = _OLLAMA_HOST, timeout: float = 180.0) -> dict:
    """The L3 JUDGE backend: ask a local OPEN model (via Ollama) whether two crash reports are the same
    bug. Open models are the academic-standard, no-API-key, anyone-can-rerun choice; this replaces a
    proprietary judge for a reproducible, undisputable evaluation.

    Temperature 0 + a fixed seed + JSON-constrained output make the judge as reproducible as the backend
    allows; GPU inference is NOT bit-deterministic on low-signal (borderline) judgments, so the BENCHMARK's
    reproducibility comes from the committed verdict cache (the in-loop oracle reads the frozen cache, never
    the live model). The high-signal SAME-bug judgments that populate that cache are empirically stable (a
    full campaign re-run reproduces them identically); only borderline cross-bug eval verdicts can flip.
    Returns ``{"same": bool, "conf": float}``. RAISES on a connection/HTTP error (so a broken Ollama fails
    the judging LOUDLY rather than silently producing an all-NO cache); a non-JSON reply degrades to the
    conservative ``{"same": False, "conf": 0.0, "parse_error": ...}``, and a malformed-but-JSON ``same``
    (a string/number/null) is read fail-closed via ``_coerce_same`` (never a raw ``bool()``). Every garbled
    path is a weak verdict, never a false match -- the judge can only under-credit."""
    user = (f"Report A (reference):\n{target_text}\n\nReport B (candidate):\n{rep_text}\n\n"
            "Are A and B the same underlying bug?")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": _JUDGE_SYSTEM}, {"role": "user", "content": user}],
        "stream": False, "format": "json", "options": {"temperature": 0, "seed": 0},
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:        # connection/HTTP errors propagate (loud)
        body = json.loads(r.read().decode())
    content = body.get("message", {}).get("content") if isinstance(body, dict) else None
    if content is None:                                            # an Ollama error envelope (HTTP 200, no message)
        return {"same": False, "conf": 0.0, "parse_error": str(body)[:120]}
    try:
        v = json.loads(content)
        return {"same": _coerce_same(v["same"]), "conf": float(v.get("confidence", 0.0))}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"same": False, "conf": 0.0, "parse_error": content[:120]}


def render_dump(obs) -> str:
    """The crash report as a judge reads it (log lines + backtrace)."""
    lines = ["--- crash report ---", *list(obs.log_lines)]
    if obs.stack:
        lines.append("backtrace (top first):")
        lines += [f"  #{i} {f}" for i, f in enumerate(obs.stack)]
    return "\n".join(lines)


def _pair_hash(a: str, b: str) -> str:
    return hashlib.sha1(f"{a}||{b}".encode()).hexdigest()[:16]
