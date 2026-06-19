# HANDOFF

> 兩個 agent 交接的唯一現況真相。離開前更新，接手前先讀。

- 最後更新：Antigravity (Gemini 3.1 Pro / GEMMA4) @ 2026-06-19 11:12
- 目前任務 / 目標：建立 12-18 個月市場熱點預見與資訊自動收集系統 (已完成 12 支選股池動態 PIT 擴展，蒙地卡羅壓力測試勝率驗證，季度再平衡回測格式優化，與極致毛玻璃 UI/UX 改版)
- 已完成：
  - [x] 實作計畫 (Implementation Plan) 經用戶審查通過
  - [x] 撰寫 PRD 規格書 (`docs/prd_market_hotspot_system.md`)
  - [x] 撰寫架設與運作成本分析 (`docs/architecture_and_cost_analysis.md`)
  - [x] 配置專案統一規範 (`AGENTS.md`)
  - [x] 擴展選股池範圍至 12 支核心台灣半導體、散熱、先進封裝及下世代去模組化龍頭
  - [x] 重構 `market_monitor.py` 的 `get_point_in_time_matrix` 函數，實作點時間 (Point-in-Time) 切片以防止未來數據生存者偏差
  - [x] 根據用戶要求對回測與觀察名單網頁進行排版：金額全部四捨五入顯示到整數，百分比限制精確顯示至小數點後第一位 (`.1f%`)
  - [x] 將標的名稱格式全面優化為 `1234.中文名稱` (如 `3131.弘塑`)，並應用於季度再平衡回測、蒙地卡羅、系統績效追蹤中
  - [x] 呼叫 UI/UX 工程師對網頁進行極致美化，升級為 radial-gradient 背景、現代字型系統、毛玻璃玻璃擬態容器 (Glassmorphism) 與呼吸狀態指示燈 (Pulsing Dot)
  - [x] 實作前端 JavaScript 後處理器，動態分析 marked.js 渲染後的表格單元，將特定交易狀態、百分比及股票標籤，無痛轉換為精緻且色彩豐富的 CSS 徽章 (Badges) 與等寬字型 (Fira Code)
  - [x] 更新 `performance_tracker.py` 與 `monte_carlo_analyzer.py` 使其報表百分比與個股格式對齊新格式
  - [x] 執行 Git Commit 與 Git Push，將所有最新程式碼推送至 GitHub 遠端
- 進行中（做到哪一步）：
  - 季度再平衡回測與網頁排版已全面完成且推送。
- 下一步：
  - 由 GitHub Pages 自動部署，即可訪問最新格式的季度再平衡回測網頁。
- 關鍵決策 + 為什麼：
  - 在 `get_point_in_time_matrix` 中使用 2015-2019 (6 支)、2020-2022 (9 支)、2023-2024 (10 支)、2025-2026 (12 支) 遞進式選股，確保歷史回測（如 2016 或 2021）不會包含 2026 時代才浮現的玻璃基板 (鈦昇) 或 CPO 光互連 (聯鈞)，防範生存者偏差。
  - 在 `pricing_revenue_expert_node` 移除了硬編碼的 `company_ids` 陣列，改為點時間動態解鎖，使得狀態機能夠支援回測時動態追蹤與分析不同的組合。
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

