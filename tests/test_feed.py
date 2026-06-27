import unittest

from trend_commerce.collectors import parse_feed
from trend_commerce.models import Source


class FeedTest(unittest.TestCase):
    def test_parse_rss(self):
        source = Source(name="test", url="test.xml", trust_level=5)
        data = b"""<?xml version='1.0'?><rss version='2.0'><channel><item>
        <title>New product</title><link>https://example.com/a</link>
        <description>Summary</description><pubDate>Wed, 24 Jun 2026 09:00:00 +0900</pubDate>
        </item></channel></rss>"""
        signals = parse_feed(data, source)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].title, "New product")
        self.assertEqual(signals[0].source_trust, 5)

    def test_parse_atom(self):
        source = Source(name="atom", url="atom.xml")
        data = b"""<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><entry>
        <title>AI feature</title><link href='https://example.com/ai'/><summary>New function</summary>
        <published>2026-06-24T09:00:00+09:00</published></entry></feed>"""
        signals = parse_feed(data, source)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].url, "https://example.com/ai")


if __name__ == "__main__":
    unittest.main()

