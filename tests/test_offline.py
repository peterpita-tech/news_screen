"""離線測試：以假回應驗證解析器、指標計算與完整建置流程（不需網路）。執行：python -m unittest discover tests"""
import json
import unittest
from unittest import mock

from dashboard import build, fetchers, news

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Oil prices surge as Iran tensions escalate - Reuters</title><link>https://x/1</link>
<pubDate>Sat, 10 Oct 2026 08:00:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>
<item><title>\xe5\x8f\xb0\xe7\xa9\x8d\xe9\x9b\xbb\xe4\xb8\x8a\xe4\xbf\xae\xe8\xb3\x87\xe6\x9c\xac\xe6\x94\xaf\xe5\x87\xba</title><link>https://x/2</link></item>
</channel></rss>"""

YAHOO = json.dumps({"chart": {"result": [{"meta": {"currency": "USD", "shortName": "Test", "regularMarketPrice": 101.0},
                                          "timestamp": [1760000000 + i * 86400 for i in range(5)],
                                          "indicators": {"quote": [{"close": [100, None, 99, 100, 100.5]}]}}]}}).encode()

FRED = b"observation_date,DGS10\n2026-10-08,4.10\n2026-10-09,.\n2026-10-10,4.12\n"


class ParserTests(unittest.TestCase):
    def test_rss(self):
        with mock.patch.object(fetchers, "http_get", return_value=RSS):
            items = fetchers.rss_items("u", "Google News", "en")
        self.assertEqual(items[0]["title"], "Oil prices surge as Iran tensions escalate")
        self.assertEqual(items[0]["source"], "Reuters")
        self.assertEqual(items[0]["time"], "2026-10-10T08:00:00Z")
        self.assertEqual(len(items), 2)

    def test_yahoo(self):
        with mock.patch.object(fetchers, "http_get", return_value=YAHOO):
            h = fetchers.yahoo_history("TEST")
        self.assertEqual(len(h["close"]), 4)
        self.assertEqual(h["close"][-1], 101.0)  # 以盤中價覆蓋最後一根

    def test_fred(self):
        with mock.patch.object(fetchers, "http_get", return_value=FRED):
            s = fetchers.fred_series("DGS10")
        self.assertEqual(s, [("2026-10-08", 4.10), ("2026-10-10", 4.12)])

    def test_news_tagging(self):
        it = news.tag_item({"title": "Oil prices surge as Iran tensions escalate", "lang": "en", "time": "", "source": "", "link": ""})
        oil = [t for t in it["tags"] if t["theme"] == "oil_mideast"][0]
        self.assertEqual(oil["dir"], 1)
        self.assertIn("XOM", it["benefit"])
        self.assertIn("DAL", it["hurt"])
        it = news.tag_item({"title": "Fed signals rate cuts, yields fall", "lang": "en", "time": "", "source": "", "link": ""})
        fed = [t for t in it["tags"] if t["theme"] == "fed_rates"][0]
        self.assertEqual(fed["dir"], -1)
        self.assertIn("TLT", it["benefit"])


class BuildTests(unittest.TestCase):
    def test_demo_build(self):
        d = build.collect(demo=True)
        self.assertGreater(d["counts"]["tickers"], 150)
        keys = {r["key"] for r in d["indicators"]}
        for k in ("hy_oas", "taiex_bias", "us10y", "vix", "dxy", "sahm", "erp", "spx_pe", "breadth"):
            self.assertIn(k, keys)
        self.assertIn(d["scenario"]["best"], {"goldilocks", "overheat", "recession", "stagflation"})
        json.dumps(d, ensure_ascii=False)  # 可序列化

    def test_manual_values_flow(self):
        manual = {"spx_fwd_pe": {"value": 23.0, "asof": "2026-10-09"}, "ndc_signal": {"value": 39, "asof": "2026-09-27"}}
        with mock.patch.object(build, "load_manual", return_value=manual):
            d = build.collect(demo=True)
        by = {r["key"]: r for r in d["indicators"]}
        self.assertEqual(by["spx_pe"]["level"], 2)
        self.assertEqual(by["ndc_signal"]["status"], "紅燈（過熱）")
        self.assertIsNotNone(by["erp"]["value"])


if __name__ == "__main__":
    unittest.main()
