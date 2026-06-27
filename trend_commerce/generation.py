from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from typing import Any, Dict, List

from .models import ArticleBundle, EventCandidate, Offer
from .settings import Settings
from .utils import safe_slug


def _offer_rows(offers: List[Offer]) -> str:
    if not offers:
        return "| 選択肢 | 向く人 | 確認事項 |\n|---|---|---|\n| 商品候補を調査中 | 急がず比較したい人 | 価格・在庫・仕様 |"
    rows = ["| 選択肢 | 向く人 | 確認事項 |", "|---|---|---|"]
    labels = ["標準候補", "価格重視候補", "機能重視候補", "代替候補", "追加候補"]
    for index, offer in enumerate(offers):
        rows.append("| %s：%s | 用途と条件が合う人 | 最新価格・在庫・公式条件 |" % (labels[index], offer.name))
    return "\n".join(rows)


def _cta_blocks(offers: List[Offer]) -> List[Dict[str, str]]:
    blocks: List[Dict[str, str]] = []
    for offer in offers[:3]:
        blocks.append(
            {
                "label": "%sの価格・条件を確認する" % offer.name,
                "offer_id": offer.offer_id,
                "placeholder": "[offer id=\"%s\" placement=\"comparison\"]" % offer.offer_id,
            }
        )
    return blocks


class LocalArticleGenerator:
    name = "local-template"

    def generate(self, candidate: EventCandidate) -> ArticleBundle:
        slug = safe_slug("trend", candidate.event_id, candidate.title)
        checked_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        source_list = "\n".join("- %s" % url for url in candidate.source_urls)
        ctas = _cta_blocks(candidate.offers)
        cta_markdown = "\n\n".join("**%s**  \n%s" % (item["label"], item["placeholder"]) for item in ctas)
        if not cta_markdown:
            cta_markdown = "商品候補は調査中です。公式情報を確認してから掲載します。"

        title = "%s｜いま買う・待つ・不要を判断するポイント" % candidate.title
        meta = "%sについて、対象者、選び方、商品候補、買わずに済む場合を整理します。" % candidate.title
        lead = (
            "結論からいうと、この話題を見て全員がすぐ購入する必要はありません。"
            "影響を受ける条件を確認し、必要な人だけが比較できるように整理します。"
        )
        body = """# {title}

> **広告について:** この記事には広告・アフィリエイトリンク候補が含まれます。価格・在庫・条件はリンク先で確認してください。

{lead}

## まず3項目を確認

- このニュースの影響を直接受ける状況か
- 手元の商品や無料の方法で代用できないか
- 価格だけでなく、用途・サイズ・互換性が合うか

1つも当てはまらない場合は、急いで購入せず情報の更新を待つ選択が妥当です。

## 何が起きたか

{summary}

現時点で確認できる情報を基にした整理です。推測部分を事実として扱わず、最新情報は出典元で確認してください。

## いま買う・待つ・不要の判断

### 買う候補になる人

- 話題の影響を受ける時期・環境が明確な人
- 手持ち品では目的を満たせない人
- 商品の仕様と利用条件を確認できた人

### 待って比較する人

- 価格や在庫が大きく動いている人
- 新商品と旧商品の差がまだ明確でない人
- 公式情報が追加される可能性がある人

### 購入不要の人

- 手持ち品で代用できる人
- 話題の対象地域・利用条件に当てはまらない人
- 一時的な流行だけが購入理由になっている人

## 選択肢を3つに整理

{offer_table}

報酬額だけで順位を決めず、対象者と用途が異なる候補として比較しています。

## 購入前の反論チェック

1. 本当に今必要か
2. 既存品やレンタルで代用できないか
3. 返品・保証・解約条件を確認したか
4. サイズ・規格・対応機種が合うか
5. セールや在庫表示の確認日時は新しいか

## 価格と条件を確認する

{cta_markdown}

## 買わない場合の代替案

まず手持ち品、無料の設定変更、自治体・メーカーの案内で対応できるか確認してください。必要性が明確になってから比較しても遅くありません。

## 出典・確認日時

確認日時: {checked_at}

{source_list}

---

この記事はニュース本文の転載ではなく、公開情報を基に買い物判断の軸を整理したものです。
""".format(
            title=title,
            lead=lead,
            summary=candidate.summary or "詳細は公式発表で確認してください。",
            offer_table=_offer_rows(candidate.offers),
            cta_markdown=cta_markdown,
            checked_at=checked_at,
            source_list=source_list,
        )
        social = {
            "x": [
                "%s。全員が急いで買う話ではありません。対象条件・代用品・価格を確認する3つの判断軸を整理しました。" % candidate.title,
                "話題の商品は『標準・価格重視・機能重視』の3候補に分けると選びやすくなります。必要性がなければ買わない選択も含めて確認。",
            ],
            "threads": [
                "%sという話題。流行を見ると焦りやすいですが、手持ち品で代用できるなら購入しないのも正解です。判断項目を整理しました。" % candidate.title
            ],
            "instagram": [
                "1枚目: %s｜買う・待つ・不要" % candidate.title,
                "2枚目: まず対象条件を確認",
                "3枚目: 手持ち品で代用できる？",
                "4枚目: 標準・価格・機能の3候補",
                "5枚目: 価格・在庫・保証を確認",
                "6枚目: 買わない選択肢",
                "7枚目: 詳細はプロフィールの記事へ",
            ],
        }
        return ArticleBundle(
            title=title,
            slug=slug,
            meta_description=meta,
            lead=lead,
            body_markdown=body,
            cta_blocks=ctas,
            social_assets=social,
            behavioral_principles=["処理流暢性", "自己関連性", "選択肢削減", "反論処理", "具体性"],
            objections=["必要性", "価格", "互換性", "返品・保証", "代替手段"],
            non_purchase_option="手持ち品・無料設定・公式案内で代用できる場合は購入しない",
            urgency_source=candidate.source_urls[0] if candidate.source_urls else "",
            evidence_urls=candidate.source_urls,
        )


