import unittest

from trend_commerce.rakuten import parse_items
from trend_commerce.trend_screening import parse_google_trends


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


if __name__ == "__main__":
    unittest.main()
