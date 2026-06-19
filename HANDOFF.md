# HANDOFF

> 兩個 agent 交接的唯一現況真相。離開前更新，接手前先讀。

- 最後更新：Claude Code (Opus 4.8) @ 2026-06-19
- 目前任務 / 目標：對全專案做 double review（正確性 + 安全性）後，整組修復所發現的問題。**已完成，測試全綠。**

## 已完成（本次 Claude Code 修復）
- **[P0] `main_agent.py` 核心引擎修復**：原 HEAD(f28c9a4) 整檔中文 mojibake 且結構毀損（`media_story_expert_node` 定義遺失、`pricing_revenue_expert_node` return 被異物覆蓋），無法 `py_compile`、CI/服務/測試全掛。處置：從最後可編譯的 commit `7e5b917` 還原該檔，再重貼 MCT(3013 晟銘電) 數據修正（CV 9.0→12.0%、+33.3%、替代風險 LOW，對齊 market_monitor.py），並移除未使用的 `ChatOpenAI` import。
- **[P1] `app.py`**：`HTML_TEMPLATE.format()` 因 CSS/JS 字面 `{}` 必拋 KeyError → 改用 `_render_html()`（`.replace`）修好 `/latest-report`、`/latest-performance`；`/run` 加 `X-Trigger-Token`(env `RUN_TRIGGER_TOKEN`) fail-closed 認證；`on_event`→lifespan；`get_performance` 改 `.get()` 防呆；markdown 渲染加 DOMPurify 防 XSS。
- **[P1] 勝率指標誠實化**：`performance_tracker.py` / `backtest_engine.py` / `monte_carlo_analyzer.py` 原「勝率」用「最大潛在漲幅(MFE)」達標判定會系統性高估。改為明確標示為「最大潛在漲幅達標率 (MFE)」並**新增「實現報酬勝率 (Realized)」**。
- **[P2] 回測可重現**：`market_monitor.simulate_revenue_inflection` 的 `np.random` 改為依 `(cid, as_of_date)` 用 hashlib 決定性 seed；`monte_carlo_analyzer.py` 新增 `--seed`(預設 42) 並 `random.seed`。
- **[P2] CI 安全**：`daily_market_pipeline.yml` 將 `git pull --rebase || echo` 改為 rebase 失敗即 `exit 1`，不再盲目 `--force-with-lease` 強推蓋掉遠端。
- **[P3] `generate_static_pages.py`**：加 DOMPurify sanitize。
- **[P3] 文件漂移**：README 修正 workflow 檔名(`daily_market_pipeline.yml`)、移除不實的 DST Guard / DeadMan Watchdog 宣稱、修正無 API key 的降級說明（無 Ollama；節點 try/except 內建規則模版）、補上「歷史回測使用模擬營收」誠實註記；`requirements.txt` 移除 `langchain-openai`。
- **[新增缺陷] CI 缺漏補上**：原 workflow 從不執行 `generate_static_pages.py`，但 README §5 宣稱自動部署 Pages → 已新增「Generate Static HTML Pages」step，並從 CI 安裝清單移除 `langchain-openai`。

## 進行中
- 無。原始碼修復已完成，`pytest tests/` 10 passed。

## 下一步
1. commit / push（待人類確認；本次未自動提交）。
2. 觸發 `daily_market_pipeline`（或手動 `python generate_static_pages.py`）以刷新 `reports/` 與 `docs/`——**產出物本次刻意未進 commit，保持 diff 乾淨**。
3. 以新指標重跑 `python backtest_engine.py` 與 `python monte_carlo_analyzer.py --seed 42` 重生回測 .md（需網路）。
### ✅ Stage 1 已實作（2026-06-19，Claude Code）
- **ADR 0005「不捏造、失敗即顯」全套**（`main_agent.py`）：移除 5 節點所有硬編碼 fallback；Critic 例外改 raise（不再 auto-PASS）；新增 `_invoke_with_retry`（3 次退避重試）；`run_hotspot_scan` 僅在 `validation_status=="PASS"` 才寫 `reports/`，否則 `[FAIL]`+`sys.exit(1)`；補 `media_story_expert_node` 的 `critic_feedback`；`temperature=0`；model 抽 env `GEMINI_MODEL`。
- **ADR 0004 存儲層基礎**（新 `pit_store.py` + `data/`）：append-only 不可變月快照（`write_monthly_snapshot` 重複寫即 `SnapshotExistsError`）、PIT 讀取（`read_snapshot`）、`load_content_value_priors`；現有矩陣已逐字搬成 `data/priors/content_value.json`（generation_specs + 4 個 eras=6/9/10/12 家）；`data/README.md` 載明不可變鐵律。**純新增、現有程式碼尚未 import 它。**
- **黃金標的門檻抽具名常數**（`market_monitor.py`）：`CONSENSUS_MAX=60`/`BACKLOG_LEAD_MIN=50`/`DOWNSTREAM_YOY_MAX=15`（行為不變）。
- **回測示意抬頭**（`backtest_engine.py`/`monte_carlo_analyzer.py`）：兩份報告強掛「⚠️ 示意：非真 PIT、勝率非證據」。
- 驗證：全檔 py_compile OK、`pytest` 10 passed、無 mojibake。

