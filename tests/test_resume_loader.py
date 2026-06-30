import pytest

from job_radar.config import ConfigError
from job_radar.resume_loader import load_resume_text, write_normalized_resume_text


def test_load_resume_text_reads_markdown(tmp_path) -> None:
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Resume\n\nLinux infrastructure and HPC operations", encoding="utf-8")

    assert load_resume_text(resume_path) == "# Resume Linux infrastructure and HPC operations"


def test_load_resume_text_reads_txt(tmp_path) -> None:
    resume_path = tmp_path / "resume.txt"
    resume_path.write_text("Cluster systems\nStorage operations", encoding="utf-8")

    assert load_resume_text(resume_path) == "Cluster systems Storage operations"


def test_load_resume_text_rejects_unsupported_extension(tmp_path) -> None:
    resume_path = tmp_path / "resume.doc"
    resume_path.write_text("legacy word file", encoding="utf-8")

    with pytest.raises(ConfigError, match="Unsupported resume format: .doc"):
        load_resume_text(resume_path)


def test_write_normalized_resume_text(tmp_path) -> None:
    resume_path = tmp_path / "resume.md"
    normalized_path = tmp_path / "resume.normalized.txt"
    resume_path.write_text("Linux\n\nInfrastructure", encoding="utf-8")

    write_normalized_resume_text(resume_path, normalized_path)

    assert normalized_path.read_text(encoding="utf-8") == "Linux Infrastructure\n"