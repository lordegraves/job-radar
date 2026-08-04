import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "benchmark_local_resume_tailoring.py"
SPEC = importlib.util.spec_from_file_location("local_tailoring_benchmark", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def make_case():
    return benchmark.BenchmarkCase(
        case_id="platform-1",
        job_title="Platform Engineer",
        job_description="Requires Linux and Kubernetes administration.",
        resume="Operated Linux HPC platforms and automated storage services.",
    )


def test_prompt_limits_local_model_to_resume_tailoring() -> None:
    messages = benchmark.build_messages(make_case())

    system = messages[0]["content"]
    assert "Never invent" in system
    assert "Do not create a résumé" in system
    assert "make an application decision" in system
    assert "job_description" in messages[1]["content"]


def test_advice_parser_and_evidence_check() -> None:
    advice = benchmark.parse_advice(
        json.dumps(
            {
                "summary": "Lead with supported Linux operations.",
                "edits": [
                    {
                        "section": "Experience",
                        "suggestion": "Move the Linux platform work earlier.",
                        "resume_evidence": "Operated Linux HPC platforms",
                    },
                    {
                        "section": "Skills",
                        "suggestion": "Add Kubernetes administration.",
                        "resume_evidence": "Administered Kubernetes clusters",
                    },
                ],
                "cautions": ["Kubernetes is not supported by the résumé."],
            }
        )
    )

    assert benchmark.unsupported_evidence(advice, make_case().resume) == (
        "Administered Kubernetes clusters",
    )
    assert benchmark.unsupported_claims(advice, ("Kubernetes", "Prometheus")) == (
        "Kubernetes",
    )


def test_load_cases_rejects_missing_private_input(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text('[{"case_id":"missing"}]', encoding="utf-8")

    try:
        benchmark.load_cases(cases_path)
    except ValueError as error:
        assert "missing required text" in str(error)
    else:
        raise AssertionError("Invalid benchmark input was accepted")
