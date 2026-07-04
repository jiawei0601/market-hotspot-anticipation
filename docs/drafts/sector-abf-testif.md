# 板塊擴充評估草案：ABF_PCB_Substrate（ABF/PCB 載板，新板塊）與 Advanced_Packaging 測試介面擴充

狀態：草案（供主對話後續套用 `constants.py` CHINESE_MAPPING 與 `data/priors/sector_specs.json`）
落檔日期：2026-07-04
方法：比照 ADR 0008 / probe-0008 流程 —— Claude Code subagent 逐檔 WebSearch/WebFetch 查證 + CMoney/MoneyDJ 概念股頁 E3 路徑查證 + Wayback 存檔嘗試，主對話彙整/落檔/驗證。
執行備註：本輪執行途中曾因 Anthropic 服務端限流中斷一次，恢復後以 `--list` 確認登記簿無半寫入狀態才續作，無重複事件。

---

## 一、ABF_PCB_Substrate（ABF/PCB 載板，新板塊）

主題敘事：高速運算（AI 伺服器）與 HBM 需求帶動 ABF 載板／高速 CCL 報價調升。載板/CCL 廠 segment 一律 `component`。

### 最終入簿清單（6 檔，`data/sector_membership/ABF_PCB_Substrate.json`，全新檔案）

| 股號 | 名稱 | 等級 | segment | evidence_date | 備註 |
|---|---|---|---|---|---|
| 3037 | 欣興 | E1 | component | 2026-02-25 | 法說會：載板 AI 占比 2025 年 40%→2026 目標 60%、ABF 稼動率約 90%、全球 ABF 前三大、Q1 ABF 漲價幅度大於上季 |
| 8046 | 南電 | E1 | component | 2026-03-17 | 法說會：ABF/BT 載板稼動率高檔、往 >140mm/30 層以上高階規格、AI/HPC 營收占比 16-18%、供需缺口恐擴大至 2028 |
| 3189 | 景碩 | E1 | component | 2026-03-10 | 法說會：ABF 載板占營收約 46%、ABF/HPC 占比 24%、切入 Google TPU/Meta AI 加速器、三年 235 億資本支出擴 ABF 產能 |
| 2383 | 台光電 | E1 | component | 2026-03-12 | 法說會：NVIDIA OAM/UBB 主機板 CCL 主要供應商、M7 以上占比逾 6 成、M9 次世代材料 2026H2 量產、Q2 全面漲價。**獨立於既有 LEO_Satellite 登記（低軌衛星 CCL E3）的 AI 高速 CCL 敘事證據，且本筆等級為 E1** |
| 6274 | 台燿 | E1 | component | 2026-05-06 | 法說會：低損耗高速材料（ELL&SLL 38% + VLL&LL 32%）合計 70%、對應 AI 伺服器/800G 交換器、M6/M7 升級 M8 |
| 6213 | 聯茂 | E1 | component | 2026-05-28 | 法說會：AI ASIC 供應 AWS/Meta 的 M7/M8 材料、M8-M9 全系列送樣認證因應 1.6T 交換器、玻纖布缺貨全面漲價 |

**E1 = 6 檔，E3 = 0 檔。** 6 檔全數以公司法說會揭露內容（財經媒體轉述）達 E1，無一檔依賴 E3 概念股頁作為主要證據；概念股分類頁僅作交叉佐證。6213 聯茂為查證過程主動擴充（原候選名單即列出），證據扎實而納入。

### ∩ universe（2026-06 快照回溯適用於 2026-07 查詢，`get_members_in_universe`）後成員（6 檔，全數通過）

`['2383', '3037', '3189', '6213', '6274', '8046']`

無任何一檔被 universe 篩選排除。

### Pending 清單（研究過但證據不足、未入簿）

