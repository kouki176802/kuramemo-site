from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .database import transaction
from .models import Signal, Source
from .settings import ROOT, Settings
from .utils import canonicalize_url, stable_hash, strip_markup


def load_sources(path: Optional[Path] = None) -> List[Source]:
    source_path = path or ROOT / "config" / "sources.json"
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    return [Source(**item) for item in raw]


def _read_bytes(url: str, timeout: int = 15) -> bytes:
    if url.startswith("http://") or url.startswith("https://"):
        request = urllib.request.Request(url, headers={"User-Agent": "TrendCommerceBot/0.1 (+local MVP)"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    path = Path(url)
    if not path.is_absolute():
        path = ROOT / path
    return path.read_bytes()


def _text(element: Optional[ET.Element], default: str = "") -> str:
    if element is None:
        return default
    return "".join(element.itertext()).strip()


def _first(*elements: Optional[ET.Element]) -> Optional[ET.Element]:
    for element in elements:
        if element is not None:
            return element
    return None


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def parse_feed(data: bytes, source: Source) -> List[Signal]:
    root = ET.fromstring(data)
    signals: List[Signal] = []
    if root.tag.endswith("rss") or root.find("channel") is not None:
        for item in root.findall("./channel/item"):
            signals.append(
                Signal(
                    title=_text(item.find("title")),
                    url=_text(item.find("link")) or _text(item.find("guid")),
                    summary=strip_markup(_text(item.find("description"))),
                    published_at=_parse_date(_text(item.find("pubDate"))),
                    source_name=source.name,
                    source_trust=source.trust_level,
                    category_hint=source.category,
                )
            )
        return [signal for signal in signals if signal.title and signal.url]

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", namespace) + root.findall("entry"):
        link = _first(entry.find("atom:link", namespace), entry.find("link"))
        url = link.attrib.get("href", "") if link is not None else ""
        title = _text(_first(entry.find("atom:title", namespace), entry.find("title")))
        summary = strip_markup(_text(_first(entry.find("atom:summary", namespace), entry.find("summary"))))
        published = _text(_first(entry.find("atom:published", namespace), entry.find("published")))
        signals.append(
            Signal(
                title=title,
                url=url,
                summary=summary,
                published_at=_parse_date(published),
                source_name=source.name,
                source_trust=source.trust_level,
                category_hint=source.category,
            )
        )
    return [signal for signal in signals if signal.title and signal.url]


def upsert_source(conn, source: Source) -> int:
    conn.execute(
        """
        INSERT INTO sources(name, url, kind, category, trust_level, active)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            name=excluded.name,
            kind=excluded.kind,
            category=excluded.category,
            trust_level=excluded.trust_level,
            active=excluded.active
        """,
        (source.name, source.url, source.kind, source.category, source.trust_level, int(source.active)),
    )
    row = conn.execute("SELECT id FROM sources WHERE url = ?", (source.url,)).fetchone()
    return int(row["id"])


def insert_signal(conn, source_id: int, signal: Signal) -> bool:
    canonical = canonicalize_url(signal.url)
    content_hash = stable_hash(signal.title, signal.summary)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO raw_signals(
            source_id, title, url, canonical_url, summary, content_hash, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            signal.title,
            signal.url,
            canonical,
            signal.summary,
            content_hash,
            signal.published_at.isoformat() if signal.published_at else None,
        ),
    )
    return cursor.rowcount > 0


def collect_sources(settings: Settings, sources: Optional[Iterable[Source]] = None) -> Tuple[int, int, List[str]]:
    added = 0
    seen = 0
    errors: List[str] = []
    selected = list(sources or load_sources())
    with transaction(settings.database_path) as conn:
        for source in selected:
            if not source.active:
                continue
            source_id = upsert_source(conn, source)
            try:
                signals = parse_feed(_read_bytes(source.url), source)
            except Exception as exc:
                errors.append("%s: %s" % (source.name, exc))
                continue
            seen += len(signals)
            for signal in signals:
                added += int(insert_signal(conn, source_id, signal))
    return seen, added, errors


def add_manual_signal(settings: Settings, title: str, url: str, summary: str, category: str = "") -> bool:
    source = Source(name="CEO手動投入", url="manual://ceo", kind="manual", category=category, trust_level=4)
    signal = Signal(
        title=title,
        url=url,
        summary=summary,
        published_at=None,
        source_name=source.name,
        source_trust=source.trust_level,
        category_hint=category,
    )
    with transaction(settings.database_path) as conn:
        source_id = upsert_source(conn, source)
        return insert_signal(conn, source_id, signal)