### ✅ Stage 2 已完成（2026-06-19，續，commit fdae62f）
- `market_monitor.py` 已改**讀 `pit_store.load_content_value_priors()`**，移除 ~360 行 hardcoded 矩陣（行為等價：era 計數 6/9/10/12、邊界一致、10 tests 綠）。雙重真相來源消除。
- `CHINESE_MAPPING` 已集中到新 `constants.py`（3 檔改 import，移除重複）。

### ⏳ Stage 2 待辦（需真實外部資料源＋開放決策，**建議先 grill 再建**）
- **Consensus** 改外資持股%+股價分位代理運算；**Backlog** 改上游 `segment=equipment` 真月營收 YoY；以上需 `pit_store` 月快照累積或歷史回填。⚠️ 開放決策：外資持股端點、Consensus 加權公式、回填深度——先 grill。
- **歷史月營收回填**（公開月營收歸檔）讓營收訊號可做真回測；回測引擎改讀真 PIT 後移除示意抬頭。
- 次要結構債：yfinance 價格**倖存者偏差**（下市股消失）；兩回測引擎以 monkey-patch `performance_tracker.WATCHLIST_FILE` 全域變數重導（脆弱、待改為傳參）。
- **鐵律**：快照不可變、門檻/權重先驗固定不回測 tune。

## 關鍵決策 + 為什麼
- **還原而非逐字修 main_agent.py**：f28c9a4 整檔 mojibake，無法可靠逐字修；`7e5b917` 為最後可編譯版本，binary-exact 還原最安全。
- **勝率保留 MFE 但併陳 Realized**：不偷改對外數字，改以誠實雙指標呈現，讀者自行判讀。
- **產出物不進本 commit**：reports/docs 為衍生物，CI 已能重生（引擎已修 + 新增靜態頁 step），避免半更新狀態與大量 HTML diff。

## 雷區 / 別碰
- **`main_agent.py` 含大量中文 f-string，對寫檔編碼極敏感**——這正是上次 mojibake 元兇。修它務必用 UTF-8 的編輯器 / Edit 工具，**勿用會以 cp950 寫 stdout/檔案的腳本覆寫**。檔頭已有 `sys.stdout.reconfigure(encoding='utf-8')`，保留。
- `.env` 內有**真實 GEMINI_API_KEY**（已 `.gitignore`、未進 git 歷史）——勿 commit。
- 既有 cosmetic `SyntaxWarning`（`\Delta`、`$\ge`、JS regex `\.`）未清，無功能影響，刻意不動以降低風險。
- 未解（需產品決策）：TWSE API 僅給最新月快照，歷史回測一律 fallback 模擬營收（已於 README 誠實標註，未假造資料）。

## 怎麼跑 / 怎麼測
- 跑測試：`C:\Users\chang\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/ -q`（現為 10 passed）
- 每日價格更新：`python main_agent.py --daily-update`
- 每週研判報告：`python main_agent.py --weekly-report`（需 `GEMINI_API_KEY`）
- 產生靜態頁：`python generate_static_pages.py`
- Web 服務：`python app.py`（`/run` 需設 `RUN_TRIGGER_TOKEN` 並帶 `X-Trigger-Token` 標頭）

## 最後 commit
- 待提交。本次修復由 Claude Code (Opus 4.8) 完成；對手 agent = Antigravity。
