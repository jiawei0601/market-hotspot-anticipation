# ADR 0006: Stage 2 真實資料來源與訊號操作化

狀態：已採納（決策已定；實作待 FinMind/TWSE 端點探查後進行）

## 脈絡
[ADR 0003](0003-market-monitor-synthetic-to-pit-engine.md) 決定 `market_monitor.py` 走 B（可稽核 PIT 量化引擎）、採混合 PIT。Stage 1 已建 [pit_store](0004-market-monitor-pit-data-architecture.md) 存儲層並讓 market_monitor 改讀先驗。Stage 2 要把三個自有訊號接上真實免費資料。本 ADR 釘死來源與操作化公式（經 grill 對齊；權威術語見 [CONTEXT.md](../../CONTEXT.md)）。

## 決策
1. **歷史月營收**：FinMind `TaiwanStockMonthRevenue`（自帶公布日、PIT 友善）為主，TWSE／TPEx 官方逐月歸檔為權威 fallback／交叉校驗。回填深度**自 2015 起**，逐月寫入 `data/snapshots/YYYY-MM/revenue.json`（append-only、不可變）。
2. **Consensus**：取「股價」與「外資持股%」兩指標，各算 (a) 自身近 12 個月歷史百分位 ＋ (b) universe 橫斷面同儕排名，**等權混合**成 0–100（高＝已擁擠/已反映）。外資持股 FinMind 主／TWSE 備。
3. **Equipment Backlog Lead**：板塊內所有 `segment=equipment` 公司**真實月營收 YoY 的聚合**，作為「上游拉貨」領先背景。⚠️ **誠實限制**：因 per-company order-book 不可得，這是「營收動能背離代理」，非真訂單領先；原 backlog-leads-revenue 論述據此降級。
4. **反 data-snooping**：Consensus 權重／窗口、黃金標的三門檻（`CONSENSUS_MAX`/`BACKLOG_LEAD_MIN`/`DOWNSTREAM_YOY_MAX`）皆 **pre-registered 先驗**，禁止用回測 tune。

## 後果
- 回填範圍含**營收 ＋ 外資持股**歷史；兩者皆 PIT 可重建 → 營收訊號與 Consensus 可做真歷史回測；回測引擎接上真 PIT 後移除「示意」抬頭。
- 依賴 FinMind 第三方（lock-in 風險）；故保留 TWSE/TPEx 官方為 fallback。
- **實作前需一次小探查**：實際打 FinMind/TWSE 端點，確認真的回傳歷史資料＋公布/資料日期，再正式建（不在本 ADR 範圍）。
