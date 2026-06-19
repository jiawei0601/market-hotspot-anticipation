# ADR 0003: market_monitor 由合成腳手架轉為可稽核 PIT 量化引擎（A→B）

狀態：已採納

## 脈絡
`market_monitor.py` 原以 hardcoded dict 與公式模擬產生 Content Value／Consensus／Backlog／營收等訊號，卻對外以「無 look-ahead bias 回測、勝率驗證」行銷——兩者矛盾。即使用世代區間 gate 掉「當年尚未出現的公司」，對當年已存在公司所手填的 CV／Consensus 仍是 2026 年回頭填的值，含**後見之明（hindsight）**，據此回測屬 data snooping，「無 look-ahead」宣稱不成立。

## 決策
轉向 B（可稽核、時點正確的量化引擎），採以下方案：

1. **混合 PIT 策略**：自有訊號（CV／Consensus／Backlog）以「從今起前向、不可變快照」累積真正的 Point-in-Time 資料；月營收以公開月營收歷史重建（次月申報後才可見），是目前**唯一可做真歷史回測**的訊號。
2. **訊號定義**（權威定義見 [`CONTEXT.md`](../../CONTEXT.md)）：
   - **Content Value** ＝某公司零組件佔「一台該世代 AI 系統」總 BOM 成本的 %；跨世代升＝被設計進、降＝被設計掉。
   - **Consensus Score** ＝題材擁擠／已定價程度（0–100），由公開資料**代理**計算（外資持股比變化＋近 12 個月股價分位…），不再手填。
   - **Equipment Backlog Lead** ＝上游設備廠**真實月營收 YoY** 領先代理（取代合成公式），非字面在手訂單。
   - **非共識黃金建倉標的** ＝ 逆勢(Consensus) ∧ 領先(Backlog) ∧ 拐點前(下游營收 YoY) 三條件 **AND** boolean。
3. **反 data-snooping 紀律**：黃金標的三門檻與 Consensus 加權，皆為 **pre-registered 先驗常數**，禁止用回測去 tune；先固定、後驗證。
4. 存儲與落地方式見 [ADR 0004](0004-market-monitor-pit-data-architecture.md)。

## 後果
- 目前只有「營收訊號」能做真歷史回測；CV／Consensus／Backlog 的回測效力**只能從前向存檔累積後**才合法——對外任何回測/勝率宣稱必須據此**限縮範圍**並標示。
- `simulate_revenue_inflection` 的未來 3 個月投影僅為示意；黃金標的判定只用**實際**當月營收，不用投影。
- 既有 hardcoded matrix 降級為過渡期的 CV 專家先驗，不得作回測證據。
