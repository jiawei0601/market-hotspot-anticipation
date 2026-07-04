# ADR 0007: Universe 客觀化全市場篩選

狀態：已採納（規則先驗固定；實作與首次實跑已完成，見下方「實作與驗證」）

## 脈絡

[HANDOFF 2026-07-04](../../HANDOFF.md) 標記 P0 產品決策缺口：現行 12 檔分析母體（`ingest.py` 的
`YFINANCE_TICKERS`）是人工事後選定名單，非可重現規則篩選結果，導致回測只能標「非證據」——
無法區分「策略有效」與「選股當下已知道結果」的倖存者偏誤。

本 ADR 決定用可重現、先驗固定的規則式篩選，取代人工選股，產出每月一次的不可變 PIT universe 快照。
實作前先做端點探查（[probe-0007](../probe-0007-universe-endpoints.md)），確認架構可行性，
本 ADR 的三層漏斗設計即依探查結果訂定。

## 決策

### 母體與三層漏斗

母體：FinMind `TaiwanStockInfo` 的 `type ∈ {twse, tpex}`（含已下市股），排除 `emerging`（興櫃）。

依序套用三條規則（先驗固定，寫成具名常數＋docstring，**禁止用回測結果調參**，見 `universe.py`）：

1. **規則 1：上市時長** `MIN_LISTING_MONTHS = 12`——該股在資料中最早可見價格月份距 as_of ≥ 12 個月。
2. **規則 2：流動性** `MONTH_END_TURNOVER_FLOOR = 15_000_000`（新台幣元）——近 3 個月「每個月底交易日的
   成交金額」皆須達標。上市股取自 TWSE `MI_INDEX` 月底批次、上櫃股取自 FinMind 日價的月底列。
3. **規則 3：產業分類** `industry_category ∈ INDUSTRY_ALLOWED`——半導體業、光電業、電子零組件業、
   電腦及週邊設備業、通信網路業、電子通路業、其他電子業、電機機械、電子工業（粗分類，
   見修正紀錄一）、其他電子類（上櫃「類」字尾變體，見修正紀錄二），共 10 類。
   字串於 2026-07-04 實際打 FinMind `TaiwanStockInfo` API 核對（回應共 57 個
   `industry_category` 值，含 ETF/ETN/Index 等非個股類別），非憑記憶猜測拼寫。

### Pre-registration 修正紀錄一（2026-07-04）：粗分類「電子工業」

首次 `--current` 實跑證明 `TaiwanStockInfo` 的分類字串**粒度不一致**：對部分上市電子股
（3017 奇鋐、3013 晟銘電）掛的是粗分類「電子工業」而非細分類（半導體業／電子零組件業等），
導致這些明確屬於電子供應鏈的個股在規則 3 被誤判剔除。故將「電子工業」納入 `INDUSTRY_ALLOWED`。

此修正的性質聲明：
- **原因**：資料源分類字串粒度不一致（同一產業空間有粗、細兩套標籤並存），屬資格判定的
  正確性修正，非依回測績效調整參數。
- **時點**：修正發生於 2026-07-04，在任何回測使用本清單**之前**——當時尚無任何回測以
  universe 快照為母體執行過，不存在「看了回測結果才改規則」的可能。
- 此修正已同步記錄於 `universe.py` 的 `INDUSTRY_ALLOWED` docstring。

### Pre-registration 修正紀錄二（2026-07-04）：上市／上櫃分類字尾不一致

回填完成後驗證發現第二個粒度問題：**TPEx 上櫃側對「其他電子」產業空間用「類」字尾
（「其他電子類」，60 檔），TWSE 上市側用「業」字尾（「其他電子業」）**——同一產業空間、
兩套字尾。`INDUSTRY_ALLOWED` 原只收「業」字尾，導致弘塑 3131、萬潤 6187、雙鴻 3324 等
上櫃電子股被誤剔除（其流動性與上市時長皆通過，僅因字尾差異卡在規則 3）。

依快取（`data/universe_cache/finmind_stock_info.json`）枚舉 type=tpex 的全部 37 個
`industry_category` 唯一值逐一核對：

- **納入**：「其他電子類」——唯一與現有清單語意對應的「類」字尾變體。其餘電子供應鏈類別
  （半導體業、光電業、電子零組件業、電腦及週邊設備業、通信網路業、電子通路業、電機機械）
  上櫃側與上市側**字串完全相同**，無需變體。
