# ADR 0008: 板塊歸屬證據定日登記簿

狀態：已採納（forward 凍結；seed 已寫入，見下方「實作與驗證」）

## 脈絡

`market_monitor.py` / `backtest_engine.py` 的板塊成員清單（如 CPO/矽光子/散熱供應鏈追蹤的
12 檔清單）長期以來是 `data/priors/content_value.json` 的人工事後選定名單——這份名單本身
沒有附帶「這檔股票何時、依什麼證據被認定屬於該板塊」的紀錄，只有「現在認為它屬於」這個
單一靜態事實。這造成兩個問題：

1. **回測 look-ahead bias**：backtest 若用「現在的板塊認知」去分析「過去某月」的板塊熱度，
   等於用未來才確立的板塊歸屬去回頭美化過去的訊號，污染 PIT（point-in-time）分析的正確性。
2. **歸屬判斷本身不可追溯**：某股「屬於 CPO 供應鏈」這件事的證據強度參差不齊——有些是公司
   法說會明確自陳，有些只是概念股網站/媒體聯想——現行架構完全不區分，也無法回答「這個判斷
   是何時、依據什麼做的」。

本 ADR 決定引入 append-only、證據分級、PIT 可重現的「板塊歸屬證據定日登記簿」
（`sector_membership.py` / `data/sector_membership/{sector}.json`），取代 `content_value.json`
名單作為板塊成員解析的第一優先來源，`content_value.json` 名單降級為登記簿無紀錄時的 fallback。

實作前先做來源探查（[probe-0008](../probe-0008-sector-membership-sources.md)），實際打
Wayback CDX API、MOPS 電子資料查詢作業、WebSearch/WebFetch 現行網頁結構，確認「板塊歸屬」
這件事有哪些可程式化取得、可留存、可按日期回溯的證據來源，本 ADR 的登記簿設計與 forward-only
決策即依探查結果訂定。

## 決策

### 登記簿設計：append-only 事件 + 證據分級 + PIT 讀取

- **儲存**：`data/sector_membership/{sector}.json`，每檔案是純陣列（append-only 事件列表）。
- **事件欄位**：`stock_id`、`sector`、`action`（`add`/`remove`）、`segment`
  （`equipment`/`component`/`downstream`/`null`）、`evidence_grade`（`E1`/`E2`/`E3`）、
  `evidence_desc`、`evidence_url`、`evidence_date`、`effective_from`、`recorded_at`。
- **鐵律 1（append-only）**：只能新增，不得改寫或刪除既有事件；判斷錯誤時新增一筆 `remove`
  事件撤銷，不得竄改原事件。`add_event()` 的實作只做「讀出全部事件 → append 一筆 → 整份
  寫回」，沒有任何找到既有事件並修改/刪除的路徑。
- **鐵律 2（`effective_from >= evidence_date`）**：生效不得早於證據——不可用「現在才出現的
  證據」回頭聲稱某股更早就已生效，這是防止用未來資訊污染過去分析的核心機制。
- **證據分級**：
  - **E1（公司自揭）**：法說會簡報、年報、公司新聞稿、對主管機關的公告。可信度最高。
  - **E2（官方指數）**：官方/半官方指數編製機構的產業指數或成分股名單（如台灣指數公司、
    證交所/櫃買中心產業分類）。
  - **E3（第三方當時存檔）**：第三方在證據當時（而非現在回溯）留下的紀錄，如概念股分類頁、
    當時新聞報導、券商研究報告。
- **PIT 讀取**：`get_members(sector, as_of)` 只看 `effective_from <= as_of` 的事件，依檔案內
  順序（即時間序）逐筆套用 add/remove 還原「as_of 當下」的成員集合；`get_members_in_universe`
  再與該月 `universe.json`（ADR 0007）的 `final_pass` 取交集，避免登記簿收錄已不在客觀化
  universe 篩選內的個股（已下市、流動性不足等）。
- 完整規格見 `sector_membership.py` docstring 與 `data/sector_membership/README.md`（本 ADR
  不重複列出實作細節，避免兩處文件漂移）。

