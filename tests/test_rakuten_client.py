import io
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from trend_commerce.rakuten import RakutenProductClient


class _Response:
    def __init__(self, body=b'{"Items": []}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def _client(retries=2):
    client = RakutenProductClient.__new__(RakutenProductClient)
    client.min_request_interval = 0.0
    client.max_retries = retries
    client._request_lock = threading.Lock()
    client._last_request_started = 0.0
    return client


class RakutenClientRetryTests(unittest.TestCase):
    def test_retries_rate_limit_then_returns_json(self):
        error = urllib.error.HTTPError("https://example.test", 429, "rate limit", {}, io.BytesIO())
        with patch("trend_commerce.rakuten.urllib.request.urlopen", side_effect=[error, _Response()]) as opener:
            with patch("trend_commerce.rakuten.time.sleep") as sleeper:
                result = _client()._fetch_json(urllib.request.Request("https://example.test"), 3)
        self.assertEqual(result, {"Items": []})
        self.assertEqual(opener.call_count, 2)
        sleeper.assert_called_once()

    def test_does_not_retry_client_error(self):
        error = urllib.error.HTTPError("https://example.test", 400, "bad request", {}, io.BytesIO())
        with patch("trend_commerce.rakuten.urllib.request.urlopen", side_effect=error) as opener:
            with self.assertRaises(urllib.error.HTTPError):
                _client()._fetch_json(urllib.request.Request("https://example.test"), 3)
        self.assertEqual(opener.call_count, 1)


if __name__ == "__main__":
    unittest.main()