- **刻意不納入的電子相關字串**：資訊服務業（軟體/SI）、數位雲端類（雲服務）、
  電子商務業（電商平台）——三者皆屬軟體與服務業，非電子供應鏈硬體製造；
  電器電纜（傳統電工產品）——不在原始八類的語意範圍內。

性質聲明同修正紀錄一：分類字串命名慣例不一致（上市/上櫃兩套字尾），屬資格判定正確性修正、
非回測調參；修正時點在任何回測使用本清單之前。

**版本升級**：`RULES_VERSION` 自 `0007-v1` 升為 `0007-v2`。既存的 v1 快照依下方重建政策
（rules_version 過時）允許重建為 v2；重建為純本地計算（資料全在 `data/universe_cache/` 快取）。

### Pre-registration 修正紀錄三（2026-07-04）：允許清單資料驅動擴充

**觸發背景**：`data/sector_membership/` 板塊登記簿（ADR 0008）陸續收錄了與電子供應鏈無關或
邊緣的板塊主題。查證草案（`docs/drafts/sector-recycle-quartz-tradi.md`）發現：

- **Traditional_Recovery**（傳產復甦：塑化/水泥，11 檔）：`get_members_in_universe()` 交集為
  **0 檔**——全部 11 檔的 `industry_category`（塑膠工業／水泥工業／油電燃氣業／化學工業）
  都不在原 `INDUSTRY_ALLOWED` 十類「電子供應鏈相關」清單內，板塊與 universe 篩選完全互斥。
- **Semiconductor_Materials_Recycling**（半導體材料循環經濟，7 檔）：交集僅 2 檔（1785光洋科、
  3663鑫科，因剛好落在「其他電子類」）；其餘 5 檔（8390金益鼎、9955佳龍、6803崑鼎、
  7610聯友金屬-創、6894衛司特）雖業務實質貼近半導體供應鏈（E1 等級證據），但官方
  `industry_category` 分別落在「其他」「創新板股票」「綠能環保類」，與電子供應鏈十類無關。

草案將此列為 ADR 0007 範圍內的決策缺口（選項 A：登記簿與 universe 交集脫鉤，維持現狀；
選項 B：擴充 `INDUSTRY_ALLOWED` 涵蓋登記簿板塊實際涉及的產業分類），提交使用者裁決。

**使用者裁決：選項 B**——擴充允許清單，使 universe 篩選能涵蓋登記簿已收錄板塊的成員。

**方法（資料驅動枚舉，非憑空猜測分類字串）**：讀取 `data/sector_membership/` 下當時存在的
全部 13 個板塊 JSON 事件檔的全部成員 `stock_id`（去除 `action=remove` 的撤銷事件），
對照 `data/universe_cache/finmind_stock_info.json`（經 `build_universe_pool()` 相同的
type∈{twse,tpex}過濾＋去重邏輯，確保與正式篩選管線行為一致）查出每檔的 `industry_category`，
枚舉出「已入簿成員所屬、但不在現行 `INDUSTRY_ALLOWED` 的類別」完整清單。枚舉結果與新增類別：

| 新增類別 | 觸發板塊 | 觸發股（stock_id 名稱） |
|---|---|---|
| 其他 | Semiconductor_Materials_Recycling | 6803崑鼎、8390金益鼎、9955佳龍 |
| 創新板股票 | Semiconductor_Materials_Recycling | 7610聯友金屬-創 |
| 綠能環保類 | Semiconductor_Materials_Recycling | 6894衛司特 |
| 塑膠工業 | Traditional_Recovery | 1301台塑、1303南亞、1312國喬、1326台化 |
| 水泥工業 | Traditional_Recovery | 1101台泥、1102亞泥、1103嘉泥、1104環泥、1108幸福 |
| 油電燃氣業 | Traditional_Recovery | 6505台塑化 |
| 化學工業 | Traditional_Recovery | 1714和桐 |

共新增 7 類，`INDUSTRY_ALLOWED` 自 10 類擴為 17 類。

**誠實聲明（本次修正的性質與限制）**：

1. **允許清單語意本身發生質變**：自本輪起，`INDUSTRY_ALLOWED` 的設計語意從「電子供應鏈相關
   類別」擴為「登記簿板塊涵蓋之產業」——這不再是單純的電子供應鏈濾網，而是「目前已知登記簿
   板塊實際涉及的產業分類聯集」。此為範圍性質的改變，非資格判定字串粒度修正（與修正紀錄一、
   二的性質不同），但修正時點仍在任何回測使用本清單之前，且是使用者明確裁決（選項 B）後執行，
   非依回測績效反推。