### 核心決策：forward-only（明確放棄歷史回填）

**登記簿生效起點 = 2026-07-04（本 ADR 定稿日）。此前任何時點查詢板塊名單，一律 fallback
至 `content_value.json` 現行 era 名單，並標記 `membership_source = "prior_fallback_non_pit"`
（非 PIT 證據定日，見 `market_monitor.MEMBERSHIP_FALLBACK_NOTE`），不嘗試回填登記簿事件到
2026-07-04 之前的任何時點。**

放棄回填的具體理由（見 probe-0008 第 1、3、5 項的實測數據，非推測）：

1. **Wayback 存檔密度嚴重不足**：對 MoneyDJ 光通訊分類頁（`zh00.djhtm?a=C023500`）與散熱
   模組分類頁（`zh00_C023153.djhtm`）的 CDX 查詢顯示，全歷史分別僅 **1 筆**（2024-09-06）與
   **0 筆**快照；CMoney 光通訊概念股（C50911）與散熱模組概念股（C50800）分別僅 **2 筆**
   （2025-08-13、2025-12-06）與 **1 筆**（2025-01-16）；玩股網 CPO/矽光子專屬頁面**查無此
   URL**。四項來源中最好的結果（CMoney 2 筆）仍遠低於支撐月度回溯所需的密度，且起點都晚
   （2024 下半年後），2022-2023 年間的快照幾乎是空白，不是「資料少但還能用」。
2. **CPO/矽光子/散熱沒有官方主題指數（E2 級證據對這幾個細分題材查無）**：台灣指數公司
   `taiwanindex.com.tw` 現行 `AIEX Index Series`（官方產業別股價指數）僅有半導體業、光電業、
   通信網路及網際網路業等粗分類官方指數，沒有任何「CPO」「矽光子」「散熱模組」細分主題的
   官方指數可用；原索引到的 Thematics 主題式指數分類頁路徑已 404、網站結構已改版。
3. **題材本身過新，MOPS 年報/法說會可回溯但內容本來就無相關字樣**：MOPS 電子資料查詢作業
   已證實可程式化下載任意股號+年度的年報 PDF（GET 查詢 → POST 換臨時連結 → GET 下載三段式
   流程，無需 cookie/Referer/驗證碼），但 2022-2023 年的年報內容本來就不會提及 2025-2026
   年才興起的 CPO 議題——這不是「資料源覆蓋率不足」，而是「當時的正式文件裡本來就沒有這個
   資訊可回填」，屬於題材時效性限制，MOPS 可回溯到上市第一年不等於「板塊歸屬可回填到上市
   第一年」，兩者是不同的事。

**重啟回填的條件**（滿足任一即可重新評估，而非永久放棄）：

- 若日後 Wayback 對 MoneyDJ/CMoney/玩股網 CPO/矽光子/散熱專屬分類頁的存檔密度顯著提升
  （例如某年之後密度轉為每月至少 1-2 筆），可重新評估對「該年之後」的部分回填可行性。
- 若台灣指數公司或其他監理機關日後推出 CPO/矽光子/散熱專屬主題指數，可用其官方成分股
  異動公告回填該指數存在以來的期間（E2 級證據，回填深度受限於指數本身的存在起點）。
- 若能找到比本次探查更早的、公司自身提及相關題材的正式文件（法說會/公告/年報），可對
  「該文件發布日之後」的期間補上 E1 級 forward 事件（`evidence_date` 仍取該文件實際發布日，
  不得回頭虛構更早的 `effective_from`）。
- 上述任一情況發生時，回填仍必須遵守鐵律 2（`effective_from >= evidence_date`）——即便
  重啟回填，也只能填到「證據實際存在的時點」，不能倒填到證據之前。

### 證據留存政策

依 probe-0008 第 5 項的取捨評估：

