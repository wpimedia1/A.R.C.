"""Autonomous tool repair.

When a registered domain tool throws, the bench synthesizes a diagnostic
script (via the Muse model when keyed, else a built-in template), executes
it in a worker thread with a timeout and a restricted builtin set, captures
the report, retries the tool once, and returns the full record. Nothing is
mocked: scripts really run, output is really captured.
"""
from __future__ import annotations

import concurrent.futures
import io
import os
import time
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

import httpx

REPAIR_MODEL_URL = os.environ.get(
    "OPEN_BASE_URL", os.environ.get("MODEL_BASE_URL",
                                   "https://api.meta.ai/v1"))
REPAIR_MODEL_KEY = os.environ.get(
    "OPEN_API_KEY", os.environ.get("MODEL_API_KEY", ""))
REPAIR_MODEL = os.environ.get(
    "OPEN_MODEL", os.environ.get("MODEL_NAME", "muse-spark-1.3"))

SAFE_BUILTINS = {
    "len": len, "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple, "range": range,
    "enumerate": enumerate, "zip": zip, "min": min, "max": max, "sum": sum,
    "sorted": sorted, "print": print, "isinstance": isinstance,
}

DIAGNOSTIC_TEMPLATE = """\
report = {{}}
report["tool"] = TOOL_NAME
report["input_keys"] = sorted(INPUT.keys())
report["input_types"] = {{k: type(v).__name__ for k, v in INPUT.items()}}
report["error"] = ERROR[-400:]
checks = []
checks.append("inputs_present:" + str(bool(INPUT)))
checks.append("error_is_value:" + str(isinstance(ERROR, str)))
report["checks"] = checks
RESULT = report
"""


@dataclass
class RepairReport:
    tool: str
    ok: bool
    attempts: int = 0
    diagnostic_output: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str = ""
    duration_s: float = 0.0


def draft_checks(tool: str, error: str) -> str:
    if REPAIR_MODEL_URL and REPAIR_MODEL_KEY:
        try:
            resp = httpx.post(
                REPAIR_MODEL_URL.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {REPAIR_MODEL_KEY}"},
                json={
                    "model": REPAIR_MODEL,
                    "messages": [
                        {"role": "system", "content":
                         "Write a short Python diagnostic script. Use only "
                         "TOOL_NAME, INPUT, ERROR. End by setting RESULT to "
                         "a dict report. Reply with code only."},
                        {"role": "user", "content":
                         f"Tool {tool} failed with: {error[:500]}"},
                    ],
                    "temperature": 0.2,
                },
                timeout=30.0,
            )
            code = resp.json()["choices"][0]["message"]["content"]
            return code.strip().strip("`").replace("python\n", "", 1)
        except Exception:
            pass
    return DIAGNOSTIC_TEMPLATE


def run_script(source: str, namespace: Dict[str, Any],
               timeout_s: float = 10.0) -> Dict[str, Any]:
    ns = {"__builtins__": SAFE_BUILTINS}
    ns.update(namespace)
    buf = io.StringIO()

    def _target():
        with redirect_stdout(buf):
            exec(compile(source, "<diagnostic>", "exec"), ns)  # noqa: S102

    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_target)
        try:
            fut.result(timeout=timeout_s)
            status = "ran"
        except concurrent.futures.TimeoutError:
            status = "timeout"
        except Exception:
            status = "error:" + traceback.format_exc(limit=3)[-400:]
    return {"status": status, "stdout": buf.getvalue()[-1000:],
            "result": ns.get("RESULT"),
            "duration_s": round(time.time() - started, 3)}


class ToolBench:
    def __init__(self) -> None:
        self.tools: Dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        self.tools[name] = fn

    def call(self, name: str, **kwargs) -> RepairReport:
        started = time.time()
        report = RepairReport(tool=name, ok=False)
        try:
            report.result = self.tools[name](**kwargs)
            report.ok = True
            report.attempts = 1
        except Exception as exc:
            err = traceback.format_exc(limit=5)
            script = draft_checks(
                name, err).replace("TOOL_NAME", repr(name))
            diag = run_script(
                script, {"INPUT": kwargs, "ERROR": err})
            report.diagnostic_output = diag
            try:
                report.result = self.tools[name](**kwargs)
                report.ok = True
            except Exception:
                report.error = err[-500:]
            report.attempts = 2
        report.duration_s = round(time.time() - started, 3)
        return report
