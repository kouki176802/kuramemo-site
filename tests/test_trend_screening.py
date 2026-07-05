import unittest

from trend_commerce.rakuten import RakutenProduct, parse_items
from trend_commerce.trend_screening import (
    TrendObservation, TrendOpportunity, TrendRule, _deduplicate_opportunities,
    _blocked_observation, _market_label, _news_terms_match_rule,
    _observation_rule_excluded, _ranking_label, parse_google_trends,
)


class TrendScreeningTest(unittest.TestCase):
    def test_google_trends_keeps_country_news_and_traffic(self):
        payload = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item>
          <title>iPhone</title><ht:approx_traffic>5000+</ht:approx_traffic>
          <pubDate>Sat, 27 Jun 2026 01:10:00 -0700</pubDate>
          <ht:news_item><ht:news_item_title>New iPhone announced</ht:news_item_title>
          <ht:news_item_url>https://example.com/iphone</ht:news_item_url>
          <ht:news_item_source>Example News</ht:news_item_source></ht:news_item>
        </item></channel></rss>'''
        rows = parse_google_trends(payload, "JP")
        self.assertEqual(1, len(rows))
        self.assertEqual("日本", rows[0].country_name)
        self.assertEqual("5000+", rows[0].approx_traffic)
        self.assertEqual("Example News", rows[0].news_source)

    def test_rakuten_ranking_parser_keeps_rank(self):
        payload = {
            "Items": [{"itemName": "USB-C 急速充電器", "itemCode": "shop:item", "itemPrice": 2980,
                       "itemUrl": "https://example.com/item", "affiliateUrl": "https://example.com/affiliate",
                       "mediumImageUrls": ["https://example.com/image.jpg"], "rank": 7,
                       "reviewCount": 100, "reviewAverage": 4.5, "genreId": "564500"}]
        }
        rows = parse_items(payload)
        self.assertEqual(7, rows[0].rank)
        self.assertEqual("564500", rows[0].genre_id)

    def test_us_trend_uses_specific_search_rising_label(self):
        payload = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item>
          <title>heat wave</title><ht:approx_traffic>1000+</ht:approx_traffic>
          <pubDate>Sat, 27 Jun 2026 01:10:00 -0700</pubDate>
        </item></channel></rss>'''
        row = parse_google_trends(payload, "US")[0]
        self.assertEqual("アメリカ", row.country_name)
        self.assertIn("【アメリカで検索急上昇】", row.evidence_text)
        self.assertNotIn("SNS", row.evidence_text)

    def test_unknown_country_is_not_treated_as_japan(self):
        self.assertEqual("海外で注目", _market_label("OTHER", "海外"))

    def test_market_mix_keeps_overseas_and_japan_lanes(self):
        rule_a = TrendRule("heat", "季節", "heat", "暑さ", "人", ["暑さ"], ["扇風機"], "1", "家電")
        rule_b = TrendRule("beauty", "美容", "beauty", "美容", "人", ["美容"], ["化粧品"], "2", "美容")
        product_a = RakutenProduct("us-item", "扇風機", 1000, 1000, "u", "a", "i", rank=1)
        product_b = RakutenProduct("jp-item", "化粧品", 1000, 1000, "u", "a", "i", rank=1)
        us = TrendObservation("us", "Google Trends", "US", "アメリカ", "heat wave", "1000+", "", "", "", "")
        jp = TrendObservation("jp", "Google Trends", "JP", "日本", "美容", "1000+", "", "", "", "")
        selected = _deduplicate_opportunities([
            TrendOpportunity("a", rule_a, us, product_a, 80, "why", "Google Trends", ""),
            TrendOpportunity("b", rule_b, jp, product_b, 80, "why", "Google Trends", ""),
        ], 2)
        self.assertEqual(["overseas_watch", "japan_now"], [item.trend_scope for item in selected])

    def test_fallback_product_is_not_called_realtime_ranking(self):
        rule = TrendRule("heat", "季節", "heat", "暑さ", "人", [], [], "1", "家電")
        product = RakutenProduct("fallback", "扇風機", 1000, 1000, "u", "a", "i", review_count=100, review_average=4.5)
        self.assertEqual("日本で販売中・レビュー確認済みの関連候補", _ranking_label(product, rule))

    def test_generic_tube_food_news_is_not_fitness_evidence(self):
        rule = TrendRule(
            "fitness", "フィットネス", "home-training", "運動", "人",
            ["筋トレ", "トレーニング", "fitness"],
            ["トレーニングマット", "ダンベル", "チューブ", "フォームローラー"],
            "1", "スポーツ",
        )
        self.assertFalse(_news_terms_match_rule("練乳をチューブから飲むヨーグルト発売", rule))
        self.assertTrue(_news_terms_match_rule("自宅トレーニング用チューブの新商品", rule))

    def test_ascii_trigger_requires_word_boundary(self):
        rule = TrendRule("pc", "AI", "pc", "作業", "人", ["PC"], ["マウス"], "1", "PC")
        self.assertFalse(_news_terms_match_rule("space designの新商品", rule))
        self.assertTrue(_news_terms_match_rule("pc 作業向け新商品", rule))

    def test_scraped_news_source_is_blocked(self):
        item = TrendObservation(
            "spam", "Google News", "JP", "日本", "防災グッズ新商品", "",
            "防災グッズ新商品", "https://example.invalid", "richardajkeys.com", "",
        )
        self.assertTrue(_blocked_observation(item))

    def test_unrelated_toy_and_vehicle_matches_are_excluded(self):
        self.assertTrue(_observation_rule_excluded("木製の知育玩具 ダンベルベル", "fitness"))
        self.assertTrue(_observation_rule_excluded("電動スクーターの充電器", "charging"))


if __name__ == "__main__":
    unittest.main()