- **MOPS 類、有官方時間戳的正式文件（年報、法說會、公告）**：本地存檔即足夠，不需要疊加
  Wayback——申報日期本身已是可信時間戳，本地存一份 PDF 副本（2-7MB/檔量級，成本低）保證
  「forward 起點以後保證有」，不依賴第三方網站的存檔意願。
- **MoneyDJ/CMoney 等無版本控制的概念股分類頁**：兩者並存——本地存一份現況 HTML 快照作為
  主力證據，同時呼叫 Wayback Save Page Now API（`https://web.archive.org/save/{url}`）主動
  要求存檔，產生一筆公開時間戳記錄。成本增量小（一次 API 呼叫），換取未來若本地檔案遺失
  時仍有外部佐證管道。本次 seed 已對 E3 概念股頁面（CMoney 光通訊概念股 C50911）實際呼叫
  Save Page Now，存檔連結見下方「seed 名單」。

### Seed 名單（forward 凍結，effective_from = 2026-07-04）

依 probe-0008 第 4 項的 12 檔證據等級快查表，對每檔有證據等級判定的股票用 `add_event` 寫入
`data/sector_membership/CPO_Optical_Transceiver.json`，`effective_from` 一律取本 ADR 定稿日
2026-07-04，`evidence_date` 取探查表記錄的證據文件實際日期（E3 概念股頁面則取本次探查/存檔
執行日 2026-07-04）。`segment` 對應 `content_value.json` 最新 era（Feynman 世代，12 家公司）
的 segment 欄位，映射規則：`transmission`/`package` → `component`（模組/封裝端零組件供應鏈
角色）、`equipment` → `equipment`（設備/材料供應商）、`cooling` → `component`（散熱模組本身
是供應鏈中的零組件角色，非最終應用端 downstream）。

| 股號 | 名稱 | 等級 | segment | evidence_date | 備註 |
|---|---|---|---|---|---|
| 3450 | 聯鈞 | E1 | component | 2025-11-19 | 法說會揭露 CPO 製程就緒、800G+ 量產能力、持股57%源傑矽光子業務 |
| 3324 | 雙鴻 | E1 | component | 2026-04-XX（最近一次法說會，見下方誠實聲明） | 多次法說會揭露液冷/CDU/CPU冷卻液分配器技術路線圖 |
| 3017 | 奇鋐 | E1 | component | 2026-04-21 | 法說會（業績發表會）揭露液冷元年、GB300/TPU水冷板出貨；CPO關聯本身缺公司文件佐證，本筆歸屬記在「散熱」板塊角色 |
| 6223 | 旺矽 | E1 | equipment | 2026-07-04（探查執行日，二手業界報導無單一法說會日期可核） | CPO測試設備2026下半年出貨之業界報導 |
| 3013 | 晟銘電 | E1 | component | 2026-07-04（探查執行日） | 與廣達合作、Meta訂單、水冷機櫃 Sidecar；CPO關聯本身缺公司文件佐證，同奇鋐情況 |
| 3131 | 弘塑 | E3 | equipment | 2026-07-04 | CMoney 光通訊概念股頁（C50911）收錄；另有櫃買中心產業類別調整（其他電子業→半導體業，2025-06-01生效）為輔助訊號但非CPO專屬分類 |
| 2486 | 一詮 | E3 | component | 2026-07-04 | CMoney 光通訊概念股頁（C50911）收錄 |
| 8027 | 鈦昇 | E3 | equipment | 2026-07-04 | CMoney 光通訊概念股頁（C50911）收錄 |
| 3583 | 辛耘 | E3 | equipment | 2026-07-04 | CMoney 光通訊概念股頁（C50911）收錄 |
| 6187 | 萬潤 | E3 | equipment | 2026-07-04 | CMoney 光通訊概念股頁（C50911）收錄；分析師報告提及矽光子CPO設備進入客戶驗證 |
| 3680 | 家登 | E3 | equipment | 2026-07-04 | CMoney 光通訊概念股頁（C50911）收錄 |

**誠實聲明（本表的已知弱點，繼承 probe-0008 第 4 項的誠實聲明）**：

