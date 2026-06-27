from __future__ import annotations

import base64
import csv
import html
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import ArticleBundle
from .settings import ROOT, load_dotenv


def _offer_links() -> Dict[str, Tuple[str, str]]:
    path = ROOT / "data" / "offers.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["offer_id"]: (row.get("name", "商品を確認"), row.get("affiliate_url", ""))
            for row in csv.DictReader(handle)
            if row.get("status") == "active" and row.get("affiliate_url")
        }


def _inline_markdown(value: str) -> str:
    value = html.escape(value, quote=False)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        lambda match: '<a href="%s" rel="noopener">%s</a>' % (
            html.escape(match.group(2), quote=True), match.group(1)
        ),
        value,
    )
    return value


def markdown_to_wp_html(markdown: str) -> str:
    """Convert the controlled article template to safe WordPress-ready HTML."""
    offers = _offer_links()
    lines = markdown.splitlines()
    out: List[str] = []
    list_tag = ""
    paragraph: List[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append("<p>%s</p>" % "<br>".join(_inline_markdown(line) for line in paragraph))
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append("</%s>" % list_tag)
            list_tag = ""

    index = 0
    while index < len(lines):
        raw = lines[index].rstrip()
        stripped = raw.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            index += 1
            continue
        offer_match = re.fullmatch(r'\[offer id="([^"]+)" placement="[^"]+"\]', stripped)
        if offer_match:
            flush_paragraph()
            close_list()
            offer = offers.get(offer_match.group(1))
            if offer:
                label, url = offer
                out.append(
                    '<p class="kuramemo-offer"><a class="button affiliate-link" href="%s" '
                    'rel="nofollow sponsored noopener" target="_blank">%s</a></p>'
                    % (html.escape(url, quote=True), html.escape(label + "の価格・条件を確認"))
                )
            continue_index = index + 1
            index = continue_index
            continue
        if stripped.startswith("# "):
            # WordPress renders the article title separately.
            index += 1
            continue
        heading = re.match(r"^(#{2,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            out.append("<h%d>%s</h%d>" % (level, _inline_markdown(heading.group(2)), level))
            index += 1
            continue
        if stripped.startswith("> "):
            flush_paragraph()
            close_list()
            out.append("<blockquote><p>%s</p></blockquote>" % _inline_markdown(stripped[2:]))
            index += 1
            continue
        item = re.match(r"^[-*]\s+(.+)$", stripped)
        numbered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if item or numbered:
            flush_paragraph()
            wanted = "ul" if item else "ol"
            if list_tag != wanted:
                close_list()
                list_tag = wanted
                out.append("<%s>" % wanted)
            out.append("<li>%s</li>" % _inline_markdown((item or numbered).group(1)))
            index += 1
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and re.match(r"^\|?[\s:|-]+\|?$", lines[index + 1].strip()):
            flush_paragraph()
            close_list()
            header_cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            index += 2
            body_rows: List[List[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                body_rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            table = ["<div class=\"wp-table-scroll\"><table><thead><tr>"]
            table.extend("<th>%s</th>" % _inline_markdown(cell) for cell in header_cells)
            table.append("</tr></thead><tbody>")
            for cells in body_rows:
                table.append("<tr>")
                table.extend("<td>%s</td>" % _inline_markdown(cell) for cell in cells)
                table.append("</tr>")
            table.append("</tbody></table></div>")
            out.append("".join(table))
            continue
        if stripped == "---":
            flush_paragraph()
            close_list()
            out.append("<hr>")
            index += 1
            continue
        paragraph.append(stripped[:-2] if stripped.endswith("  ") else stripped)
        index += 1

    flush_paragraph()
    close_list()
    return "\n".join(out)


class WordPressPublisher:
    """WordPress adapter that only creates drafts."""

    def __init__(self) -> None:
        load_dotenv()
        self.base_url = os.environ["WORDPRESS_BASE_URL"].rstrip("/")
        self.username = os.environ["WORDPRESS_USERNAME"]
        self.password = os.environ["WORDPRESS_APPLICATION_PASSWORD"].replace(" ", "")

    def _request(self, path: str, payload: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        token = base64.b64encode((self.username + ":" + self.password).encode("utf-8")).decode("ascii")
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Authorization": "Basic %s" % token, "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def check_connection(self) -> Dict[str, object]:
        user = self._request("/wp-json/wp/v2/users/me?context=edit")
        return {"connected": True, "user_id": user.get("id"), "name": user.get("name")}

    def create_draft(self, bundle: ArticleBundle) -> Dict[str, object]:
        return self._request(
            "/wp-json/wp/v2/posts",
            {
                "title": bundle.title,
                "content": markdown_to_wp_html(bundle.body_markdown),
                "excerpt": bundle.meta_description,
                "slug": bundle.slug,
                "status": "draft",
            },
        )

    def create_draft_from_file(self, path: Path, title: str = "", slug: str = "", excerpt: str = "") -> Dict[str, object]:
        markdown = path.read_text(encoding="utf-8")
        detected = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        final_title = title or (detected.group(1).strip() if detected else path.stem)
        bundle = ArticleBundle(
            title=final_title,
            slug=slug or path.stem,
            meta_description=excerpt or final_title,
            lead="",
            body_markdown=markdown,
            cta_blocks=[], social_assets={}, behavioral_principles=[], objections=[],
            non_purchase_option="", urgency_source="", evidence_urls=[],
        )
        return self.create_draft(bundle)
