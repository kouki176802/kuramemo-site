from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Dict

from .models import ArticleBundle


class WordPressPublisher:
    """Paid-hosting adapter. The public method defaults to draft and refuses publish."""

    def __init__(self) -> None:
        self.base_url = os.environ["WORDPRESS_BASE_URL"].rstrip("/")
        self.username = os.environ["WORDPRESS_USERNAME"]
        self.password = os.environ["WORDPRESS_APPLICATION_PASSWORD"]

    def create_draft(self, bundle: ArticleBundle) -> Dict[str, object]:
        endpoint = "%s/wp-json/wp/v2/posts" % self.base_url
        payload = {
            "title": bundle.title,
            "content": bundle.body_markdown,
            "excerpt": bundle.meta_description,
            "slug": bundle.slug,
            "status": "draft",
        }
        token = base64.b64encode((self.username + ":" + self.password).encode("utf-8")).decode("ascii")
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Basic %s" % token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

