from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Dict, List

from .settings import ROOT, Settings


def scan_affiliate_programs(settings: Settings) -> Dict[str, object]:
    """Create the research department's recurring A8/ASP review queue.

    A8 requires an authenticated dashboard, so this job never scrapes private
    terms. It prepares a focused checklist that a logged-in review can update.
    """
    source = ROOT / "data" / "service_offer_candidates.csv"
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows: List[Dict[str, str]] = list(csv.DictReader(handle))
    rows.sort(key=lambda row: (
        0 if "A8" in row.get("network_candidates", "") else 1,
        0 if row.get("status") in {"apply", "research"} else 1,
        row.get("risk_level", ""), row.get("service_group", ""),
    ))
    out_dir = settings.output_dir / "affiliate_research"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "latest_program_check.csv"
    fields = [
        "checked_on", "service_group", "category", "network_candidates",
        "status", "risk_level", "check_items", "news_match_action", "notes",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "checked_on": date.today().isoformat(),
                "service_group": row.get("service_group", ""),
                "category": row.get("category", ""),
                "network_candidates": row.get("network_candidates", ""),
                "status": row.get("status", ""),
                "risk_level": row.get("risk_level", ""),
                "check_items": "提携可否|成果地点|否認条件|SNS可否|バナー|終了日",
                "news_match_action": "関連ニュース一致時は比較記事とSNS候補を優先生成",
                "notes": row.get("notes", ""),
            })
    return {"candidates": len(rows), "a8_candidates": sum("A8" in r.get("network_candidates", "") for r in rows), "output": str(output)}