2. **「其他」是官方分類系統的通用未分類桶**：母體（2026-06 快照）中「其他」類別涵蓋 151 檔，
   遠多於本次三檔觸發股（6803/8390/9955）。納入「其他」類別意味著這 151 檔中只要通過規則1
   （上市時長）與規則2（流動性），皆會通過規則3，而非僅有這三檔觸發股。本次納入僅因登記簿
   證據要求收錄這三檔，**未對「其他」桶內其餘 148 檔逐一審查產業適格性**，這是選項 B
   的必然結果（允許清單以分類字串為粒度、無法只放行單一 stock_id），使用者裁決時已知悉此點。
3. **後續維運責任**：若日後新增板塊引入尚未被本清單涵蓋的產業分類，需同步重跑本節枚舉方法
   （比對板塊成員 `industry_category` 與 `INDUSTRY_ALLOWED`），修訂清單並在 ADR 補記錄，
   不可讓允許清單與登記簿實際涵蓋範圍脫節、也不可為求方便直接放行未經枚舉驗證的分類字串。
4. 本輪修正執行時，`data/sector_membership/` 下另有其他 agent 正在並行新增板塊 JSON
   （ABF/IC_Design/AI_Power 等）；本次枚舉以修正執行當下已存在的 13 個板塊 JSON 為準，
   晚到的板塊如引入新產業分類，依上一點原則由後續變更另行枚舉補查，不在本次範圍內。

**版本升級**：`RULES_VERSION` 自 `0007-v2` 升為 `0007-v3`。既存的 v2 快照依下方重建政策
（rules_version 過時）允許重建為 v3；重建為純本地計算（資料全在 `data/universe_cache/` 快取）。

### 資料來源架構（依 probe-0007 的「批次優先、混合為輔」建議）

- **上市股（type=twse）**：規則 1、2 皆用 TWSE `exchangeReport/MI_INDEX?type=ALLBUT0999` 月底批次
  行情——近 3 個月（流動性）＋ 1 個探測點（`as_of` 往前推 `MIN_LISTING_MONTHS` 個月的月底，判斷該股
  是否已出現在批次行情中）。每月一次全市場批次呼叫，不逐檔打 FinMind，維持探查報告估算的
  「138 個月＝138 次呼叫」量級架構。
- **上櫃股（type=tpex）**：因 TPEx 官方歷史批次行情端點已失效（見誠實聲明缺口 2），改用 FinMind
  `TaiwanStockPrice` 逐檔抓日價序列，本地依日期切月計算月底交易金額與最早可見月份。
- **下市名單**：TWSE `openapi/v1/company/suspendListingCsvAndHtml`（264 筆，一次呼叫）用於標記
  `delisted` 欄位；上櫃股無對應官方端點（見誠實聲明缺口 3）。
- **快取**：所有原始 API 回應快取到 `data/universe_cache/`，檔案存在即不重打（可續跑）。
  FinMind 請求間 sleep ≥ 3 秒、TWSE ≥ 2 秒，延續 `ingest.py` 既有節奏慣例。

### 限流韌性（2026-07-04 實跑後補強）

首次實跑證實：FinMind 免費匿名層在連續約 285 次請求後觸發 `HTTP 402 Payment Required`
（"Requests reach the upper limit"），與探查報告「5 次請求無 402/429」的樣本量不足結論不符。
補強措施（見 `universe.py`）：

- **指數退避**：402/403 時依 `RATE_LIMIT_RETRY_SLEEPS = (60, 900, 900)` 重試——先 sleep 60 秒
  重試一次，再失敗 sleep 900 秒（15 分鐘）重試，最多 3 輪，全部耗盡仍失敗才記 `fetch_error`。
- **`--paced` 旗標**：偵測到限流即進入「每小時窗口」模式（sleep 到下個整點再繼續，
  上限 `PACED_WINDOW_MAX = 48` 個窗口），讓長回填能無人值守跑完。
- **進度可見**：上櫃股逐檔處理每 50 檔（`PROGRESS_PRINT_EVERY`）列印進度、fetch_error 累計數
  與已快取檔案數。
- 非限流錯誤（其他 HTTP／網路錯誤）不重試、直接拋出（fail loud，ADR 0005）。
- 單檔最終失敗不讓整批中止：顯式記入快照的 `fetch_errors`／`fetch_error_count`，
  該檔不算通過也不算「已知不通過」（避免與真實剔除原因混淆）。