| 股號 | 名稱 | 缺什麼 |
|---|---|---|
| 2368 | 金像電 | 本業為伺服器板/高速 PCB（使用 CCL 的下游），非 ABF 載板/CCL 製造本身；查無自身法說會提及 ABF 載板業務，市場分類頁亦將其與 ABF 三雄明確區分。若日後另立「AI 伺服器 PCB」板塊可再評估 |
| 3044 | 健鼎 | 多篇分析明確指出「主要以 PCB 為主，並非直接生產 ABF 載板」，查無自身文件提及 ABF/CCL 業務 |
| 5439 | 高技 | 本業 PCB 而非 ABF 載板；法說會談 AI 伺服器/AI ASIC 營收占比（35%→50%+），非載板/CCL 本業敘事 |
| 2367 | 燿華 | 法說會（2025-12-12）談 AI 伺服器/800G/1.6T/低軌衛星應用，但主力為 HDI/軟硬板/高頻板，未提及 ABF 載板或 CCL 為核心產品線 |

四檔共同點：屬「廣義 AI 伺服器 PCB」而非本板塊主題敘事（載板/CCL 報價調升）的直接參與者，不為湊數放寬標準。

### E3 概念股分類頁與 Wayback 存檔

E3 路徑本身可行（存在專屬分類頁），但本輪 6 檔全數達 E1，分類頁僅作輔助交叉佐證，未作為任何一筆事件的主要證據等級：

| 來源 | URL | Wayback 狀態 |
|---|---|---|
| CMoney IC 載板概念股 | `https://www.cmoney.tw/forum/concept/C50852` | 既存快照 `https://web.archive.org/web/20251120024756/...`（2025-11-20，CDX 查證） |
| CMoney 銅箔基板概念股 | `https://www.cmoney.tw/forum/concept/C50866` | 既存快照 `https://web.archive.org/web/20251121102540/...`（2025-11-21，CDX 查證，另有 2025-01/2025-10 共 3 筆） |
| MoneyDJ IC 基板同業頁 | `https://www.moneydj.com/z/zh/zha/zh00.djhtm?a=C023331` | CDX 查證 0 筆快照（與 probe-0008 觀察的 MoneyDJ 稀疏模式一致） |
| CMoney ABF 類股分類 | `https://www.cmoney.tw/forum/category/C30021` | 未存檔（category 頁非 concept 頁，僅記錄存在） |

**Wayback Save Page Now 本日不可用**：多次呼叫 SPN 端點（`web.archive.org/save/{url}`）皆逾時或回 HTTP 520/429（服務端限流），新快照成功數 = 0。因兩個 CMoney concept 頁皆有 2025-11 的既存近期快照可引用、且本板塊無任何事件以 E3 為主要等級，不影響本次入簿證據有效性；建議日後 SPN 恢復時對 C50852/C50866 補打一次產生 2026-07 時點快照。

### 建議 sector_specs.json 內容草案

```json
"ABF_PCB_Substrate": {
  "current_generation": "Vera_Rubin",
  "next_generation": "Feynman",
  "future_generation": "Feynman_Next",
  "narrative_hint": "高速運算與 HBM 需求帶動載板/CCL 報價調升：GPU/AI ASIC 晶片面積與 HBM 堆疊層數隨世代擴大，ABF 載板往大尺寸/高層數規格升級（供需缺口）、CCL 材料等級隨傳輸速率升級（M7→M8→M9），ABF 三雄（欣興/南電/景碩）與 CCL 三雄（台光電/台燿/聯茂）雙軌結構；漲價循環與材料升級是連續訊號，可用「ABF 稼動率」「M7 以上占比」「漲價幅度」等連續指標輔助世代框架"
}
```

**世代框架適用性判斷：適用但混合**。ABF 載板供需缺口與 CCL 材料等級升級都直接綁定 GPU/AI ASIC 世代（晶片尺寸、HBM 層數、傳輸速率），沿用 `Vera_Rubin`/`Feynman` 框架合理；但報價調升是連續訊號（類似散熱的液冷滲透率），非單一切換點，建議輔以連續指標追蹤。

### 建議補入 constants.py CHINESE_MAPPING 對照表

（`type` 依 2026-06 universe 快照 `records` 欄位以 `get_universe_type_map` 逐檔查證）

