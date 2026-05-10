#!/usr/bin/env python3
"""
Commodities Dashboard Data Collector — 8 항목 일별
- FRED 3종: WTI, Brent, Henry Hub Natural Gas
- Yahoo Finance 5종: Gold (GC=F), Silver (SI=F), Copper (HG=F), Iron Ore (IO=F), Uranium ETF (URA)

카테고리:
  귀금속 (Precious): Gold, Silver
  산업용 (Industrial): Copper, Iron Ore
  에너지 (Energy): WTI, Brent, Natural Gas
  특수 (Specialty): Uranium (URA ETF proxy)

Output: commodities_data.js (window.COMMODITIES_DATA = {...})

Env: FRED_API_KEY (required, GitHub Secret)
"""

import json, os, sys, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()

# (key, source, source_id, category, label)
ITEMS = [
    ("GOLD",   "yahoo", "GC=F",        "precious",   "Gold (XAU/USD)"),
    ("SILVER", "yahoo", "SI=F",        "precious",   "Silver (XAG/USD)"),
    ("COPPER", "yahoo", "HG=F",        "industrial", "Copper (COMEX, $/lb)"),
    ("IRON",   "yahoo", "TIO=F",       "industrial", "Iron Ore 62%Fe (TIO=F)"),
    ("WTI",    "fred",  "DCOILWTICO",  "energy",     "WTI Crude ($/bbl)"),
    ("BRENT",  "fred",  "DCOILBRENTEU","energy",     "Brent Crude ($/bbl)"),
    ("NG",     "fred",  "DHHNGSP",     "energy",     "Henry Hub NG ($/MMBtu)"),
    ("URANIUM","yahoo", "URA",         "specialty",  "Uranium (URA ETF proxy)"),
]

OBSERVATION_LIMIT = 800
REQUIRED = {"WTI", "GOLD"}
OUTPUT_PATH = "commodities_data.js"


def fetch_fred(series_id, max_retries=4):
    url_base = "https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json",
              "limit": OBSERVATION_LIMIT, "sort_order": "desc"}
    url = url_base + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = json.loads(resp.read().decode())
                clean = []
                for o in data.get("observations", []):
                    v = o.get("value", "")
                    if v in (".", "", None): continue
                    try: clean.append({"date": o["date"], "value": float(v)})
                    except (ValueError, TypeError): continue
                return clean
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"FRED({series_id}) failed: {last_err}")


def fetch_yahoo(ticker, max_retries=3):
    """Yahoo Finance via yfinance (lazy import)."""
    import yfinance as yf
    last_err = None
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="3y", interval="1d", auto_adjust=False)
            if hist.empty:
                raise RuntimeError(f"empty data for {ticker}")
            obs = []
            for idx, row in hist.iterrows():
                close = row.get("Close")
                if close is None or (isinstance(close, float) and (close != close)):
                    continue
                obs.append({"date": idx.strftime("%Y-%m-%d"), "value": float(close)})
            obs.sort(key=lambda o: o["date"], reverse=True)
            return obs[:OBSERVATION_LIMIT]
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Yahoo({ticker}) failed: {last_err}")


def main():
    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set", file=sys.stderr); sys.exit(1)

    print(f"Collecting {len(ITEMS)} commodity series...")
    series_data = {}
    with ThreadPoolExecutor(max_workers=4) as exe:
        futs = {}
        for key, src, sid, cat, label in ITEMS:
            if src == "fred":
                futs[exe.submit(fetch_fred, sid)] = key
            else:
                futs[exe.submit(fetch_yahoo, sid)] = key
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                series_data[key] = fut.result()
                print(f"  ✓ {key}: {len(series_data[key])} obs")
            except Exception as e:
                print(f"  ✗ {key}: {e}", file=sys.stderr)
                series_data[key] = []

    for req in REQUIRED:
        if not series_data.get(req):
            print(f"ABORT: required '{req}' empty.", file=sys.stderr); sys.exit(1)

    metadata = {key: {"source": src, "id": sid, "category": cat, "label": label}
                for key, src, sid, cat, label in ITEMS}
    payload = {
        "series": series_data,
        "metadata": metadata,
        "categories": {
            "precious":   {"label": "귀금속",      "order": 1},
            "industrial": {"label": "산업용 금속",  "order": 2},
            "energy":     {"label": "에너지",      "order": 3},
            "specialty":  {"label": "특수",        "order": 4},
        },
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    js = "window.COMMODITIES_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",",":")) + ";\n"
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"Wrote {OUTPUT_PATH} ({len(js)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
