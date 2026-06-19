# ADR 0004: Point-in-Time 資料以 git 追蹤、append-only 按月快照存儲

狀態：已採納

脈絡見 [ADR 0003](0003-market-monitor-synthetic-to-pit-engine.md)（A→B 的混合 PIT 策略）。`market_monitor.py` 原本無持久層（每次回傳記憶體 hardcoded dict）；走 B 需要一個能支撐「前向不可變累積 ＋ 歷史營收回填」的存儲層。專案既有信仰為 serverless／git 當資料庫／GitHub Actions／零成本（如 `watchlist.json`）。

## 決策
採 **git 追蹤、append-only、按月分檔的 JSON 快照**：

- 路徑如 `data/snapshots/YYYY-MM/{revenue,holdings,prices}.json`，由每月 GitHub Actions 抓取「月營收＋外資持股%＋收盤價」寫入。
- **不可變鐵律**：一份快照一旦寫入即**永不編輯**——這是前向 PIT 合法性的地基，`git log` 本身即不可竄改的時點證據。
- **CV 專家先驗**獨立為版本化表（如 `data/priors/content_value.json`），任何調整經 PR 留痕，直到有真實 teardown 來源。
- 回測引擎改讀此存檔，**不再讀** `market_monitor.py` 內的 hardcoded matrix；讀取時以 pandas／DuckDB 查詢扁平檔。

## 考慮過的替代方案
- **倉內 SQLite/DuckDB 單檔**：查詢力強，但 git 內為二進位 diff、不可讀、合併易爆、破壞「git 即稽核軌跡」。
- **外部 DB／雲端**：擴展性最佳，但打破零成本 serverless 信仰、引入憑證與維運負擔。

## 後果
- 回測可回溯的深度＝「可重建的營收歷史」；自有訊號則需時間前向累積才有效。
- repo 每月小幅成長（小型 JSON，可接受）。
- 不可變性需靠 code review 維護：CI 與人類**皆不得回頭編輯過去月份的快照**（只能新增當月）。
