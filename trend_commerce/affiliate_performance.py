from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Dict, List

from .database import connect, initialize, transaction
from .settings import ROOT, Settings


REQUIRED_FIELDS = {"measured_date", "page_slug", "offer_id", "page_views", "affiliate_clicks"}


def import_affiliate_metrics(settings: Settings, path: Path, source: str = "ga4_csv") -> Dict[str, int]:
    initialize(settings.database_path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError("クリック指標CSVに必須列がありません: %s" % ", ".join(sorted(missing)))
        rows = list(reader)
    inserted = 0
    with transaction(settings.database_path) as conn:
        for row in rows:
            conn.execute(
                """INSERT INTO affiliate_metrics_daily(measured_date,page_slug,offer_id,page_views,affiliate_clicks,source)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(measured_date,page_slug,offer_id,source) DO UPDATE SET
                page_views=excluded.page_views,affiliate_clicks=excluded.affiliate_clicks""",
                (row["measured_date"], row["page_slug"], row["offer_id"], int(row["page_views"] or 0), int(row["affiliate_clicks"] or 0), source),
            )
            inserted += 1
    return {"processed": len(rows), "upserted": inserted}


def affiliate_performance_rows(settings: Settings) -> List[Dict[str, object]]:
    initialize(settings.database_path)
    page_by_offer = _page_by_offer()
    with connect(settings.database_path) as conn:
        offers = [dict(row) for row in conn.execute("SELECT offer_id,name,category,status FROM offers WHERE status='active'")]
        metrics = {
            row["offer_id"]: dict(row)
            for row in conn.execute(
                """SELECT offer_id,COALESCE(SUM(page_views),0) page_views,COALESCE(SUM(affiliate_clicks),0) clicks
                FROM affiliate_metrics_daily GROUP BY offer_id"""
            )
        }
        sales = {
            row["offer_id"]: dict(row)
            for row in conn.execute(
                """SELECT offer_id,COUNT(*) conversions,COALESCE(SUM(amount),0) revenue
                FROM conversions WHERE status IN ('approved','confirmed') AND offer_id IS NOT NULL GROUP BY offer_id"""
            )
        }
    result = []
    for offer in offers:
        offer_id = offer["offer_id"]
        m = metrics.get(offer_id, {"page_views": 0, "clicks": 0})
        s = sales.get(offer_id, {"conversions": 0, "revenue": 0})
        views, clicks = int(m["page_views"]), int(m["clicks"])
        conversions, revenue = int(s["conversions"]), float(s["revenue"])
        ctr = clicks / views if views else 0.0
        cvr = conversions / clicks if clicks else 0.0
        epc = revenue / clicks if clicks else 0.0
        result.append({
            "offer_id": offer_id, "name": offer["name"], "category": offer["category"],
            "page_slug": page_by_offer.get(offer_id, ""), "page_views": views, "clicks": clicks,
            "ctr": round(ctr * 100, 2), "conversions": conversions, "cvr": round(cvr * 100, 2),
            "revenue": round(revenue, 2), "epc": round(epc, 2),
            "recommendation": _recommendation(views, clicks, conversions, revenue),
        })
    return sorted(result, key=lambda row: (-float(row["revenue"]), -int(row["clicks"]), str(row["offer_id"])))


def write_affiliate_performance_report(settings: Settings) -> Dict[str, object]:
    rows = affiliate_performance_rows(settings)
    directory = settings.output_dir / "affiliate_analysis"
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "product_performance.csv"
    fields = ["offer_id", "name", "category", "page_slug", "page_views", "clicks", "ctr", "conversions", "cvr", "revenue", "epc", "recommendation"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    html_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.2f%%</td><td>%s</td><td>¥%s</td><td>¥%s</td><td>%s</td></tr>" % (
            html.escape(str(row["offer_id"])), html.escape(str(row["name"])[:80]), row["page_views"], row["clicks"],
            row["ctr"], row["conversions"], f"{float(row['revenue']):,.0f}", f"{float(row['epc']):,.0f}", html.escape(str(row["recommendation"])),
        ) for row in rows
    )
    html_path = directory / "product_performance.html"
    html_path.write_text(
        "<!doctype html><html lang='ja'><meta charset='utf-8'><title>商品別収益分析</title><style>body{font-family:sans-serif;margin:32px}table{border-collapse:collapse;width:100%%}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:left}th{position:sticky;top:0;background:#eef4ff}</style><h1>商品別収益分析</h1><table><thead><tr><th>商品ID</th><th>商品</th><th>PV</th><th>クリック</th><th>CTR</th><th>成約</th><th>売上</th><th>EPC</th><th>改善提案</th></tr></thead><tbody>%s</tbody></table></html>" % html_rows,
        encoding="utf-8",
    )
    return {"rows": len(rows), "csv": str(csv_path), "html": str(html_path)}


def _page_by_offer() -> Dict[str, str]:
    path = ROOT / "data" / "comparison_product_map.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["offer_candidate_id"]: row["page_slug"] for row in csv.DictReader(handle)}


def _recommendation(views: int, clicks: int, conversions: int, revenue: float) -> str:
    if views < 100:
        return "データ収集中"
    if clicks == 0:
        return "商品位置とCTAを改善"
    if clicks / views < 0.02:
        return "タイトルと商品訴求を改善"
    if conversions == 0 and clicks >= 20:
        return "商品価格と販売ページのズレを確認"
    if conversions and revenue / max(clicks, 1) > 100:
        return "維持してSNSと関連記事へ展開"
    return "継続観測"
