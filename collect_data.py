#!/usr/bin/env python3
"""
Commodities Dashboard Data Collector — EIA + Yahoo Finance hybrid
- WTI/Brent/Henry Hub NG: EIA api.eia.gov 직접 (FRED 보다 1~2일 빠름) — 실패 시 FRED fallback
- Gold/Silver/Copper/Iron/Uranium: Yahoo Finance via yfinance

카테고리:
  귀금속: Gold (GC=F), Silver (SI=F)
  산업용: Copper (HG=F), Iron Ore (TIO=F)
  에너지: WTI · Brent · Henry Hub NG (EIA primary, FRED fallback)
  특수: Uranium (URA ETF proxy)

Output: commodities_data.js
Env: EIA_API_KEY (필수), FRED_API_KEY (fallback 용)
"""

import json, os, sys, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

EIA_API_KEY = os.environ.get("EIA_API_KEY", "").strip()
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
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


def fetch_eia(series_id, route, max_retries=3):
    """EIA v2 API direct. series_id = e.g. RWTC, RBRTE, RNGWHHD."""
    url = (f"https://api.eia.gov/v2/{route}/data/"
           f"?api_key={EIA_API_KEY}"
           f"&frequency=daily"
           f"&data[0]=value"
           f"&facets[series][]={series_id}"
           f"&sort[0][column]=period&sort[0][direction]=desc"
           f"&offset=0&length={OBSERVATION_LIMIT}")
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "commodities-dashboard/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            obs = data.get("response", {}).get("data", [])
            clean = []
            for o in obs:
                period = o.get("period")
                v = o.get("value")
                if period is None or v is None: continue
                try: clean.append({"date": period, "value": float(v)})
                except (ValueError, TypeError): continue
            return clean
        except Exception as e:
            last_err = e
            print(f"  EIA({series_id}) retry {attempt+1}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"EIA({series_id}) failed: {last_err}")


def fetch_yahoo(ticker, max_retries=3):
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


# (key, label, category, primary_source, primary_id, primary_route|None, fallback_source, fallback_id)
ITEMS = [
    ("GOLD",    "Gold (XAU/USD)",         "precious",   "yahoo", "GC=F",     None,                         None, None),
    ("SILVER",  "Silver (XAG/USD)",       "precious",   "yahoo", "SI=F",     None,                         None, None),
    ("COPPER",  "Copper (COMEX, $/lb)",   "industrial", "yahoo", "HG=F",     None,                         None, None),
    ("IRON",    "Iron Ore 62%Fe (TIO=F)", "industrial", "yahoo", "TIO=F",    None,                         None, None),
    ("WTI",     "WTI Crude ($/bbl)",      "energy",     "eia",   "RWTC",     "petroleum/pri/spt",          "fred", "DCOILWTICO"),
    ("BRENT",   "Brent Crude ($/bbl)",    "energy",     "eia",   "RBRTE",    "petroleum/pri/spt",          "fred", "DCOILBRENTEU"),
    ("NG",      "Henry Hub NG ($/MMBtu)", "energy",     "eia",   "RNGWHHD",  "natural-gas/pri/fut",        "fred", "DHHNGSP"),
    ("URANIUM", "Uranium (URA ETF proxy)","specialty",  "yahoo", "URA",      None,                         None, None),
]


def fetch_one(item):
    key, label, cat, p_src, p_id, p_route, f_src, f_id = item
    used = None
    obs = []
    try:
        if p_src == "eia":
            obs = fetch_eia(p_id, p_route)
            used = "EIA"
        elif p_src == "yahoo":
            obs = fetch_yahoo(p_id)
            used = "Yahoo"
        elif p_src == "fred":
            obs = fetch_fred(p_id)
            used = "FRED"
    except Exception as e:
        print(f"  ✗ {key} primary ({p_src}) 실패: {e}", file=sys.stderr)
        if f_src and f_id:
            try:
                if f_src == "fred":
                    obs = fetch_fred(f_id)
                    used = "FRED (fallback)"
            except Exception as e2:
                print(f"  ✗ {key} fallback ({f_src}) 도 실패: {e2}", file=sys.stderr)
                used = "FAIL"
    return key, label, cat, p_src if used else "FAIL", p_id, used or "FAIL", obs


def main():
    if not EIA_API_KEY and not FRED_API_KEY:
        print("ERROR: 둘 다 없음 (EIA_API_KEY 또는 FRED_API_KEY 중 하나 필요)", file=sys.stderr)
        sys.exit(1)

    print(f"Collecting {len(ITEMS)} commodities (EIA primary for energy, Yahoo for others)...")
    series_data = {}
    metadata = {}
    with ThreadPoolExecutor(max_workers=4) as exe:
        futs = {exe.submit(fetch_one, it): it[0] for it in ITEMS}
        for fut in as_completed(futs):
            key, label, cat, p_src, p_id, used, obs = fut.result()
            series_data[key] = obs
            metadata[key] = {"source": used, "id": p_id, "category": cat, "label": label}
            latest = obs[0]['date'] if obs else 'N/A'
            print(f"  {'✓' if obs else '✗'} {key}: {len(obs)} obs (latest: {latest}, source: {used})")

    for req in REQUIRED:
        if not series_data.get(req):
            print(f"ABORT: required '{req}' empty.", file=sys.stderr)
            sys.exit(1)

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
    print(f"\nWrote {OUTPUT_PATH} ({len(js)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
