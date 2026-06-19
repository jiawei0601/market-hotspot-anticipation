# HANDOFF

> 兩個 agent 交接的唯一現況真相。離開前更新，接手前先讀。

- 最後更新：Antigravity (Gemini 3.5 Flash) @ 2026-06-19 09:18
- 目前任務 / 目標：建立 12-18 個月市場熱點預見與資訊自動收集系統 (已完成 GitHub Actions + GitHub Pages 無伺服器排程與發佈、績效/勝率追蹤與圖表標記、證交所每月營收真實數據對接、Bug與邊界安全防護、GitHub Actions 排程與執行模式優化)
- 已完成：
  - [x] 實作計畫 (Implementation Plan) 經用戶審查通過
  - [x] 撰寫 PRD 規格書 (`docs/prd_market_hotspot_system.md`)
  - [x] 撰寫架設與運作成本分析 (`docs/architecture_and_cost_analysis.md`)
  - [x] 配置專案統一規範 (`AGENTS.md`)
  - [x] 實作 `market_monitor.py` 數據收集與 YoY 營收拐點模擬器，並整合台灣證券交易所 (TWSE) 開放 API 獲取真實月營收
  - [x] 實作 `main_agent.py` LangGraph 狀態機（三專家 + 自我修正品質評審）
  - [x] 廢棄原有的單次排程，改為配置 `.github/workflows/daily_market_pipeline.yml` 自動排程 (支援每日 18:00 與每週一 07:30 雙排程機制)
  - [x] 寫入單元測試且全數通過 (8/8 OK)
  - [x] 第一版推送至 GitHub 私有倉庫 (`market-hotspot-anticipation`)
  - [x] 依用戶要求將 LLM 核心模型改為 **Gemini 3.1 Pro**，並將環境變數切換為 **GEMINI_API_KEY**，移除了 Ollama/Gemma4 本地 fallback 模擬以確保故障可視性
  - [x] 實作 `app.py` 與 `Procfile`，完成 Railway 雲端部署與 API 觸發機制配置
  - [x] 實作 `performance_tracker.py` 並對接狀態機與 API，實現觀察名單 (`watchlist.json`) 每日 K 線股價追蹤與系統勝率評估報告
  - [x] 實作 `/latest-report` 與 `/latest-performance` 網頁固定連結，以精美毛玻璃深色模式直接渲染最新 Markdown 報告
  - [x] 實作 `generate_static_pages.py` 並整合至 GitHub Actions 流水線，實現每週自動將報告編譯並部署至 GitHub Pages
  - [x] 根據 Double Review 結果，修復 yfinance 收盤價 NaN 問題與營收 YoY 逆推之極端值防護
  - [x] 將 K 線觀察資料取得時間加長至「往前三個月」，並在 ApexCharts K 線圖上清晰標記列入觀察的時間點與股價。
  - [x] 移除了 performance_tracker.py 中所有的 Console 輸出 emojis，避免 Windows cp950 編碼錯誤。
  - [x] 引入 `--daily-update` 與 `--weekly-report` 命令行參數，實現每日只更新價格數據，每週一生成評估報告的分流機制。
- 進行中（做到哪一步）：
  - 任務已全面完成。
- 下一步：
  - 由使用者確認 Git Commit & Push 狀態。
- 關鍵決策 + 為什麼：
  - 使用 `ChatGoogleGenerativeAI` 調用 `gemini-3.1-pro` 作為線上運行主力，並將環境變數對齊為 `GEMINI_API_KEY`。
  - 分流運行模式：`--daily-update` 只跑 `yfinance` 更新 watchlist 價格，不呼叫 LLM 狀態機，節省運算成本與 Actions 執行限額。
  - 網頁渲染 Markdown 採用前端 CDN 讀取 `marked.js` 的無伺服器架構，免去 Python 後端依賴包的編譯與維護成本，同時提供最精美的高級 HSL 毛玻璃深色主題。
- 雷區 / 別碰：
  - 注意 Windows 終端機編碼 (cp950) 的 stdout 輸出。代碼中已移除了 emojis 以防止 stdout編碼崩潰。
  - 在 GitHub Actions 中跑測試需指定合適的 python env，已設定 `python-version: '3.12'` 確保其依賴安裝與環境正確。
- 怎麼跑 / 怎麼測：
  - 每日價格追蹤更新：`python main_agent.py --daily-update`
  - 每週板塊掃描研判：`python main_agent.py --weekly-report --sector CPO_Optical_Transceiver` (需要 GEMINI_API_KEY)
  - 跑測試：`C:\Users\chang\AppData\Local\Programs\Python\Python312\python.exe -m unittest discover tests`
  - 運行 Web 伺服器：`python app.py` (預設 port: 8080，支援 POST `/run` 手動分析，並內建台灣時間週一 07:30 自動排程)
  - 檢視績效網頁：直接在瀏覽器訪問 `GET /latest-performance` 取得勝率與詳細表單，或 `GET /latest-report` 取得最新熱點可行性評估報告。

