import unittest

from trend_commerce.utils import canonicalize_url, similarity, stable_hash, strip_markup


class UtilsTest(unittest.TestCase):
    def test_canonicalize_url_removes_tracking(self):
        url = "HTTPS://Example.COM/news/?utm_source=x&b=2&a=1#section"
        self.assertEqual(canonicalize_url(url), "https://example.com/news?a=1&b=2")

    def test_similarity_detects_related_japanese_titles(self):
        score = similarity("広い地域で猛暑となる見込み", "全国的な猛暑の見込みを発表")
        self.assertGreater(score, 0.4)

    def test_generic_ai_term_does_not_merge_unrelated_news(self):
        score = similarity("AIで写真を編集する新機能", "AI時代の教育方針を発表")
        self.assertLess(score, 0.42)

    def test_stable_hash_is_deterministic(self):
        self.assertEqual(stable_hash("a", "b"), stable_hash("a", "b"))
        self.assertNotEqual(stable_hash("a", "b"), stable_hash("a", "c"))

    def test_strip_markup_removes_executable_content(self):
        value = strip_markup("<p>安全</p><script>alert(1)</script><b>本文</b>")
        self.assertEqual(value, "安全 本文")


if __name__ == "__main__":
    unittest.main()