### 探測點近似（規則 1 的成本折衷）

對 2000+ 檔上市股逐檔打 FinMind 抓完整歷史以求精確「首次上市月份」，成本與批次優先架構相悖
（探查報告 5b 已證實 TWSE 無全市場批次的「上市日期」端點）。故規則 1 對上市股改用
**探測點存在性**近似：只在 `as_of` 往前推 12 個月的月底檢查該股是否已出現在 TWSE 批次行情中，
存在即通過、不存在或該月無資料即不通過。`first_price_month` 欄位在此情況下記錄的是
「探測點月份」而非精確首月，需誠實理解為「至少從此月已存在」而非「恰好從此月開始」。

`--current` 模式下，上櫃股為降低單次執行負載，FinMind 查詢起點縮至 `as_of` 往前
`CURRENT_TPEX_LOOKBACK_MONTHS = 15` 個月（涵蓋 12 個月探測點＋3 個月流動性窗口的緩衝）；
若探測點仍落在縮窗範圍內即可精確判斷，退化情況（探測點早於縮窗起點）則同樣改用探測點存在性
近似，與上市股邏輯一致。`--backfill` 則用完整歷史起點精確計算，不受此近似影響。

### 快照格式

`build_snapshot(month)` 產出 `data/snapshots/YYYY-MM/universe.json`（經 `pit_store` 以
`kind="universe"` 寫入），欄位：

- `as_of`、`rules_version`（規則版本標籤，供未來規則變動時追溯）
- `pool_count` / `rule1_listing_length_count` / `rule2_liquidity_count` / `rule3_industry_count`
  （各層漏斗計數）
- `final_pass`（最終通過的 stock_id 排序列表）
- `records`：每檔 `{stock_id, name, type, industry, month_end_turnover, first_price_month, delisted}`
- `fetch_error_count` / `fetch_errors`（限流等原因抓取失敗的個股與原因）
- `provisional`（暫定旗標，見下方重建政策）

### 快照重建政策（provisional ＋ rules_version）

不可變鐵律的適用範圍依快照完整性**與規則版本**區分（判定函式
`universe.snapshot_is_rebuildable()`）：

- **完整且版本相同的快照**（`fetch_error_count == 0` 且 `rules_version == RULES_VERSION`）：
  維持 append-only 不可變鐵律，已存在即拒寫（`pit_store.SnapshotExistsError`），永不覆蓋。
- **暫定快照**（`fetch_error_count > 0`，標記 `"provisional": true`）：允許被重跑覆蓋——
  限流等原因造成缺值的快照，重跑補齊是預期操作（重跑會利用 `data/universe_cache/` 快取，
  只補失敗的檔），不算違反不可變鐵律。重建後若已無缺值，快照轉為完整、自此不可再覆寫。
- **版本過時的快照**（`rules_version != RULES_VERSION`，即使完整）：允許重建——規則經
  pre-registration 修訂（如 0007-v1 → 0007-v2 補產業分類字尾變體）後，舊版本快照重建為
  新版本是預期操作；重建為純本地計算（資料全在快取）。版本相同且完整者不在此列。
- 判定函式 `universe.snapshot_is_provisional()` 同時相容「顯式 provisional 旗標」與
  「早期未寫入該欄位、但 `fetch_error_count > 0`」的快照——2026-07-04 首次實跑產出的
  2026-06 快照（850 檔缺值）即屬後者，依本政策視為 provisional、允許重建。
- `--backfill` 遇到既存的 provisional 或版本過時快照會自動重建，遇到完整且版本相同的
  快照則略過。

理由：不可變鐵律的目的在保護「已完成的 PIT 證據」不被事後竄改。一份因外部限流而大量缺值的
快照並非完成的證據，把它鎖死反而讓缺值永久化；同理，規則已修訂而快照仍是舊版規則的產物時，
「用新規則重算」不是竄改證據而是套用當前已凍結規則（修訂本身受 pre-registration 紀錄約束）。
以 `fetch_error_count == 0 且 rules_version 相同` 作為「證據完成」的機械判準，
邊界客觀可驗，不依人工判斷。

### pit_store 最小擴充

