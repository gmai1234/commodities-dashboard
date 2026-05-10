# commodities-dashboard

원자재 대시보드 — 8 항목 일별 (귀금속·산업용·에너지·특수)

| 카테고리 | 항목 | 소스 |
|---|---|---|
| 귀금속 | Gold (XAU), Silver (XAG) | Yahoo Finance |
| 산업용 | Copper (HG=F), Iron Ore (TIO=F) | Yahoo Finance |
| 에너지 | WTI, Brent, Natural Gas | FRED |
| 특수 | Uranium (URA ETF proxy) | Yahoo Finance |

GitHub Actions cron 일 2회 (08·20 KST) 자동 갱신.

**Live**: <https://gmai1234.github.io/commodities-dashboard/>
**데이터**: <https://gmai1234.github.io/commodities-dashboard/commodities_data.js> (글로벌 `window.COMMODITIES_DATA`)
