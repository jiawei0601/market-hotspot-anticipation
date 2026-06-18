# HANDOFF

> 兩個 agent 交接的唯一現況真相。離開前更新，接手前先讀。

- 最後更新：Antigravity (Gemini 3.5 Flash) @ 2026-06-18 22:02
- 目前任務 / 目標：建立 12-18 個月市場熱點預見與資訊自動收集系統 (已完成 Gemini 3.1 Pro 接入)
- 已完成：
  - [x] 實作計畫 (Implementation Plan) 經用戶審查通過
  - [x] 撰寫 PRD 規格書 (`docs/prd_market_hotspot_system.md`)
  - [x] 撰寫架設與運作成本分析 (`docs/architecture_and_cost_analysis.md`)
  - [x] 配置專案統一規範 (`AGENTS.md`)
  - [x] 實作 `market_monitor.py` 數據收集與 YoY 營收拐點模擬器
  - [x] 實作 `main_agent.py` LangGraph 狀態機（三專家 + 自我修正品質評審）
  - [x] 配置 `.github/workflows/weekly_research_scheduler.yml` 自動排程
  - [x] 寫入單元測試且全數通過 (7/7 OK)
  - [x] 第一版推送至 GitHub 私有倉庫 (`market-hotspot-anticipation`)
  - [x] 依用戶要求將 LLM 核心模型改為 **Gemini 3.1 Pro**，並將環境變數切換為 **GEMINI_API_KEY**
- 進行中（做到哪一步）：
  - 專案已處於 Production-ready 狀態。
- 下一步：
  - 提供系統展示，等待用戶進行下一步的功能擴展需求。
- 關鍵決策 + 為什麼：
  - 使用 `ChatGoogleGenerativeAI` 調用 `gemini-3.1-pro` 作為線上運行主力，並將環境變數對齊為 `GEMINI_API_KEY`。
  - 當無 API Key 時，系統自動回退至 `ChatOpenAI` 來調用本地端點 (Ollama) 或執行內建本地規則模版，以防排程中斷。
- 雷區 / 別碰：
  - 注意 Windows 終端機編碼 (cp950) 的 stdout 輸出。代碼中已移除了 emojis 以防止 stdout 編碼崩潰。
- 怎麼跑 / 怎麼測：
  - 執行掃描：`python main_agent.py --sector CPO_Optical_Transceiver` (需要 GEMINI_API_KEY)
  - 跑測試：`python -m unittest discover tests`