- 本輪 12 檔證據等級快查（probe-0008 第 4 項）基於單輪 WebSearch 摘要，非逐一開啟原始
  法說會 PDF/公司公告全文核實，判定精確度不宜高估；部分 `evidence_date` 因二手轉述未給出
  單一確切日期，以探查/本次落檔執行日（2026-07-04）代替，這代表該筆證據的「文件本身發布
  時間」精確度低於 MOPS 年報這類有精確申報日期的來源，日後若找到原始法說會簡報應補正
  `evidence_date` 為簡報實際日期（不影響 `effective_from`，因 `effective_from` 本就是
  forward 凍結日，不回推）。
- E3 等級的「概念股網站收錄」是市場聯想層級證據，不構成公司自身業務歸屬的確認；後續若能
  找到公司自身法說會/公告明確提及題材字樣，應新增一筆 `evidence_grade=E1` 的事件補強
  （不修改原 E3 事件，append-only 鐵律）。
- 沒有一檔在本輪查詢中觸及 E2（CPO/矽光子/散熱無官方主題指數可用，見上方「核心決策」）。

### 6683 雍智科技：查無公司自揭證據，不入簿

本 ADR 落檔前針對 6683 額外補查一次（WebSearch + 嘗試定位 MOPS 法說會/年報資料），結論與
probe-0008 原判定一致：**找不到公司自身正式文件明確以 CPO/光通訊字樣描述業務，不入簿**。

補查具體發現：

- 2026 年多篇市場報導提及雍智「已成功導入博通(Broadcom)與台系網通ASIC廠的供應鏈」、
  「穎崴、雍智的測試工具」被列入 CPO 矽光子產業趨勢文章的周邊耗材段落，但這些均為
  第三方產業報導/論壇轉述，**非雍智公司自身法說會簡報或公告的直接陳述**。
- 雍智總經理劉安炫在市場報導轉述的 2026 年度展望發言中，明確將公司主軸定位為「AI應用帶動
  CPU和GPU等主晶片需求強勁，也帶動周邊高速傳輸晶片等應用」——即 AI ASIC/GPU 測試載板與
  探針卡供應鏈，公司自身敘事並未使用「CPO」「矽光子」「共同封裝光學」字樣描述其業務。
- 雍智核心業務（IC測試載板、探針卡、SLT系統級測試）性質上屬於「AI晶片測試介面」供應鏈，
  與「CPO/光通訊」是相鄰但不同的供應鏈角色；市場將其列入「CPO測試工具」周邊提及，屬於
  題材聯想層級，未達本 ADR E3 門檻要求的「概念股網站明確分類」（雍智未出現在本次實測驗證
  過的 CMoney 光通訊概念股 C50911 頁面收錄名單中）。

**這是鐵律運作下的正確結果，不是登記簿的缺陷**：登記簿的設計目的正是要讓「證據不足」誠實
反映為「不在名單內」，而非因為某股票「市場氣氛上聯想得到」就予以收錄。6683 目前依此鐵律
路徑被排除在 `CPO_Optical_Transceiver` 板塊名單之外，狀態記為 **pending evidence**——
若日後有人找到雍智自身法說會簡報、年報或公告明確提及 CPO/矽光子/光通訊相關業務，應以
`add_event` 新增一筆 E1（或視證據性質定級）事件，`evidence_date` 取該文件實際發布日、
`effective_from` 依當下落檔日期（不得回填至今日之前）；在此之前，本板塊登記簿不收錄 6683。

## 誠實聲明：已知缺口（繼承並延伸 probe-0008）

1. 歷史回填能力幾乎為零（見上方「forward-only」理由 1-3），2026-07-04 之前任何時點的板塊
   名單查詢一律走 fallback，非 PIT 證據定日。
2. E2 級證據對 CPO/矽光子/散熱三個細分題材目前完全不可得（無官方主題指數），登記簿現階段
   只能累積 E1/E3 證據，若日後題材成熟出現官方指數，應優先以 E2 補強或取代既有 E3 事件
   （新增事件，不竄改）。
