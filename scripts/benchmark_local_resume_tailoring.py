"""Benchmark one local model for on-demand résumé-tailoring advice.

This developer tool is deliberately outside Junior's runtime. It does not load
the application database, run scans, change recommendations, or install a
model. It talks only to a locally started llama.cpp OpenAI-compatible server.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import requests


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    job_title: str
    job_description: str
    resume: str
    unsupported_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    elapsed_seconds: float
    valid_structure: bool
    evidence_supported: bool
    unsupported_evidence: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    advice: dict[str, Any] | None
    raw_response: str | None
    error: str | None


def load_cases(path: Path) -> list[BenchmarkCase]:
    """Load explicitly supplied benchmark material without application data."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError("Benchmark cases must be a non-empty JSON list.")
    cases: list[BenchmarkCase] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Benchmark case {index} must be an object.")
        required = ("case_id", "job_title", "job_description", "resume")
        if any(not isinstance(item.get(field), str) or not item[field].strip() for field in required):
            raise ValueError(f"Benchmark case {index} is missing required text.")
        terms = item.get("unsupported_terms", [])
        if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
            raise ValueError(f"Benchmark case {index} has invalid unsupported terms.")
        cases.append(
            BenchmarkCase(
                **{field: item[field].strip() for field in required},
                unsupported_terms=tuple(term.strip() for term in terms if term.strip()),
            )
        )
    return cases


def build_messages(case: BenchmarkCase) -> list[dict[str, str]]:
    """Build the same evidence boundary expected from Junior's future local adviser."""

    return [
        {
            "role": "system",
            "content": (
                "You are a résumé-tailoring adviser. Return only one JSON object. "
                "Suggest at most six concise changes to title, summary, skills, "
                "experience, or projects. Never invent experience, credentials, "
                "dates, employers, tools, responsibilities, or metrics. Every edit "
                "must quote a short supporting phrase that already appears in the "
                "résumé. A real quotation is not enough if it does not directly "
                "support the suggested claim. Never convert adjacent experience "
                "into a named tool or skill the résumé does not state. Put every "
                "unsupported job requirement in cautions. Do not create "
                "a résumé or make an application decision. Use keys summary, edits, "
                "and cautions. Each edit must use keys section, suggestion, and "
                "resume_evidence."
            ),
        },
        {
            "role": "user",
            "content": (
                json.dumps(
                    {
                        "job_title": case.job_title,
                        "job_description": case.job_description,
                        "resume": case.resume,
                    },
                    ensure_ascii=False,
                )
                + "\n/no_think"
            ),
        },
    ]


def parse_advice(raw_text: str) -> dict[str, Any]:
    """Parse a bounded response, tolerating a fenced JSON object only."""

    text = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Advice is not a JSON object.")
    if set(value) != {"summary", "edits", "cautions"}:
        raise ValueError("Advice has unexpected top-level fields.")
    if not isinstance(value["summary"], str):
        raise ValueError("Advice summary must be text.")
    if not isinstance(value["edits"], list) or len(value["edits"]) > 6:
        raise ValueError("Advice edits must be a list of at most six items.")
    if not isinstance(value["cautions"], list) or not all(
        isinstance(item, str) for item in value["cautions"]
    ):
        raise ValueError("Advice cautions must be a list of text items.")
    for edit in value["edits"]:
        if not isinstance(edit, dict) or set(edit) != {
            "section",
            "suggestion",
            "resume_evidence",
        }:
            raise ValueError("Each edit must have the three required fields.")
        if not all(isinstance(edit[field], str) and edit[field].strip() for field in edit):
            raise ValueError("Each edit field must contain text.")
    return value


def unsupported_evidence(advice: dict[str, Any], resume: str) -> tuple[str, ...]:
    """Return evidence quotations that do not appear in the supplied résumé."""

    normalized_resume = _normalize(resume)
    unsupported = []
    for edit in advice["edits"]:
        evidence = edit["resume_evidence"].strip()
        if _normalize(evidence) not in normalized_resume:
            unsupported.append(evidence)
    return tuple(unsupported)


def unsupported_claims(
    advice: dict[str, Any],
    unsupported_terms: tuple[str, ...],
) -> tuple[str, ...]:
    """Detect known unsupported skills promoted as strengths or edits."""

    promoted_text = " ".join(
        [advice["summary"]] + [edit["suggestion"] for edit in advice["edits"]]
    ).casefold()
    return tuple(term for term in unsupported_terms if term.casefold() in promoted_text)


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#.]+", value.casefold()))


def wait_for_server(base_url: str, process: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The local model server exited before becoming ready.")
        try:
            response = requests.get(f"{base_url}/health", timeout=1)
            if response.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise RuntimeError("The local model server did not become ready in time.")


def run_case(base_url: str, case: BenchmarkCase, timeout: float) -> CaseResult:
    started = time.perf_counter()
    raw_text = None
    try:
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "messages": build_messages(case),
                "temperature": 0.1,
                "max_tokens": 1200,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "junior_resume_tailoring",
                        "strict": True,
                        "schema": advice_schema(),
                    },
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        raw_text = payload["choices"][0]["message"]["content"]
        advice = parse_advice(raw_text)
        unsupported = unsupported_evidence(advice, case.resume)
        claim_violations = unsupported_claims(advice, case.unsupported_terms)
        return CaseResult(
            case_id=case.case_id,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            valid_structure=True,
            evidence_supported=not unsupported and not claim_violations,
            unsupported_evidence=unsupported,
            unsupported_claims=claim_violations,
            advice=advice,
            raw_response=raw_text,
            error=None,
        )
    except (KeyError, TypeError, ValueError, requests.RequestException) as error:
        return CaseResult(
            case_id=case.case_id,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            valid_structure=False,
            evidence_supported=False,
            unsupported_evidence=(),
            unsupported_claims=(),
            advice=None,
            raw_response=raw_text,
            error=f"{type(error).__name__}: {error}",
        )


def advice_schema() -> dict[str, Any]:
    """Return the strict portable schema expected from the local server."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "edits", "cautions"],
        "properties": {
            "summary": {"type": "string"},
            "edits": {
                "type": "array",
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["section", "suggestion", "resume_evidence"],
                    "properties": {
                        "section": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "resume_evidence": {"type": "string"},
                    },
                },
            },
            "cautions": {"type": "array", "items": {"type": "string"}},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-executable", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8137)
    parser.add_argument("--context-size", type=int, default=8192)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--startup-timeout", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    for path, label in ((args.server_executable, "server"), (args.model, "model")):
        if not path.is_file():
            parser.error(f"The {label} file does not exist: {path}")

    command = [
        str(args.server_executable),
        "--model",
        str(args.model),
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--ctx-size",
        str(args.context_size),
    ]
    if args.threads > 0:
        command.extend(("--threads", str(args.threads)))
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    base_url = f"http://127.0.0.1:{args.port}"
    started = time.perf_counter()
    try:
        wait_for_server(base_url, process, args.startup_timeout)
        startup_seconds = round(time.perf_counter() - started, 3)
        results = [run_case(base_url, case, args.request_timeout) for case in cases]
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    output = {
        "boundary": "resume_tailoring_only_not_scan_evaluation",
        "model_filename": args.model.name,
        "model_size_bytes": args.model.stat().st_size,
        "server_filename": args.server_executable.name,
        "startup_seconds": startup_seconds,
        "cases": [asdict(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if all(result.valid_structure for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
