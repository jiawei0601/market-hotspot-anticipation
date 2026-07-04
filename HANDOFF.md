# HANDOFF

> 兩個 agent 交接的唯一現況真相。離開前更新，接手前先讀。

- 最後更新：Claude Code (Fable 5 指揮 + sonnet/haiku 分工) @ 2026-07-04
- 目前任務 / 目標：全專案審查後整組修正（回測口徑、訊號誠實化、判定 bug、repo 衛生、README 決策流程文件化）。2026-07-04 一日完成「審查整改→universe 客觀化→板塊登記簿→七板塊擴容→LLM 切換 NIM GLM-5.2」全鏈。**167 tests 全綠，七板塊報告 7/7。**

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

### ✅ ADR 0007 Universe 客觀化全篩（2026-07-04 續，同日完成）
- **`universe.py` 管線**：三層漏斗先驗規則（上市滿 12 月／月底成交值 ≥1500 萬／產業 10 類）＋TWSE 批次與 FinMind 逐檔混合架構＋限流退避（`--paced`）＋provisional/版本雙判準重建政策＋`FINMIND_TOKEN` 支援。
- **138 個月 universe 快照全數建成**（`data/snapshots/YYYY-MM/universe.json`，2015-01..2026-06，rules_version=0007-v2，0 缺值）：2026-06 漏斗 2741→2412→939→**538 檔**；時間趨勢 237(2015)→538(2026) 平滑遞增。
- 兩筆 pre-registration 修正（皆在任何回測使用前，記於 ADR 0007）：①上市粗分類「電子工業」補入；②上市／上櫃字尾不一致（其他電子**業** vs 其他電子**類**）補入——後者曾誤篩弘塑/萬潤/雙鴻。修正後舊 12 檔 universe 全數通過篩選（12/12）。
- fresh 驗證：漏斗單調 138/138、PIT 上市時長抽查全過、華亞科(3474) 2017 後正確消失、45 個 universe 測試（全套 77 passed）。
- 快取 `data/universe_cache/`（1428 檔 FinMind 價格＋TWSE 月批次）已 gitignore，重建純本地。

### ✅ ADR 0008 板塊歸屬登記簿 + 接線 + forward 凍結（2026-07-04 續，同日完成）
- **`sector_membership.py`**：append-only 證據定日事件簿（E1 公司自揭/E2 官方指數/E3 第三方當時存檔；`effective_from>=evidence_date` 硬驗證；PIT 讀取；`get_members_in_universe` 與 universe 快照取交集）。31 tests。
- **接線**：`market_monitor.resolve_sector_members` 單一入口——登記簿非空走 registry（PIT），空則 fallback content_value 先驗＋`membership_source` 標記一路帶到報告與回測（fallback 時 LLM 報告強制非 PIT 警語）。訊號公式/門檻不動，fallback 行為與現狀等價（回歸測試固化）。回測 ticker 改由 stock_id＋universe type map 組尾碼。
- **核心決策 forward-only**（probe-0008 實測 Wayback 快照過稀、無 CPO 主題指數、題材過新）：放棄歷史回填，登記簿起點 2026-07-04；此前時點永遠 fallback＋非 PIT 標示。
- **Seed 完成**：CPO 板塊 11 檔入簿（E1×5：聯鈞/雙鴻/奇鋐/旺矽/晟銘電；E3×6：弘塑/一詮/鈦昇/辛耘/萬潤/家登，共用 CMoney 概念股頁 Wayback 存檔）。**雍智 6683 找無 CPO 歸屬證據→不入簿（ADR 記 pending evidence）**，registry 路徑下已退出板塊名單——鐵律正確結果，補到證據即可 `add_event` 歸隊。
- 驗證：今日 resolve → registry 11 檔；2021 時點 → fallback 9 檔（era 正確）。118 tests 綠。

