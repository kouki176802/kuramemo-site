from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List

from .settings import load_dotenv


PRODUCT_SEARCH_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801"
ITEM_SEARCH_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401"
ITEM_RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"


@dataclass
class RakutenProduct:
    product_id: str
    name: str
    min_price: int
    max_price: int
    product_url: str
    affiliate_url: str
    image_url: str
    review_count: int = 0
    review_average: float = 0.0
    availability: int = 0
    postage_flag: int = 0
    shop_name: str = ""
    shop_of_the_year: int = 0
    affiliate_rate: float = 0.0
    rank: int = 0
    genre_id: str = ""


def parse_products(payload: Dict[str, Any]) -> List[RakutenProduct]:
    products: List[RakutenProduct] = []
    for wrapper in payload.get("Products", payload.get("products", [])):
        item = wrapper.get("Product", wrapper.get("product", wrapper)) if isinstance(wrapper, dict) else {}
        product_id = str(item.get("productId") or item.get("productNo") or item.get("jan") or "")
        name = str(item.get("productName") or item.get("name") or "")
        if not name:
            continue
        products.append(
            RakutenProduct(
                product_id=product_id,
                name=name,
                min_price=int(item.get("salesMinPrice") or item.get("minPrice") or item.get("minPriceNum") or 0),
                max_price=int(item.get("salesMaxPrice") or item.get("maxPrice") or item.get("maxPriceNum") or 0),
                product_url=str(item.get("productUrlPC") or item.get("productUrl") or ""),
                affiliate_url=str(item.get("affiliateUrl") or ""),
                image_url=str(item.get("mediumImageUrl") or item.get("imageUrl") or ""),
                review_count=int(item.get("reviewCount") or 0),
                review_average=float(item.get("reviewAverage") or 0),
            )
        )
    return products


def parse_items(payload: Dict[str, Any]) -> List[RakutenProduct]:
    products: List[RakutenProduct] = []
    for wrapper in payload.get("Items", payload.get("items", [])):
        item = wrapper.get("Item", wrapper.get("item", wrapper)) if isinstance(wrapper, dict) else {}
        name = str(item.get("itemName") or item.get("name") or "")
        if not name:
            continue
        medium_images = item.get("mediumImageUrls") or []
        image_url = ""
        if medium_images:
            first = medium_images[0]
            image_url = str(first.get("imageUrl") if isinstance(first, dict) else first)
        products.append(
            RakutenProduct(
                product_id=str(item.get("itemCode") or ""),
                name=name,
                min_price=int(item.get("itemPrice") or item.get("itemPriceMin3") or 0),
                max_price=int(item.get("itemPriceMax3") or 0),
                product_url=str(item.get("itemUrl") or ""),
                affiliate_url=str(item.get("affiliateUrl") or item.get("itemUrl") or ""),
                image_url=image_url,
                review_count=int(item.get("reviewCount") or 0),
                review_average=float(item.get("reviewAverage") or 0),
                availability=int(item.get("availability") or 0),
                postage_flag=int(item.get("postageFlag") or 0),
                shop_name=str(item.get("shopName") or ""),
                shop_of_the_year=int(item.get("shopOfTheYearFlag") or 0),
                affiliate_rate=float(item.get("affiliateRate") or 0),
                rank=int(item.get("rank") or 0),
                genre_id=str(item.get("genreId") or ""),
            )
        )
    return products


