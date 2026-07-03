# HANDOFF

> 兩個 agent 交接的唯一現況真相。離開前更新，接手前先讀。

- 最後更新：Claude Code (Fable 5 指揮 + sonnet/haiku 分工) @ 2026-07-04
- 目前任務 / 目標：全專案審查後整組修正（回測口徑、訊號誠實化、判定 bug、repo 衛生、README 決策流程文件化）。**已完成，32 tests 全綠。**

## 已完成（2026-07-04 本輪）

### 回測引擎口徑統一與誠實化（backtest_engine.py / monte_carlo_analyzer.py）
- **固定持有期出場**：backtest_engine 原無出場規則（報酬=到 --end-date 當天，各標的持有期不一致）→ 新增 `resolve_fixed_holding_exits()`，統一 `HOLDING_PERIOD_WEEKS=52` 與 monte_carlo 一致；未滿 52 週標 `tracking_incomplete`（勝率分母排除）。
- **交易成本**：兩引擎統一常數 `FEE_RATE_BUY/SELL=0.1425%`、`TAX_RATE=0.3%`、`SLIPPAGE_RATE=0.1%/邊`＋`apply_net_return()`；報告併陳毛/淨報酬與成本假設。
- **缺資料顯式化**：yfinance 抓不到不再靜默回 0.0，改回傳 `(value, missing)`；缺資料標的列入報告清單、排除於勝率分母（進場缺價與出場缺價單一來源計數，不重複）。防護：`entry_price<=0`、期間早於進場日、None 欄位過濾。
- **口徑註記**：monte_carlo 組合 30% vs 個股 15% 勝率門檻為不同定義，兩報告互相註明。
- **非證據警語**：universe 12 檔為事後選定名單 → 報告抬頭明示「回測勝率不構成策略證據，僅供機制驗證」。

### 訊號與報告誠實化（market_monitor.py / main_agent.py）
- **【核心 bug 修正】黃金標的判定統一**：`run_hotspot_scan` 原有第二套未文件化寬鬆門檻（`consensus<70 and |yoy|>30`，這是鈦昇 64.6 被誤標「黃金潛伏」的根因）→ 刪除，一律讀 `is_golden_accumulation_target`（單一真相來源，CONSENSUS_MAX=60）。
- **機械外推標示**：未來 3 個月 YoY 投影＝末值×固定係數（[1.05,1.15,1.35]/[1.10,1.25,1.50]），非模型預測 → 結果加 `projection_note`，LLM prompt 明文禁止描述為基本面預測。
- **Consensus 整數化**：12 檔橫斷面 percentile 一階≈8.3 分，小數精度是假精度 → `_compute_consensus` 輸出整數＋`granularity_note` 粗粒度警語。
- **Backlog 標示**：板塊層代理訊號（equipment 月營收 YoY 中位數，全公司同值），非公司別訂單 → `backlog_signal_note`。

### 其他
- **performance_tracker.py**：抓價失敗/成功寫入 `price_fetch_status`（失敗不再只留 CI log）。「現價=進場價」經查**不是 bug**：本機 clone 落後 origin/main（CI 每日正常更新並 push），pull 即同步。
- **repo 衛生**：`portfolio_backtest.py`（不相干的美股 ETF 回測）移至 `C:\CLAUDE\investing\`；根目錄 `settings.json` 移至 `.claude/settings.local.json` 並 gitignore。
- **README**：新增「## 2. 決策推演流程」全章（資料層 PIT→三訊號→決策閘門→LangGraph 多專家→追蹤驗證→已知限制→端到端 mermaid 總覽）；修正過時的「TWSE 無歷史回溯、回測用模擬營收」敘述（Stage 2 已用 FinMind 真實回填）。
- **品質關卡**：Gemini + GLM-5.2 雙路 code review（共同抓到缺資料雙重計算等 7 項，已全數修復）；fresh agent read-back 驗證 README 與程式碼一致（7 項 PASS）。

## 進行中
- 無。

## 下一步（依優先序）
1. **P0（產品決策）**：universe 客觀化——定義可重現納入規則（產業分類碼＋市值/流動性門檻，按時點成分），否則回測永遠只能標「非證據」。
2. 觸發 daily pipeline 或手動 `python generate_static_pages.py` 刷新 reports/docs（本輪未重生產出物）。
3. 用新口徑重跑 `python backtest_engine.py` 與 `python monte_carlo_analyzer.py --seed 42`（需網路）。
4. 舊掃描報告（2026-06-19）是用舊寬鬆門檻產的，鈦昇「黃金潛伏」標示已不成立——下次掃描會自動以新判定產出，可考慮在舊報告加勘誤註記。

## 關鍵決策 + 為什麼
- **黃金標的單一真相來源**：報告/watchlist 不得另設門檻——第二套門檻正是本次誤標事故的根因；已加靜態測試防回歸（test_agent_workflow）。
- **勝率分母只算「已走完 52 週且資料完整」的樣本**：tracking_incomplete 與 missing_data 分開列示，不混算，避免高估。
- **MFE 維持毛值**：未實現極值不套成本；已實現報酬一律淨值。
- **門檻/權重先驗固定不回測 tune**（鐵律不變，經查未被動過）。

## 雷區 / 別碰
- **`main_agent.py` 中文 f-string 對編碼極敏感**（歷史 mojibake 元兇）——只用 UTF-8 的 Edit 工具改，勿用 cp950 腳本覆寫。
- **`BacktestEngine.__init__` 會清空 `backtest_watchlist.json`**（既有設計）——任何跑過 pytest / 實例化的動作都會把該檔弄髒成 `[]`，commit 前務必 `git checkout -- backtest_watchlist.json` 還原。
- `.env` 內有真實 GEMINI_API_KEY（已 gitignore）——勿 commit。
- 本機 clone 容易落後 origin/main（CI 每日 auto-commit）——接手前先 `git pull --rebase`，別誤判「資料沒更新」。
- 既有 cosmetic SyntaxWarning 刻意不動。

## 怎麼跑 / 怎麼測
- 跑測試：`C:\Users\chang\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/ -q`（現為 **32 passed**；跑完記得還原 backtest_watchlist.json，見雷區）
- 每日價格更新：`python main_agent.py --daily-update`
- 每週研判報告：`python main_agent.py --weekly-report`（需 `GEMINI_API_KEY`）
- 產生靜態頁：`python generate_static_pages.py`
- Web 服務：`python app.py`（`/run` 需 `RUN_TRIGGER_TOKEN`）

## 最後 commit
- 見 git log 最新 commit（2026-07-04 整改，Claude Code 多 agent 分工完成）；對手 agent = Antigravity。
