from pathlib import Path

from job_radar.config import ConfigError
from job_radar.normalize import clean_text


SUPPORTED_RESUME_EXTENSIONS = {".md", ".txt"}


def load_resume_text(path: str | Path) -> str:
    resume_path = Path(path)
    extension = resume_path.suffix.lower()

    if extension not in SUPPORTED_RESUME_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_RESUME_EXTENSIONS))
        raise ConfigError(
            f"Unsupported resume format: {extension or 'none'}. "
            f"Supported formats: {supported}"
        )

    if not resume_path.exists():
        raise ConfigError(f"Resume file does not exist: {resume_path}")

    text = resume_path.read_text(encoding="utf-8")
    normalized_text = clean_text(text)

    if not normalized_text:
        raise ConfigError(f"Resume file is empty: {resume_path}")

    return normalized_text


def write_normalized_resume_text(
    source_path: str | Path,
    normalized_text_path: str | Path,
) -> Path:
    normalized_text = load_resume_text(source_path)
    output_path = Path(normalized_text_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(normalized_text + "\n", encoding="utf-8")
    return output_path