### ✅ 板塊擴容工程（2026-07-04 續，同日完成）
- **管線泛化**：content_value.json 改 sector-keyed（CPO 數值零變動）；`sector_specs.json` 世代規格表；main_agent prompt 泛化（動態代表股、未知板塊禁編造世代敘事、`future_gen` 參數化）；app.py 支援 `?sector=`；ingest.py 登記簿驅動（`--backfill-sector`、ticker 三層解析）。
- **兩個新板塊上線**：`Thermal_Cooling` 14 檔（E1×12）、`Advanced_Packaging` 12 檔（E1×7），全數附證據＋Wayback 存檔；pending 清單見 `docs/drafts/sector-expansion-評估.md`。
- **兩個 P0 修復（雙路 review + 實跑抓到）**：
  ①登記簿純代號 vs CV 矩陣帶尾碼代號查表 miss → registry 路徑 CV 分析全空 → `_pure_id` 正規化＋防回歸測試；
  ②pit_store 不可變粒度為整月檔 → 新板塊成員無法補歷史資料 → 鐵律精確化為「(月,公司) 級」＋`append_companies_to_snapshot`（既有條目 byte 不變、追加冪等）。
- **PIT 資料已擴容**：散熱 +2535 筆營收/持股 +1360 筆價格、先進封裝 +1447/+776，PIT 抽查正確（台達電 2016 有、均華上櫃前正確缺席）。
- **散熱首份報告產出**（`reports/2026-07-04-Thermal_Cooling-feasibility-report.md`，Critic PASS）：正確使用登記簿 11 檔、誠實回報「無標的通過黃金潛伏門檻」。首版曾出現 LLM 虛構「假設性標的情境」→ 已加誠實化規則第 5 條（嚴禁虛構假設性標的）＋ Critic 捏造禁令檢查，重產後 0 虛構。
- 156 tests 綠。

### ✅ 七板塊擴容＋LLM 切換 NIM GLM-5.2（2026-07-04 深夜完成）
- **四個新板塊上線**（證據定日入簿＋PIT 回填＋sector_specs 無世代框架模式）：LEO_Satellite 12 檔（E1×11）、Edge_AI 10 檔（全 E1、嚴格門檻）、Passive_Components 10 檔（全 E1）、Memory 13 檔（全 E1）。CHINESE_MAPPING 擴至 75 筆（尾碼依 universe records 程式核對；曾誤標 4904 中華電信→已修為遠傳）。
- **LLM 供應商切換**：Gemini → NVIDIA NIM `z-ai/glm-5.2`（`NIM_MODEL` 可覆寫；無金鑰 fail loud）。GitHub secret `NVIDIA_NIM_API_KEY` 已設。**Critic 三重 fail-closed**（GLM 實測回 "REJECTED" 非枚舉值）：描述鎖 PASS/FAIL＋validator 同義詞正規化（未知→FAIL）＋路由改「非 PASS 即重修」。
- **Backlog 不適用誠實化**：無 equipment 成員板塊 `get_backlog_lead` 回 None（非 0.0 充數）、黃金閘門誠實地不可觸發（替代訊號＝開放產品決策）、Critic 要求改條件式（程式判定注入，不讓 LLM 猜）。散熱板塊憑此首次過審發布。
- **429 限流韌性**：`_invoke_with_retry` 對 429 走 30→300 秒長退避（不耗一般重試額度）；CI 板塊間隔 sleep 90。
- **CI 週報擴至七板塊**。**報告 6/7 完成**（Memory 因 NIM 當日額度耗盡待重試，背景已排 30 分鐘冷卻重掃）。watchlist=0（七板塊皆無黃金標的，誠實結果）。167 tests 綠。

### ✅ 十分類板塊重整＋universe v3（2026-07-05 凌晨完成）
- **十分類上線**（使用者定義的分類架構）：CPO 11／先進封裝+測試介面 15（雍智以 MOPS 原件 E1 歸隊）／被動元件 10／記憶體 13／ABF 載板 6／循環經濟 3／IC 設計 ASIC 8（含 IP 商附但書；譜瑞/信驊 pending）／AI 電源基建 11（電源+重電+水冷周邊三軌）／石英 5／**傳產復甦 9**。散熱/低軌衛星/邊緣AI 退出週掃輪替（登記簿保留、可手動掃）。
- **Universe v3**（使用者裁決選項 B）：INDUSTRY_ALLOWED 10→17 類（資料驅動枚舉：化學/塑膠/水泥/油電燃氣/綠能環保類/創新板/其他），138 快照全重建，2026-06 漏斗 2741→2412→939→**617**；傳產 ∩universe 0→9。ADR 0007 修正紀錄三。
- **三層 LLM 備援鏈**：NIM GLM-5.2 → DeepSeek 官方（thinking 模式僅支援 json_mode，已做包裝層）→ Claude CLI（本機限定）；429 同層 2 輪×180s 後黏性降級；報告尾部誠實標示實際 provider。CI secrets 三把齊備。
- CHINESE_MAPPING 121 筆（全數對 universe records 官方欄位校驗）；sector_specs 13 板塊（十分類敘事為使用者原話）；PIT 資料層 117 家公司。178 tests 綠。
- 十分類首輪掃描交由 CI 週報（cron 週日）執行，或手動逐板塊跑。

