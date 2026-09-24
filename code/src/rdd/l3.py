"""The L3 crash-identity judge: an open model asked whether two crash reports are the same bug.

L3 runs only on the pairs L2 cannot decide. ``judge_ollama`` queries a local model through Ollama;
``render_dump`` produces the report text the judge reads and ``_pair_hash`` keys the verdict memo.
The offline judging that fills the benchmark's verdict cache lives in ``benchmarks/eval/l3_eval.py``.
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
    """Read the model's ``same`` field, failing closed: a bool is taken as is, a number is True only
    when equal to 1, a string only when it is an affirmative token, and anything else is False."""
    if isinstance(s, bool):
        return s
    if isinstance(s, (int, float)):
        return s == 1
    if isinstance(s, str):
        return s.strip().lower() in {"true", "yes", "same", "match"}
    return False


def judge_ollama(target_text: str, rep_text: str, *, model: str = "llama3.1:8b",
                 host: str = _OLLAMA_HOST, timeout: float = 180.0) -> dict:
    """Ask a local open model through Ollama whether two crash reports describe the same bug.

    Returns ``{"same": bool, "conf": float}``. Temperature 0, a fixed seed and JSON-constrained output
    make the answer as repeatable as the backend allows. A connection or HTTP error propagates; a
    non-JSON reply returns ``same=False`` with a ``parse_error`` field, and a malformed ``same`` value
    goes through ``_coerce_same``, so a garbled reply can only under-credit."""
    user = (f"Report A (reference):\n{target_text}\n\nReport B (candidate):\n{rep_text}\n\n"
            "Are A and B the same underlying bug?")
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": _JUDGE_SYSTEM}, {"role": "user", "content": user}],
        "stream": False, "format": "json", "options": {"temperature": 0, "seed": 0},
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:        # connection and HTTP errors propagate
        body = json.loads(r.read().decode())
    content = body.get("message", {}).get("content") if isinstance(body, dict) else None
    if content is None:                                            # an Ollama error envelope: HTTP 200, no message
        return {"same": False, "conf": 0.0, "parse_error": str(body)[:120]}
    try:
        v = json.loads(content)
        return {"same": _coerce_same(v["same"]), "conf": float(v.get("confidence", 0.0))}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"same": False, "conf": 0.0, "parse_error": content[:120]}


def render_dump(obs) -> str:
    """The crash report text the judge reads: log lines, then the backtrace top first."""
    lines = ["--- crash report ---", *list(obs.log_lines)]
    if obs.stack:
        lines.append("backtrace (top first):")
        lines += [f"  #{i} {f}" for i, f in enumerate(obs.stack)]
    return "\n".join(lines)


def _pair_hash(a: str, b: str) -> str:
    return hashlib.sha1(f"{a}||{b}".encode()).hexdigest()[:16]