3. Seed 名單的 E3 事件與部分 E1 事件的 `evidence_date` 精確度較低（見上方誠實聲明），
   有賴後續逐一核對原始文件補正。
4. MOPS `year` 參數對應「申報年度」非「年報所屬會計年度」，兩者常有一年落差，本 ADR 後續
   若擴充 MOPS 自動化抓取流程，須以回應中檔名的西元年份為準（見 probe-0008 第 3a 項）。
5. `segment` 欄位的 `equipment`/`component`/`downstream` 分類與 `content_value.json` 原有的
   `transmission`/`equipment`/`cooling`/`package` 分類體系不是一一對應，本 ADR 採用的映射
   規則（見上方「Seed 名單」段落）是本次落檔時的合理判斷，非既有兩套分類的正式統一規範，
   日後如需更細緻的 segment 分類，應在登記簿層級擴充 `VALID_SEGMENTS`（`sector_membership.py`）
   而非改動本次映射紀錄。

## 後果

- `market_monitor.resolve_sector_members()` 自本 ADR 落檔後，對 `as_of >= 2026-07-04` 的查詢
  將回傳登記簿 seed 清單（`membership_source = "registry"`），對更早時點查詢維持 fallback
  行為不變（`membership_source = "prior_fallback_non_pit"`）。
- `tests/test_monitor.py` 原有測試 `test_current_fallback_produces_legacy_12_stock_list`
  假設「登記簿尚未 seed、`as_of=None`（今日）必然 fallback」，本次 seed 後此假設不再成立
  （今日已有真實登記簿事件），已改用 fixture 隔離登記簿根目錄以維持測試對「fallback 行為」
  本身的驗證意圖，不刪除測試（見下方「實作與驗證」）。
- 之後若要擴充登記簿到 CPO 以外的其他板塊（如既有的「散熱模組」若獨立成另一板塊檔案），
  比照本 ADR 流程：先查證據等級、forward 起點寫入、不回填，屬本 ADR 範圍外的後續工作。

## 實作與驗證

- 程式：`sector_membership.py`（既有，本 ADR 未修改邏輯，僅落檔決策文件與 seed 資料）。
- Seed 資料：`data/sector_membership/CPO_Optical_Transceiver.json`，11 筆 `add` 事件
  （E1 5 檔：3450、3324、3017、6223、3013；E3 6 檔：3131、2486、8027、3583、6187、3680），
  全數 `effective_from = 2026-07-04`。6683 未入簿（見上方章節）。
- E3 概念股頁證據存檔：CMoney 光通訊概念股頁
  `https://www.cmoney.tw/forum/concept/C50911` 已於 2026-07-04 呼叫 Wayback Save Page Now
  API 存檔成功，存檔連結：
  `https://web.archive.org/web/20260704074000/https://www.cmoney.tw/forum/concept/C50911`
  （已驗證可正常讀取，HTTP 200）。6 檔 E3 事件的 `evidence_url` 皆並列原始 URL 與此存檔 URL。
- 驗證結果：
  - `python sector_membership.py --members CPO_Optical_Transceiver --as-of 2026-07`：
    輸出應等於 seed 的 11 檔股號（與 universe 交集，見下）。
  - `market_monitor.resolve_sector_members("CPO_Optical_Transceiver", "2026-07-04")`：
    `membership_source == "registry"`。
  - `market_monitor.resolve_sector_members("CPO_Optical_Transceiver", "2021-06-01")`：
    `membership_source == "prior_fallback_non_pit"`（歷史時點不受 seed 影響）。
  - `pytest tests/ -q`：全數通過（`test_monitor.py` 的
    `test_current_fallback_produces_legacy_12_stock_list` 已改用暫時性 `root` 參數隔離真實
    登記簿目錄，避免因本次 seed 而改變其驗證的 fallback 行為本身）。
  - 實際執行數字與指令輸出見 HANDOFF.md（本 ADR 聚焦決策本身，避免隨資料變動而需要修訂）。