class RakutenProductClient:
    def __init__(self) -> None:
        load_dotenv()
        self.application_id = os.environ["RAKUTEN_APPLICATION_ID"]
        self.access_key = os.environ["RAKUTEN_ACCESS_KEY"]
        self.affiliate_id = os.getenv("RAKUTEN_AFFILIATE_ID", "")
        self.referer = os.getenv("RAKUTEN_REFERER", "https://x.com/m0506k")
        # Rakuten APIs return 429 when ranking, scouting and audits overlap.
        # Keep one client-wide start interval and retry only transient failures.
        self.min_request_interval = max(0.0, float(os.getenv("RAKUTEN_REQUEST_INTERVAL", "1.1")))
        self.max_retries = max(0, int(os.getenv("RAKUTEN_MAX_RETRIES", "2")))
        self._request_lock = threading.Lock()
        self._last_request_started = 0.0

    def _fetch_json(self, request: urllib.request.Request, timeout: int) -> Dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            with self._request_lock:
                wait = self.min_request_interval - (time.monotonic() - self._last_request_started)
                if wait > 0:
                    time.sleep(wait)
                self._last_request_started = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                transient = error.code == 429 or 500 <= error.code < 600
                if not transient or attempt >= self.max_retries:
                    raise
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = min(8.0, 1.5 * (2 ** attempt))
                time.sleep(max(self.min_request_interval, delay))
        raise RuntimeError("楽天APIの再試行上限に到達しました")

    def search(self, keyword: str, limit: int = 10) -> List[RakutenProduct]:
        params = {
            "applicationId": self.application_id,
            "accessKey": self.access_key,
            "format": "json",
            "keyword": keyword,
            "hits": max(1, min(limit, 30)),
        }
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id
        url = "%s?%s" % (PRODUCT_SEARCH_ENDPOINT, urllib.parse.urlencode(params))
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TrendCommerceBot/0.1",
                "Referer": self.referer,
            },
        )
        return parse_products(self._fetch_json(request, timeout=30))

    def search_items(self, keyword: str, limit: int = 10, sort: str = "-reviewCount") -> List[RakutenProduct]:
        params = {
            "applicationId": self.application_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": 2,
            "keyword": keyword,
            "hits": max(1, min(limit, 30)),
            "availability": 1,
            "hasReviewFlag": 1,
            "imageFlag": 1,
            "carrier": 0,
            "sort": sort,
            "elements": ",".join([
                "itemName", "itemCode", "itemPrice", "itemUrl", "affiliateUrl",
                "mediumImageUrls", "availability", "postageFlag", "shopOfTheYearFlag",
                "reviewCount", "reviewAverage", "affiliateRate", "shopName",
            ]),
        }
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id
        url = "%s?%s" % (ITEM_SEARCH_ENDPOINT, urllib.parse.urlencode(params))
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TrendCommerceBot/0.1",
                "Referer": self.referer,
            },
        )
        return parse_items(self._fetch_json(request, timeout=30))

    def ranking_items(
        self,
        genre_id: str = "",
        period: str = "realtime",
        page: int = 1,
    ) -> List[RakutenProduct]:
        """Return products backed by Rakuten Ichiba ranking data."""
        params = {
            "applicationId": self.application_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": 2,
            "carrier": 0,
            "page": max(1, min(page, 34)),
            "period": period,
        }
        if genre_id:
            params["genreId"] = genre_id
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id
        url = "%s?%s" % (ITEM_RANKING_ENDPOINT, urllib.parse.urlencode(params))
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "TrendCommerceBot/0.2", "Referer": self.referer},
        )
        return parse_items(self._fetch_json(request, timeout=12))

    def lookup_item(self, item_code: str) -> List[RakutenProduct]:
        """Fetch one currently sold item by Rakuten shop:item itemCode."""
        params = {
            "applicationId": self.application_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": 2,
            "itemCode": item_code,
            "availability": 1,
            "imageFlag": 1,
            "carrier": 0,
            "elements": ",".join([
                "itemName", "itemCode", "itemPrice", "itemUrl", "affiliateUrl",
                "mediumImageUrls", "availability", "postageFlag", "shopOfTheYearFlag",
                "reviewCount", "reviewAverage", "affiliateRate", "shopName",
            ]),
        }
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id
        url = "%s?%s" % (ITEM_SEARCH_ENDPOINT, urllib.parse.urlencode(params))
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "TrendCommerceBot/0.1", "Referer": self.referer},
        )
        return parse_items(self._fetch_json(request, timeout=30))

    def search_shop_items(self, shop_code: str, keyword: str, limit: int = 30) -> List[RakutenProduct]:
        """Search inside one shop so a current URL can be matched safely."""
        params = {
            "applicationId": self.application_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": 2,
            "shopCode": shop_code,
            "keyword": keyword,
            "hits": max(1, min(limit, 30)),
            "availability": 0,
            "imageFlag": 1,
            "carrier": 0,
            "field": 0,
            "elements": ",".join([
                "itemName", "itemCode", "itemPrice", "itemUrl", "affiliateUrl",
                "mediumImageUrls", "availability", "postageFlag", "shopOfTheYearFlag",
                "reviewCount", "reviewAverage", "affiliateRate", "shopName",
            ]),
        }
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id
        url = "%s?%s" % (ITEM_SEARCH_ENDPOINT, urllib.parse.urlencode(params))
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "TrendCommerceBot/0.1", "Referer": self.referer},
        )
        return parse_items(self._fetch_json(request, timeout=30))
