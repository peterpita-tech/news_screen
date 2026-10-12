"""產生靜態網站（GitHub Pages 用）：複製 web/ 並寫入最新 data.json 到 site/。
用法：python build_static.py [--demo] [--out site]
"""
import argparse
import shutil
from pathlib import Path

from dashboard import build

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", default="site")
    args = ap.parse_args()
    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    data = build.collect(demo=args.demo)
    build.write_all(out, data)
    (out / ".nojekyll").write_text("")
    c = data["counts"]
    print(f"完成：{out}  標的 {c['tickers']}/{c['universe']}、新聞 {c['news']}、FRED {c['fred']}/{c['fred_total']}、錯誤 {data['error_count']}")
    for e in data["errors"][:20]:
        print("  -", e)
    if c["tickers"] < c["universe"] * 0.5:
        raise SystemExit("行情抓取成功率過低，中止發布")


if __name__ == "__main__":
    main()