## 進行中
- 無。（Memory 首掃已於 2026-07-04 21:4x 完成，Critic 一輪 PASS，七板塊報告 7/7 齊備；429 重試已改固定 180 秒×10 輪）

## 下一步（依優先序）
1. 雍智 6683 pending evidence；E1 三檔（旺矽/晟銘電/雙鴻）evidence_date 佔位待補正。
2. 手動或等 CI 跑 `python generate_static_pages.py` 刷新 GitHub Pages（七板塊新報告尚未編入靜態頁）。
3. 用新口徑重跑 `python backtest_engine.py` 與 `python monte_carlo_analyzer.py --seed 42`（需網路）。
4. 開放產品決策：無 equipment 成員板塊（散熱/被動元件/記憶體等）的黃金閘門是否需要替代第三訊號（現況＝誠實地永不觸發）。
5. NIM 免費層 ~40 RPM 共享速率制：CI 已有板塊間隔 90s＋429 固定 180s×10 輪重試；若常撞牆可把週報 cron 移到台北早晨或換 NIM_MODEL。
（已完成不再列：watchlist 已歸檔重置=0、CI 已七板塊、新板塊 SOP 見 ADR 0008）

## 關鍵決策 + 為什麼
- **黃金標的單一真相來源**：報告/watchlist 不得另設門檻——第二套門檻正是本次誤標事故的根因；已加靜態測試防回歸（test_agent_workflow）。
- **勝率分母只算「已走完 52 週且資料完整」的樣本**：tracking_incomplete 與 missing_data 分開列示，不混算，避免高估。
- **MFE 維持毛值**：未實現極值不套成本；已實現報酬一律淨值。
- **門檻/權重先驗固定不回測 tune**（鐵律不變，經查未被動過）。

## 雷區 / 別碰
- **`main_agent.py` 中文 f-string 對編碼極敏感**（歷史 mojibake 元兇）——只用 UTF-8 的 Edit 工具改，勿用 cp950 腳本覆寫。
- **`BacktestEngine.__init__` 會清空 `backtest_watchlist.json`**（既有設計）——任何跑過 pytest / 實例化的動作都會把該檔弄髒成 `[]`，commit 前務必 `git checkout -- backtest_watchlist.json` 還原。
- `.env` 內有真實金鑰（GEMINI_API_KEY／FINMIND_TOKEN／NVIDIA_NIM_API_KEY，已 gitignore）——勿 commit。
- 本機 clone 容易落後 origin/main（CI 每日 auto-commit）——接手前先 `git pull --rebase`，別誤判「資料沒更新」。
- 既有 cosmetic SyntaxWarning 刻意不動。

## 怎麼跑 / 怎麼測
- 跑測試：`C:\Users\chang\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/ -q`（現為 **167 passed**；跑完記得還原 backtest_watchlist.json，見雷區）
- 每日價格更新：`python main_agent.py --daily-update`
- 每週研判報告：`python main_agent.py --weekly-report --sector <板塊>`（需 `NVIDIA_NIM_API_KEY`；`NIM_MODEL` 可覆寫，預設 z-ai/glm-5.2）
- 產生靜態頁：`python generate_static_pages.py`
- Web 服務：`python app.py`（`/run` 需 `RUN_TRIGGER_TOKEN`）

## 最後 commit
- 見 git log 最新 commit（2026-07-04 整改，Claude Code 多 agent 分工完成）；對手 agent = Antigravity。
