from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class VideoCampaign:
    campaign_id: str
    name: str
    genre: str
    landing_url: str
    account_theme: str
    primary_audience: str
    angles: list[str]
    checks: list[str]
    ng_claims: list[str]
    disclosure: str
    notes: str


@dataclass(frozen=True)
class VideoContentPack:
    campaign: VideoCampaign
    theme: str
    hooks: list[str]
    script_blocks: list[tuple[str, str]]
    narration: str
    image_prompts: list[str]
    caption: str
    x_post: str
    hashtags: list[str]

    def to_markdown(self) -> str:
        lines = [
            f"# {self.campaign.name} 短尺動画素材パック",
            "",
            f"- 生成日: {date.today().isoformat()}",
            f"- 案件: {self.campaign.name}",
            f"- URL: {self.campaign.landing_url}",
            f"- テーマ: {self.theme}",
            f"- 表記: {self.campaign.disclosure}",
            "",
            "## フック案",
            "",
        ]
        lines.extend(f"- {hook}" for hook in self.hooks)
        lines.extend(["", "## 30秒台本", ""])
        for timing, body in self.script_blocks:
            lines.extend([f"### {timing}", "", body, ""])
        lines.extend(["## ナレーション原稿", "", self.narration, ""])
        lines.extend(["## 画像生成プロンプト", ""])
        lines.extend(f"{idx}. {prompt}" for idx, prompt in enumerate(self.image_prompts, start=1))
        lines.extend(["", "## SNSキャプション", "", self.caption, ""])
        lines.extend(["## X投稿", "", self.x_post, ""])
        lines.extend(["## ハッシュタグ", "", " ".join(self.hashtags), ""])
        lines.extend([
            "## 公開前チェック",
            "",
            "- 金額、キャンペーン、適用条件を公式LPまたはASP管理画面で確認した",
            "- 断定的な最安・必ず得・速度保証の表現を入れていない",
            "- 広告・PR表記を入れた",
            "- URLが正しい",
            "",
        ])
        return "\n".join(lines)


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def load_video_campaigns(path: Path) -> list[VideoCampaign]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    campaigns: list[VideoCampaign] = []
    for row in rows:
        campaigns.append(
            VideoCampaign(
                campaign_id=row["campaign_id"],
                name=row["name"],
                genre=row["genre"],
                landing_url=row["landing_url"],
                account_theme=row["account_theme"],
                primary_audience=row["primary_audience"],
                angles=_split_pipe(row["angles"]),
                checks=_split_pipe(row["checks"]),
                ng_claims=_split_pipe(row["ng_claims"]),
                disclosure=row["disclosure"],
                notes=row["notes"],
            )
        )
    return campaigns


def find_video_campaign(campaign_id: str, path: Path = Path("data/video_campaigns.csv")) -> VideoCampaign:
    for campaign in load_video_campaigns(path):
        if campaign.campaign_id == campaign_id:
            return campaign
    raise ValueError(f"campaign_idが見つかりません: {campaign_id}")


def generate_video_content_pack(
    campaign: VideoCampaign,
    *,
    news_context: str = "",
    angle: str = "",
) -> VideoContentPack:
    selected_angle = angle or (campaign.angles[0] if campaign.angles else campaign.genre)
    context = news_context.strip()
    context_prefix = f"{context}に関連して、" if context else ""
    context_hook = f"{context}の今こそ、" if context else ""
    checks = campaign.checks[:5]
    check_sentence = "、".join(checks)
    hooks = [
        f"{context_hook}{selected_angle}で先に見るべきポイント",
        f"{campaign.name}が気になる人ほど、月額だけで決めないで",
        f"{campaign.primary_audience}へ。契約前に見るポイントを整理します",
    ]
    script_blocks = [
        ("0〜3秒", hooks[0]),
        ("3〜8秒", f"{campaign.genre}は、安そうに見えても条件で総額が変わりやすいジャンルです。"),
        ("8〜20秒", f"{campaign.name}を候補にするなら、{check_sentence}を先に確認します。条件が合えば候補になりますが、全員向けとは限りません。"),
        ("20〜30秒", f"最新条件は公式ページで確認してください。{campaign.landing_url} {campaign.disclosure}。"),
    ]
    narration = (
        f"{context_prefix}{campaign.name}を候補にする前に、月額だけで決めないでください。"
        f"{campaign.genre}は、提供条件やキャンペーン条件、解約時費用で実際の総額が変わりやすいです。"
        f"まず確認するのは、{check_sentence}です。"
        f"条件が合う人には候補になりますが、全員に合うわけではありません。"
        f"最新条件は公式ページで確認してください。{campaign.disclosure}。"
    )
    image_prompts = [
        "Vertical 9:16 clean lifestyle illustration, Japanese adult reviewing monthly internet or fixed cost bill on smartphone, modern apartment, no readable text, no logos",
        "Vertical 9:16 person comparing home internet options on tablet, calm thoughtful expression, blue-white clean design, no readable text, no logos",
        "Vertical 9:16 minimal checklist icons for service area, total monthly cost, construction fee, campaign conditions, cancellation cost, no readable text, no logos",
        "Vertical 9:16 cozy living room, person using laptop and smartphone comfortably, router on shelf, calm bright mood, no brand logos",
        "Vertical 9:16 friendly guide character pointing gently to smartphone checklist, soft blue background, no readable text, no logos",
    ]
    caption = (
        f"{context_prefix}{campaign.name}を候補にするなら、月額だけでなく条件まで確認。\n"
        f"見るポイントは、{check_sentence}。\n"
        "条件が合う人には候補になりますが、全員向けではありません。\n\n"
        f"詳しくは {campaign.landing_url}\n{campaign.disclosure}"
    )
    x_post = (
        f"{hooks[0]}\n\n"
        f"{campaign.name}を見るなら、月額だけではなく\n"
        + "\n".join(f"・{item}" for item in checks)
        + "\nまで確認。\n\n"
        "条件が合う人には候補ですが、全員向けではありません。\n"
        f"{campaign.landing_url}\n\n"
        f"{campaign.disclosure}"
    )
    hashtags = ["#通信費見直し", "#固定費削減", "#光回線", f"#{campaign.name}", "#節約"]
    return VideoContentPack(
        campaign=campaign,
        theme=campaign.account_theme,
        hooks=hooks,
        script_blocks=script_blocks,
        narration=narration,
        image_prompts=image_prompts,
        caption=caption,
        x_post=x_post,
        hashtags=hashtags,
    )


def write_video_content_pack(
    campaign_id: str,
    output: Path,
    *,
    news_context: str = "",
    angle: str = "",
    campaigns_path: Path = Path("data/video_campaigns.csv"),
) -> Path:
    campaign = find_video_campaign(campaign_id, campaigns_path)
    pack = generate_video_content_pack(campaign, news_context=news_context, angle=angle)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(pack.to_markdown(), encoding="utf-8")
    return output