| stock_id | 中文名 | 建議 mapping key | universe type |
|---|---|---|---|
| 3037 | 欣興 | `3037.TW` → `3037.欣興` | twse |
| 8046 | 南電 | `8046.TW` → `8046.南電` | twse |
| 3189 | 景碩 | `3189.TW` → `3189.景碩` | twse |
| 6274 | 台燿 | `6274.TWO` → `6274.台燿` | tpex |
| 6213 | 聯茂 | `6213.TW` → `6213.聯茂` | twse |

（2383 台光電已存在於現行 CHINESE_MAPPING（`2383.TW`），無需新增。）

### 誠實聲明（本節弱點）

1. **6 檔 E1 證據全數為財經媒體對法說會的轉述**（自由財經、鉅亨網、vocus、StockFeel、富果、uanalyze 等），非逐一開啟 MOPS 法說會簡報原始 PDF 核實——與同日落檔的 Advanced_Packaging 測試介面三檔（已下載 MOPS 原件）證據強度有差，建議日後比照補核原件。法說會日期本身精確度高（媒體報導有明確舉行日）。
2. 未觸及任何 E2 證據（無官方 ABF 載板/CCL 主題指數，僅半導體/電子零組件粗分類官方指數，符合 probe-0008 既有結論）。
3. Wayback SPN 本日服務端不可用（520/429），新快照 0 筆，僅引用既存 2025-11 快照；因無 E3 主要證據事件，實質影響為零，但「2026-07 時點的概念股頁內容」未留下第三方時間戳，僅有 CDX 既存快照佐證至 2025-11。
4. 2383 台光電同時存在於 `LEO_Satellite.json`（E3）與本板塊（E1），為刻意設計：同一股票可屬多板塊，各板塊證據獨立成立；本筆 AI 高速 CCL 敘事與低軌衛星 CCL 敘事互不重複使用證據。
5. pending 四檔（金像電/健鼎/高技/燿華）的排除是基於「本業非載板/CCL 製造」的主題敘事邊界判斷，非公司品質判斷；若日後板塊定義放寬為「AI 伺服器 PCB 供應鏈」則應重新查證，屆時用 add_event 新增、不回填。

---

## 二、Advanced_Packaging 測試介面擴充（既有登記簿，僅 add_event 追加）

主題敘事：AI ASIC/GPU 測試介面供應鏈（探針卡、測試載板、測試座、系統級測試），segment 一律 `component`。既有 12 筆事件未做任何修改（append-only 鐵律），本次僅追加 3 筆。

### 追加入簿清單（3 檔，`data/sector_membership/Advanced_Packaging.json` 第 13-15 筆事件）

| 股號 | 名稱 | 等級 | segment | evidence_date | 備註 |
|---|---|---|---|---|---|
| 6515 | 穎崴 | E1 | component | 2026-05-14 | 法說會簡報原件（MOPS，**已直接下載驗證內文**，59 頁）：CPO/CPC 測試流程、GPU 功耗路線圖 800W→1200W、ASIC/HBM 先進封裝測試挑戰、HyperSocket 測試座；另官網新聞稿（2025-03-17）自述「semiconductor test interfaces for the AI era」、AI/HPC 營收占比逾 50% |
| 6510 | 精測 | E1 | component | 2025-10-29 | 2025Q3 法說會簡報原件（MOPS，**已直接下載驗證內文**）：HPC 占營收 40%、探針卡營收 HPC 占比 57.9%、高腳數探針卡（~65k pin）；官網產品頁明列 BR 系列適用 GPU/APU/CPU、NS 系列適用 ASIC |
| 6683 | 雍智科技 | E1 | component | 2025-10-22 | 2025 法說會簡報原件（MOPS，**已直接下載逐頁解析**，16 頁）：市場應用明列 AI/ASIC/CPU/GPU/高速運算；營業項目=晶圓測試載板（Probe Card/Interposer/Probe Head）+ IC 測試載板（Load Board/Burn-in Board/SFT）；前段測試載板占比 2025H1 達 33% |

