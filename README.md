# 12-18 個月市場熱點預見與資訊自動收集系統

本系統是一套基於大師中期投資思維（**產品週期供應鏈洗牌**、**12-18個月能見度推演**、**高頻價格與營收 YoY 拐點預判**）所設計的自動化市場監控與多 Agent 研判系統。

系統透過模擬與收集高頻產業價格、Design Win 時程、歷史月度營收基期，並利用 LangGraph 狀態機協同三位專家 Agent（供應鏈專家、價格營收專家、新聞情緒專家）進行分析與 Self-Correction（自我修正）品質把關，最終自動生成繁體中文的學術級市場可行性評估報告。

---

## 1. 系統架構與設計思維

本系統高度整合了三位優秀投資人的中期投資心法：
1. **Product Cycle 的供應鏈洗牌效應**：追蹤主流架構（如 NVIDIA Blackwell $\rightarrow$ Vera Rubin $\rightarrow$ Feynman）物理限制突破後，特定零組件（如散熱、CPO 矽光子）在系統中的 **內含價值 (Content Value)** 變動，以及舊供應鏈的替代歸零風險。
2. **12-18 個月的能見度推演**：在大眾仍為當代產品放量歡呼時，多 Agent 系統已提前拆解下一代架構規格，並透過高頻封測稼動率等 Channel Check 數據進行動態修正。
3. **短期催化劑與新聞預警**：
   - 抓取 **高頻價格走勢**（如記憶體現貨價、材料價格）作為資金流入的先行 Catalyst。
   - 基於 **「去年低營收基期」** 與 **「今年出貨放量」**，模擬未來 3 個月營收年增率 (YoY) 即將爆發的拐點，在新聞滿天飛前 2-3 個月悄悄潛伏，並於散戶興奮時獲利了結。

---

## 2. 專案目錄結構

```text
.
├── .github/
│   └── workflows/
│       └── weekly_research_scheduler.yml  # 每週一自動化運行排程 (Cron + DST 檢查 + Keep-alive)
├── docs/
│   ├── adr/
│   │   ├── 0001-record-architecture-decisions.md
│   │   └── 0002-market-hotspot-anticipation-architecture.md  # 系統架構決策紀錄 (ADR)
│   ├── prd_market_hotspot_system.md       # 產品需求文件 (PRD)
│   └── architecture_and_cost_analysis.md  # 架設與每週運行 Token 成本評估報告
├── reports/                               # 產出的市場可行性報告存放目錄 (Markdown)
├── tests/                                 # 單元測試 (驗證監控器與狀態機流轉)
│   ├── test_monitor.py
│   └── test_agent_workflow.py
├── main_agent.py                          # LangGraph 狀態機與 Agent 節點邏輯
├── market_monitor.py                      # 數據收集、價值量變動與營收 YoY 拐點模擬引擎
├── requirements.txt                       # Python 必要依賴
├── AGENTS.md                              # 統一開發規範與紀律 (Antigravity & Claude 共享)
├── HANDOFF.md                             # 跨 Agent 交接狀態文檔
└── README.md                              # 本說明文件
```

---

## 3. 本地安裝與執行指南

### 3.1 環境配置
本專案建議使用 Python 3.10+ 環境。

1. **安裝依賴套件**：
   ```bash
   pip install -r requirements.txt
   ```
2. **設定環境變數**：
   系統撰寫報告與評審時預設使用 Google Gemini 3.1 Pro。請配置您的 API Key：
   - **Windows (PowerShell)**：
     ```powershell
     $env:GEMINI_API_KEY="your-api-key-here"
     ```
   - **Linux / macOS**：
     ```bash
     export GEMINI_API_KEY="your-api-key-here"
     ```
   > **備註**：若未檢測到 `GEMINI_API_KEY`，系統會自動嘗試呼叫本地執行的 Ollama (localhost:11434, 運行 gemma4)；若本地無服務，將自動降級至系統內建的高精度本地規則生成模版，以防排程中斷。

### 3.2 執行熱點分析
執行 `main_agent.py` 並指定目標板塊（例如 `CPO_Optical_Transceiver`）：
```bash
python main_agent.py --sector CPO_Optical_Transceiver
```
執行後，系統將運行 LangGraph 狀態機，三位專家將進行評估、Writer 撰寫報告、Critic 進行結構數據檢核（若缺失將自動回溯重構）。最終，產出的報告將被寫入 `reports/` 目錄，檔名格式為：
`reports/YYYY-MM-DD-<板塊名稱>-feasibility-report.md`。

### 3.3 執行單元測試
本專案使用 `unittest` 框架驗證數據正確性與狀態機流暢度：
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 4. DevOps 自動化排程

系統在 `.github/workflows/weekly_research_scheduler.yml` 中定義了每週一自動運行的流水線，具備以下上線保障機制：
- **美東時區守護 (DST Guard)**：動態檢查紐約時間，判斷當前是夏令時 (EDT) 還是冬令時 (EST)，自動報告與美股收盤後的時差對齊性。
- **防止 Action 停用 (Keep-Alive)**：GitHub 會在 Repo 超過 60 天無 commit 時停用 Cron 排程。為此，Workflow 執行完畢後會將最新報告自動 commit 並 push 回 Repo 預設分支，附帶 `[skip ci]` 標記，維持 Repo 活性。
- **DeadMan Watchdog**：在工作流開始與結束時，透過 `curl` 向 `deadmancheck.io` 發送 ping 請求，確保若流程掛死或執行失敗，管理員能第一時間收到警報。
