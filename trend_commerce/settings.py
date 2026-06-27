from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Optional[Path] = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    company_name: str
    timezone: str
    database_path: Path
    output_dir: Path
    draft_threshold: int
    auto_publish_threshold: int
    max_candidates_per_run: int
    max_daily_generation_cost_yen: int
    categories: List[str]
    banned_topics: List[str]
    dark_pattern_terms: List[str]
    openai_model: str
    site_base_url: str = ""
    ga4_measurement_id: str = ""
    gsc_verification: str = ""


def load_settings(path: Optional[Path] = None) -> Settings:
    load_dotenv()
    config_path = path or ROOT / "config" / "settings.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    database_path = Path(os.getenv("TREND_COMMERCE_DB", raw["database_path"]))
    output_dir = Path(os.getenv("TREND_COMMERCE_OUTPUT", raw["output_dir"]))
    if not database_path.is_absolute():
        database_path = ROOT / database_path
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return Settings(
        company_name=raw["company_name"],
        timezone=raw["timezone"],
        database_path=database_path,
        output_dir=output_dir,
        draft_threshold=int(raw["draft_threshold"]),
        auto_publish_threshold=int(raw["auto_publish_threshold"]),
        max_candidates_per_run=int(raw["max_candidates_per_run"]),
        max_daily_generation_cost_yen=int(raw["max_daily_generation_cost_yen"]),
        categories=list(raw["categories"]),
        banned_topics=list(raw["banned_topics"]),
        dark_pattern_terms=list(raw["dark_pattern_terms"]),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        site_base_url=os.getenv("SITE_BASE_URL", "").rstrip("/"),
        ga4_measurement_id=os.getenv("GA4_MEASUREMENT_ID", "").strip(),
        gsc_verification=os.getenv("GSC_VERIFICATION", "").strip(),
    )


def ensure_directories(settings: Settings) -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    for name in ("drafts", "social", "reports"):
        (settings.output_dir / name).mkdir(parents=True, exist_ok=True)
