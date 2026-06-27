import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_commerce.catalog import import_offers, match_offers
from trend_commerce.database import initialize
from trend_commerce.scoring import score_event
from trend_commerce.settings import ROOT, Settings, load_settings


def main() -> None:
    base = load_settings()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = Settings(
            company_name=base.company_name,
            timezone=base.timezone,
            database_path=root / "eval.db",
            output_dir=root / "output",
            draft_threshold=base.draft_threshold,
            auto_publish_threshold=base.auto_publish_threshold,
            max_candidates_per_run=base.max_candidates_per_run,
            max_daily_generation_cost_yen=0,
            categories=base.categories,
            banned_topics=base.banned_topics,
            dark_pattern_terms=base.dark_pattern_terms,
            openai_model=base.openai_model,
        )
        initialize(settings.database_path)
        import_offers(settings, ROOT / "data" / "offers.csv")
        cases = json.loads((ROOT / "data" / "eval_cases.json").read_text(encoding="utf-8"))
        failed = []
        for case in cases:
            matches = match_offers(settings, case["title"], case["summary"], case["category"])
            score = score_event(settings, case["title"], case["summary"], matches, 1, "", 5)
            actual_ids = {offer.offer_id for offer, _, _ in matches}
            expected_ids = set(case["expected_offer_ids"])
            risk_ok = bool(score.risk_flags) == bool(case["expected_risk"])
            offers_ok = expected_ids.issubset(actual_ids)
            status = "PASS" if risk_ok and offers_ok else "FAIL"
            print("[%s] %s score=%d offers=%s risks=%s" % (status, case["name"], score.total, sorted(actual_ids), score.risk_flags))
            if status == "FAIL":
                failed.append(case["name"])
        if failed:
            raise SystemExit("評価失敗: %s" % ", ".join(failed))


if __name__ == "__main__":
    main()