`pit_store.write_monthly_snapshot` 的 `kind` 參數原文件僅列舉
`{'revenue','holdings','prices'}`，但函式本身未做白名單限制。本 ADR 新增 `kind="universe"`
使用方式，僅更新 docstring 明確支援任意快照種類字串，不變更任何既有行為或介面
（見 `pit_store.py` 第 19-24 行變更）。

## 誠實聲明：四項已知缺口

以下限制經探查報告確認，非實作疏漏，necessitate 使用者對 universe 快照的定位保持謹慎：

1. **產業分類為現行分類回溯套用到歷史月份**。未找到任何端點提供「某公司在歷史某時點的產業分類」
   時間序列；`industry_category` 本質是資料庫當前快照。已知台股產業分類異動事件確實存在但頻率低、
   非常態，此限制對篩選結果的影響幅度預期可接受，但不宜宣稱「歷史分類完全準確」。
2. **上櫃股歷史批次行情端點已失效**。TPEx 新版 openapi (`tpex_mainboard_quotes`) 僅回傳當日資料、
   舊版查詢 (`stk_quote_result.php`) 的歷史日期參數已被忽略（回應固定回傳查詢當下日期），無替代
   官方批次端點；只能逐檔用 FinMind 補上，耗時遠高於上市股的批次路徑。
3. **上櫃股下市名單缺**。TWSE 有完整下市清單 API（264 筆），TPEx 未找到對應端點；本管線目前
   僅能標記上市股的 `delisted` 欄位，上櫃股已下市個股無法從官方批次清單直接排除
   （會因近期無成交量自然被規則 2 流動性門檻篩掉，但這是流動性篩選的副作用，非母體層級的
   顯式下市判斷，兩者概念上有別，不可混淆）。
4. **流動性用月底單日抽樣代理**，非月度總成交量或日均成交量。批次端點（TWSE `MI_INDEX`）
   天生只提供單日全市場快照，逐日全月加總的成本（交易日數 × 月數）超出可行範圍。此代理指標
   可能低估「月中曾有高流動性但月底恰逢量縮」的個股，為已知限制而非資料遺漏。

## 定位聲明

**universe 快照僅供 forward 使用起點與弱證據回測，不構成策略證據。** 具體而言：

- 從快照建立月份起，可作為「不知道未來結果」的客觀納入池，供之後的訊號/回測使用，這是本 ADR
  解決的核心問題（消除人工選股的倖存者偏誤）。
- 對快照建立月份**之前**的歷史回填快照，因產業分類回溯（缺口 1）與流動性代理指標（缺口 4）的
  限制仍然適用，用這些快照做「回測驗證策略歷史表現」時，結果只能視為弱證據——規則本身客觀
  可重現，但底層資料的時點精確度不如即時建的快照，不能宣稱是嚴格的歷史真實母體重建。

## 後果

- 12 檔既有 `YFINANCE_TICKERS` 名單需對照 universe 篩選結果重新檢視（見實作與驗證章節的核對結果）；
  未通過的個股不代表基本面不佳，只代表不滿足本 ADR 的客觀規則（如產業分類字串不在允許清單、
  或流動性代理指標未達標）。
- 之後如需將 universe 篩選結果接入 `backtest_engine.py` / `main_agent.py` 的實際選股池，
  屬本 ADR 範圍外的後續整合工作。
- 規則常數（`MIN_LISTING_MONTHS`、`MONTH_END_TURNOVER_FLOOR`、`INDUSTRY_ALLOWED`）如需調整，
  必須有規則本身的業務理由（如產業分類範圍擴充），不得為了讓特定歷史回測績效好看而調整
  ——這是延續 ADR 0006 反 data-snooping 原則的直接應用。

## 實作與驗證

- 程式：`universe.py`（篩選邏輯、資料抓取、限流韌性、CLI）、`tests/test_universe.py`
  （45 個純本地 fixture 測試：三規則通過/剔除案例（含兩筆 pre-registration 修正的字串）＋
  快照不可變性＋provisional/rules_version 重建政策＋限流退避/paced 模式＋
  build_snapshot 全流程，無網路依賴）。
- 實跑 `--current` 結果、12 檔既有 universe 核對結果：見 commit 訊息與 HANDOFF.md（此 ADR
  聚焦決策本身，實跑數字為一次性驗證證據，記錄於交接文件避免 ADR 隨資料變動而需要修訂）。
- 2026-06 首次實跑快照因 FinMind 限流含 850 檔缺值，依 provisional 政策標記為暫定、
  待重跑補齊（長回填由主對話另行安排，不在本次變更範圍內執行）。
