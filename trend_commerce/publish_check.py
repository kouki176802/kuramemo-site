from __future__ import annotations

from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

from .settings import Settings


REQUIRED_PAGES = {
    "index.html",
    "about.html",
    "advertising-policy.html",
    "editorial-policy.html",
    "privacy-policy.html",
    "disclaimer.html",
}


def check_publish_ready(settings: Settings, site_dir: Path) -> Dict[str, object]:
    errors: List[str] = []
    warnings: List[str] = []
    parsed = urlparse(settings.site_base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("SITE_BASE_URLに公開用HTTPS URLが未設定")
    if parsed.hostname in {"localhost", "127.0.0.1"}:
        errors.append("SITE_BASE_URLがローカルURL")
    if not site_dir.exists():
        errors.append("サイト出力先が存在しない")
        return {"ready": False, "errors": errors, "warnings": warnings, "html_pages": 0}

    names = {path.name for path in site_dir.glob("*.html")}
    for name in sorted(REQUIRED_PAGES - names):
        errors.append("必須ページ不足: %s" % name)
    html_files = sorted(site_dir.glob("*.html"))
    for path in html_files:
        body = path.read_text(encoding="utf-8")
        if 'name="robots" content="noindex' in body:
            errors.append("noindexが残っています: %s" % path.name)
        if "127.0.0.1" in body or "localhost" in body:
            errors.append("ローカルURLが残っています: %s" % path.name)
        if "商品リンク準備中" in body:
            warnings.append("未接続の商品枠があります: %s" % path.name)
    robots = site_dir / "robots.txt"
    sitemap = site_dir / "sitemap.xml"
    if not robots.exists() or "Disallow: /" in robots.read_text(encoding="utf-8"):
        errors.append("robots.txtが公開許可状態ではありません")
    if not sitemap.exists():
        errors.append("sitemap.xmlがありません")
    if not settings.ga4_measurement_id:
        warnings.append("GA4測定IDが未設定")
    if not settings.gsc_verification:
        warnings.append("Search Console確認トークンが未設定")
    return {
        "ready": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "html_pages": len(html_files),
    }
