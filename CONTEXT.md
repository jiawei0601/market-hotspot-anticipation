# Market Monitor — 中期市場熱點資料引擎

`market_monitor.py` 的資料／訊號層：供應鏈內含價值、共識度、設備訂單與營收拐點等中期投資訊號的來源。目標是成為**可稽核、時點正確的量化資料引擎**（現況部分仍為專家先驗的確定性參數，逐步以真實資料源取代——方向見 [ADR](docs/adr/)）。

## Language

**Point-in-Time（PIT／時點正確）**:
某時點 T 的訊號值只反映「在 T 當下可得知」的資訊，不含後見之明。採**混合**策略：自有訊號（CV／Consensus／Backlog）以「從今起前向快照、不可變存檔」累積真 PIT；月營收則以公開月營收歷史重建（次月申報後才可見）。
_Avoid_: 單獨宣稱「無 look-ahead bias」（既有 hardcoded 歷史 matrix 仍含後見之明，不得作回測證據）

**內含價值（Content Value, CV）**:
某公司零組件佔「一台該世代 AI 系統／機櫃」總 BOM 成本的百分比；跨世代 CV 上升＝被設計進，下降＝被設計掉（designed out）。
_Avoid_: 公司營收佔比、毛利率（CV 是系統 BOM 視角，非公司財報視角）

**世代（Generation）**:
以主流 AI 運算架構為時間軸（Vera_Rubin → Feynman → Feynman_Next），作為 CV 與供應鏈洗牌的比較基準；當前代／次代／未來代為相對位置。

**共識度（Consensus Score）**:
市場對「此股為 AI 受惠者」題材的擁擠／已定價程度（0–100；高＝已擁擠、已反映，低＝逆勢、未被覆蓋）。B 階段以公開資料代理：取「股價」與「外資持股%」兩指標，各算 **(a) 自身近 12 個月歷史百分位** ＋ **(b) universe 橫斷面同儕排名**，等權混合成 0–100。來源：外資持股 FinMind 主／TWSE 備、股價 yfinance/TWSE。權重/窗口先驗固定、不回測 tune。
_Avoid_: 估值貴賤、一致預期離散度、手填分數

**設備 Backlog 領先指標（Equipment Backlog Lead）**:
板塊內**所有 `segment=equipment` 公司真實月營收 YoY 的聚合值**，作為「上游正在拉貨」的領先背景（領先下游約 2 季）。⚠️ **誠實限制**：因 per-company 在手訂單／order-book 資料免費不可得，這是「**營收動能背離代理**」，非真正的「訂單領先營收」；原 backlog-leads-revenue 論述據此**降級**。
_Avoid_: 字面「在手訂單簿」；亦勿宣稱「訂單領先」的強論述。

**非共識黃金建倉標的（Golden Accumulation Target）**:
同時滿足三條件的潛伏買點，三者**必須同時成立**（AND）：① 逆勢（Consensus < `CONSENSUS_MAX`）② 領先已動（Equipment Backlog Lead > `BACKLOG_LEAD_MIN`）③ 基本面未現（下游當月營收 YoY < `DOWNSTREAM_YOY_MAX`）。v1 為 boolean。
_Avoid_: 「黃金標的」泛稱任何看好標的（必須三條件齊備）

## Relationships

- 每個**世代**有一組零組件**類別**的 CV（`generation_specs`），加總描述該世代系統的 BOM 結構
- 每家**公司**在其所屬類別內貢獻一份 CV（`content_value_by_gen`），單位同為「佔系統 BOM %」，可與類別 CV 比較
- **替代風險（Substitution Risk）** 由公司 CV 的跨世代變化推導：次代→未來代 CV 大跌＝HIGH（被換掉），大漲＝NONE（含量擴張）
- **非共識黃金建倉標的** ＝ 逆勢(Consensus) ∧ 領先(Equipment Backlog Lead) ∧ 拐點前(下游營收 YoY) 三者 AND

## Flagged ambiguities

- 「內含價值」曾在 `generation_specs`（類別 %）與公司 `content_value_by_gen`（公司 %）兩處使用 → **已解析**：兩處同為「佔系統 BOM %」；前者為零組件類別佔比，後者為該公司在其類別內的貢獻佔比。
- ⚠️ Consensus 的 0–100 加權公式本身是**設計選擇**；其權重**不得用後見之明回測去 tune**（否則重新引入 data snooping）。權重應先驗固定，再驗證。
- ⚠️ 黃金標的三門檻（`CONSENSUS_MAX=60` / `BACKLOG_LEAD_MIN=50` / `DOWNSTREAM_YOY_MAX=15`）為 **pre-registered 先驗常數**，禁止用回測 tune；應從 magic number 抽為具名常數。