class OpenAIArticleGenerator:
    """Optional paid adapter. It is never selected without OPENAI_API_KEY."""

    name = "openai-responses"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = os.environ["OPENAI_API_KEY"]

    @staticmethod
    def _schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "meta_description": {"type": "string"},
                "lead": {"type": "string"},
                "body_markdown": {"type": "string"},
                "cta_blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "offer_id": {"type": "string"},
                            "placeholder": {"type": "string"},
                        },
                        "required": ["label", "offer_id", "placeholder"],
                        "additionalProperties": False,
                    },
                },
                "social_assets": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "array", "items": {"type": "string"}},
                        "threads": {"type": "array", "items": {"type": "string"}},
                        "instagram": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["x", "threads", "instagram"],
                    "additionalProperties": False,
                },
                "behavioral_principles": {"type": "array", "items": {"type": "string"}},
                "objections": {"type": "array", "items": {"type": "string"}},
                "non_purchase_option": {"type": "string"},
                "urgency_source": {"type": "string"},
                "evidence_urls": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "title", "meta_description", "lead", "body_markdown", "cta_blocks",
                "social_assets", "behavioral_principles", "objections",
                "non_purchase_option", "urgency_source", "evidence_urls"
            ],
            "additionalProperties": False,
        }

    def generate(self, candidate: EventCandidate) -> ArticleBundle:
        payload = {
            "model": self.settings.openai_model,
            "reasoning": {"effort": "low"},
            "instructions": (
                "あなたは編集・行動設計部です。事実と推測を分け、広告表示、買わない選択肢、"
                "反論処理を含めます。偽の希少性、架空レビュー、恐怖の誇張は禁止です。"
                "与えられた出典と商品以外の事実を作らないでください。"
            ),
            "input": json.dumps(candidate, default=lambda obj: obj.__dict__, ensure_ascii=False),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "editorial_bundle",
                    "strict": True,
                    "schema": self._schema(),
                },
                "verbosity": "low",
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer %s" % self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw.get("output_text")
        if not text:
            parts = []
            for item in raw.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        parts.append(content.get("text", ""))
            text = "".join(parts)
        parsed = json.loads(text)
        parsed["slug"] = safe_slug("trend", candidate.event_id, parsed["title"])
        return ArticleBundle(**parsed)


def choose_generator(settings: Settings, allow_paid: bool = False):
    if allow_paid and os.getenv("OPENAI_API_KEY"):
        return OpenAIArticleGenerator(settings)
    return LocalArticleGenerator()
