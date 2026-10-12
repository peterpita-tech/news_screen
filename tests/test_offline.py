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


class MarketAutofillTests(unittest.TestCase):
    def test_parse_zs_data(self):
        from dashboard import market
        html = '<html><script>window.ZS_DATA = {"date":"2026-10-09","rows":[{"code":"2330","name":"台積電","s":"a};b"}]};</script></html>'
        d = market.parse_zs_data(html)
        self.assertEqual(d["rows"][0]["code"], "2330")

    def test_parse_chain(self):
        from dashboard import market
        themes = [{"group": "先進封裝", "items": [{"name": "CoWoS", "md": "## 上游 (1)\n\n- **3167 大量** (x)\n\n## 下游 (1)\n- **3131 弘塑** (y)\n## 相關公司 (1)\n- **3037 欣興** (z)"}]}]
        c = market.parse_chain(themes)
        self.assertEqual(c["3167"][0]["pos"], "上游")
        self.assertEqual(c["3131"][0]["pos"], "下游")
        self.assertEqual(c["3037"][0]["pos"], "相關")

    def test_extractors(self):
        from dashboard import autofill as a
        self.assertEqual(a._ndc("8月景氣燈號續亮紅燈 分數38分"), 38)
        self.assertEqual(a._ism("ISM manufacturing PMI rises to 49.8 in September"), 49.8)
        self.assertEqual(a._fut_oi("外資台指期淨空單增至32,150口"), -32150)
        self.assertEqual(a._export("9月外銷訂單年減3.2%"), -3.2)
        self.assertEqual(a._pct_in(100, 220)("大盤融資維持率降至158.3%"), 158.3)
        self.assertIsNone(a._ndc("景氣燈號 100分"))

    def test_merge_prefers_newer(self):
        from dashboard import autofill as a
        manual = {"ism_pmi": {"value": 48.0, "asof": "2026-08-01"}, "ndc_signal": {"value": None, "asof": None}}
        auto = {"ism_pmi": {"value": 49.5, "asof": "2026-10-01", "note": "自動"}, "ndc_signal": {"value": 33, "asof": "2026-09-27", "note": "自動"}}
        m = a.merge(manual, auto)
        self.assertEqual(m["ism_pmi"]["value"], 49.5)
        self.assertEqual(m["ndc_signal"]["value"], 33)
        m = a.merge({"ism_pmi": {"value": 48.0, "asof": "2026-11-01"}}, auto)
        self.assertEqual(m["ism_pmi"]["value"], 48.0)

    def test_ttm_yoy(self):
        from dashboard import autofill as a
        pts = [(f"2025-0{i}-30", 10.0) for i in range(1, 5)] + [(f"2026-0{i}-30", 12.0) for i in range(1, 5)]
        self.assertAlmostEqual(a._ttm_yoy(pts)[0], 20.0)
