# ADR 0002: 市場熱點預見系統架構決策

狀態：部分被取代（DevOps/金鑰部分已過期；架構方向見 ADR 0003、0004，Agent 行為見 ADR 0005）

## 脈絡
我們需要設計並實作一個能預見未來 12-18 個月市場熱點的系統。根據優秀投資人的中期投資思維，此系統不能單純依賴傳統技術分析（如日 K 線動量），而必須深入科技業供應鏈物理規格升級（例如散熱、CPO 傳輸）、Design Win 放量時程、高頻報價止跌信號，以及營收 YoY 拐點。此任務需要整合多元化的定量與定性數據，並產出高品質的繁體中文學術級分析報告。

## 決策
我們決定採用以下技術架構與設計方案：

1. **多 Agent 狀態機框架 (LangGraph)**：
   - 採用 Python 3.10 與 LangGraph 庫建立 `StateGraph`。
   - 使用 **Supervisor-Expert (主導-專家)** 設計模式，由三個專家節點（`supply_chain_expert`、`pricing_revenue_expert`、`media_story_expert`）各自提取並分析專屬數據，再由 `report_writer` 進行報告整合。
   - 此設計能解耦不同領域的知識抽取，降低單次 Prompt 的 Context 負擔。

2. **結構化 Critic 自我修正機制 (Structured Self-Correction)**：
   - 評審節點 (`quality_critic`) 採用 **Pydantic v2** 的結構化輸出模型（例如 `validation_status` 為 `PASS` 或 `FAIL`，並附帶 `critic_feedback`）。
   - 當判定為 `FAIL` 且未滿 3 次迭代時，透過狀態機條件路由 (Conditional Edge) 將回饋寫回狀態，引導專家節點與寫作者進行針對性的修正。
   - 這能有效解決 LLM 生成報告時「數據漏缺」或「空泛說理」的缺點。

3. **分模組數據引擎 (Decoupled Monitor Engine)**：
   - 建立獨立的數據收集與模擬類別 `MarketInformationMonitor` (於 `market_monitor.py` 實作)。
   - 提供三個專屬介面：高頻價格追蹤、供應鏈時程推演、營收 YoY 拐點模擬。
   - 模擬或抓取台灣供應鏈（台股）實體月營收，作為推算 YoY 拐點的基準。

4. **DevOps 自動化與防護**：
   - 於 GitHub Actions (`.github/workflows/daily_market_pipeline.yml`) 設定兩段排程：每日（台北 Mon–Fri 18:00）股價追蹤，每週（台北 Mon 07:30）多 Agent 報告。
   - 執行完畢後強制 commit 最新報告推回 repo 預設分支，並附帶 `[skip ci]`，保持 Repo 活躍（避免 GitHub 60 天無 commit 暫停 Action 排程的限制）。

## 後果
- **好處**：
  - **品質保證**：透過 Critic 自我修正與 Pydantic 結構限制，報告能包含物理限制、Content Value、YoY 數據等定量指標，產出品質極高。
  - **高擴充性**：後續要增加新的分析維度（例如「政策紅利分析專家」），只需在 LangGraph 中註冊新節點，不需修改主幹邏輯。
  - **低維護成本**：GitHub Actions 免費額度支持，運作成本低廉。
- **折衷與代價**：
  - **運行延遲**：相較於純數值回測，由於需要多次 LLM 調用與 Critic 自我修正循環，單次執行時間預期在 1-2 分鐘內。
  - **API 依賴**：強烈依賴 `GEMINI_API_KEY`，需要配置安全憑證。

> 補註：本 ADR 描述的「無 API key 時以本地樣板產出」行為已由 [ADR 0005](0005-agent-layer-no-fabrication-fail-loud.md) 廢止——LLM 失敗即報錯，不得捏造假數據。