**E1 = 3 檔，E3 = 0 檔。** 三檔證據等級為本專案登記簿目前最強——全數取得 MOPS 法說會簡報**原始 PDF 並下載解析內文**（`mopsov.twse.com.tw/nas/STR/` 正式存檔路徑，官方時間戳），非媒體二手轉述，優於既有多數 E1 事件的證據形態。

**6683 雍智科技的證據升級說明**：ADR 0008 曾判定雍智在 `CPO_Optical_Transceiver` 板塊「找不到公司自揭證據，不入簿（pending evidence）」——該判定針對 CPO/矽光子主題，維持不變。本次是**不同主題（AI ASIC/GPU 測試介面）下找到公司自身法說會簡報原件**，其市場應用頁明列 AI/ASIC/CPU/GPU，構成本板塊的 E1 證據，與 CPO 板塊的不入簿判定並存不矛盾——這正是鐵律設計的預期運作方式：按板塊、按證據各自定日。注意公司文件用語為「SFT」（系統級測試），非市場慣用「SLT」，`evidence_desc` 照公司用語記錄。

**6223 旺矽**：已在本登記簿中（第 12 筆 E3 事件），本次未重複研究、未重複寫入。

### ∩ universe（2026-06 快照回溯，`get_members_in_universe`）後成員（15 檔，全數通過）

`['2467', '3131', '3374', '3583', '3680', '3711', '6187', '6223', '6239', '6510', '6515', '6640', '6664', '6683', '8027']`

新增 3 檔（6510/6515/6683）皆在 universe `final_pass` 內，無排除。

### Pending 清單

無——本次三檔候選全數達 E1 入簿。

### E3 概念股分類頁查證結果與 Wayback

**查無**「測試介面」「探針卡」「半導體檢測」專屬 CMoney 概念股分類頁（concept 總覽現有 CoWoS/ASIC/TPU/HBM/次世代半導體等分類，測試介面未列為獨立分類）。E3 路徑對本子題不可得，但三檔皆達 E1，無需 E3 兜底。本節證據全為 MOPS 正式存檔文件（官方時間戳），依 ADR 0008 證據留存政策**不需疊加 Wayback**；本次 Wayback SPN 新快照數 = 0（無需要存檔的 E3 頁面，且 SPN 本日服務端不可用）。

### 建議補入 constants.py CHINESE_MAPPING 對照表

（`type` 依 2026-06 universe 快照 `records` 欄位以 `get_universe_type_map` 逐檔查證）

| stock_id | 中文名 | 建議 mapping key | universe type |
|---|---|---|---|
| 6515 | 穎崴 | `6515.TW` → `6515.穎崴` | twse |
| 6510 | 精測 | `6510.TWO` → `6510.精測` | tpex |

（6683 雍智科技已存在於現行 CHINESE_MAPPING（`6683.TWO`），無需新增。sector_specs.json 無需變動——Advanced_Packaging 板塊條目已於前次擴充建議過，本次僅增成員。）

### 誠實聲明（本節弱點）

1. 三檔 MOPS 簡報 PDF 由查證 subagent 下載解析，主對話未二次逐頁重驗內文（信任鏈為 subagent 自陳「已直接下載驗證」+ 引述具體頁碼與逐字內容，具體性高；MOPS URL 可長期引用，隨時可複驗）。
2. 穎崴 `evidence_date` 取 2026-05-14 法說會簡報日（主題契合度最高的文件）；其官網新聞稿 2025-03-17 為更早的自揭證據，已並列於 `evidence_desc`/`evidence_url`，若日後需要更早的 evidence_date 可另補一筆事件（不修改本筆）。
3. 精測官網產品頁未出現「AI」字面（明列 GPU/APU/CPU/ASIC/HPC），與板塊主題「AI ASIC/GPU 測試介面」的對齊是透過 HPC/GPU/ASIC 用語推定，非公司原文逐字使用「AI 測試介面」一詞；法說會簡報的 HPC 佔比數字補強了此對齊。
4. 未觸及任何 E2 證據（無官方測試介面主題指數）。
5. 本次未對既有 12 筆事件做任何修改或刪除（append-only 鐵律遵守，可由 git diff 驗證僅有陣列尾端追加）。
