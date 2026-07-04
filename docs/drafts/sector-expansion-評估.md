# 板塊擴充評估草案：Thermal_Cooling（散熱）與 Advanced_Packaging（先進封裝）

狀態：草案（供主對話後續套用 `constants.py` CHINESE_MAPPING 與 `data/priors/sector_specs.json`）
落檔日期：2026-07-04
方法：比照 ADR 0008 / probe-0008 流程（WebSearch 逐檔查證 + CMoney 概念股頁 E3 + Wayback Save Page Now 存檔）
執行者：Claude Code subagent 分工（散熱、先進封裝各一組研究）+ 主對話彙整/落檔/驗證

---

## 一、Thermal_Cooling（散熱）

### 最終入簿清單（14 檔，`data/sector_membership/Thermal_Cooling.json`）

| 股號 | 名稱 | 等級 | segment | evidence_date | 備註 |
|---|---|---|---|---|---|
| 3017 | 奇鋐 | E1 | component | 2026-04-21 | 法說會：液冷元年、GB300/TPU水冷板出貨 |
| 3324 | 雙鴻 | E1 | component | 2026-04-15 | 法說會：液冷/氣冷方案，水冷產品占比51%→55% |
| 3013 | 晟銘電 | E1 | component | 2025-11-13 | 法說會簡報：液冷產品占比增加、防漏液冷專利 |
| 2421 | 建準 | E1 | component | 2026-05-08 | 法說會：水冷板首批出貨、氣冷→液冷→浸沒式路線圖 |
| 3483 | 力致 | E1 | component | 2025-08-20 | 法說會：水冷板、CDU，新莊廠已投產 |
| 3338 | 泰碩 | E1 | component | 2025-08-20 | 法說會：伺服器占比35%、水冷產品占比17%（**注意：起點名單「3339」為股號誤植，正確為3338**） |
| 6230 | 尼得科超眾 | E1 | component | 2025-08-29 | 法說會：水冷板與分歧管開發，水冷占比展望2-5%→10% |
| 8996 | 高力 | E1 | component | 2025-09-03 | 法說會/年報：CDU/CDM液冷占比3%→15-20% |
| 2308 | 台達電 | E1 | component | 2026-04-30 | 法說會：水冷產品(冷水板/CDU/Sidecar)占比<1%→8-9% |
| 6831 | 邁科 | E1 | component | 2026-03-27 | 法說會：AI伺服器液冷占比逾50%、浸沒式水冷、AWS ASIC認證 |
| 6805 | 富世達 | E1 | component | 2026-03-05 | 法說會：伺服器（含水冷快接頭UQD/MQD）占比5.3%→36.3% |
| 3653 | 健策 | E1 | component | 2026-07-04（精確度低，見誠實聲明） | 財報/法人報告引述均熱片切入微通道液冷 |
| 2354 | 鴻準 | E3 | component | 2026-07-04 | CMoney 散熱模組概念股頁（C50800）收錄 |
| 6591 | 動力-KY | E3 | component | 2026-07-04 | CMoney 散熱模組概念股頁（C50800）收錄；未查得公司自身法說會數字佐證 |

**E1 = 12 檔，E3 = 2 檔。**

### ∩ universe（2026-06 快照，`get_members_in_universe`）後成員（11 檔）

`['2308', '2354', '2421', '3013', '3017', '3324', '3338', '3483', '3653', '6805', '8996']`

**排除 3 檔**：6230（尼得科超眾）、6831（邁科）不在 `final_pass`（ADR 0007 篩選未通過，非登記簿問題——查 `data/snapshots/2026-06/universe.json` 的 `records`，兩檔皆存在且非下市，應是流動性或上市天數規則篩掉；6591 未在此份 universe 快照列出）。此為 universe 客觀篩選的正常結果，登記簿本身仍保留全部 14 檔事件（不因 universe 排除而移除登記）。

### Pending 清單（研究過但證據不足、未入簿）

| 股號 | 名稱 | 缺什麼 |
|---|---|---|
| 3037 | 欣興 | ABF載板龍頭，未見自身散熱業務揭露 |
| 3413 | 京鼎 | 半導體設備廠，未提及散熱業務 |
| 2059 | 川湖 | 滑軌龍頭，僅機構相容液冷管路，非功能性散熱零組件本身 |
| — | 協禧、動力-KY(強度另評，已改列E3)、鴻海/廣達/緯創/緯穎 | 純downstream組裝廠，散熱僅是採購項目非自身業務，不建議收錄 |

### Wayback 存檔

CMoney 散熱模組概念股頁 `https://www.cmoney.tw/forum/concept/C50800` 已於 2026-07-04 呼叫 Wayback Save Page Now API 存檔成功（**首次呼叫未帶 `?force=1` 時回傳既有 2025-01-16 舊快照**，改用 `?force=1` 強制產生新快照）：

- 存檔連結：`https://web.archive.org/web/20260704084656/https://www.cmoney.tw/forum/concept/C50800?force=1`
- 已用 curl 驗證：HTTP 200，內容含「散熱模組」字樣與 3017/3324/3013/2421/3483/6230/8996 等股號，確認存檔內容有效。
- 存檔成功數：1（成功，含 force 重試 1 次）。

### 建議 sector_specs.json 內容草案

```json
"Thermal_Cooling": {
  "current_generation": "Vera_Rubin",
  "next_generation": "Feynman",
  "future_generation": "Feynman_Next",
  "narrative_hint": "AI 資料中心液冷元年直接受益者：GPU 世代熱功耗持續攀升（Vera_Rubin→Feynman），氣冷轉液冷（CDU/水冷板/Sidecar/浸沒式）滲透率加速，供應鏈內容價值隨世代交替擴大"
}
```

**世代框架適用性判斷**：散熱板塊的世代驅動邏輯與既有 CPO_Optical_Transceiver 高度相似（都跟隨 NVIDIA GPU 世代 Vera_Rubin→Feynman 的熱設計功耗需求走），沿用相同的 `current_generation`/`next_generation`/`future_generation` 框架合理。但散熱的世代切換訊號比 CPO 更「連續」（液冷滲透率是漸進曲線，不是單一世代切換點），若日後要精細化，可考慮新增「液冷滲透率」量化欄位，而非套用純世代二分法；本草案先沿用既有框架、不擴充 schema，留待實測後再評估是否需要。

### 建議補入 constants.py CHINESE_MAPPING 對照表

（新增股票，未出現在既有 CHINESE_MAPPING 中；`type` 依 2026-06 universe 快照 `records` 欄位查證）

| stock_id | 中文名 | 建議 mapping key | universe type |
|---|---|---|---|
| 2421 | 建準 | `2421.TW` → `2421.建準` | twse |
| 3483 | 力致 | `3483.TWO` / `3483.TW` → `3483.力致` | 待查（力致為上櫃，建議先查證） |
| 3338 | 泰碩 | `3338.TW` → `3338.泰碩` | twse |
| 6230 | 尼得科超眾 | `6230.TWO` → `6230.尼得科超眾` | 不在最新universe final_pass但records存在，type待查 |
| 8996 | 高力 | `8996.TWO` → `8996.高力` | 待查（高力為上櫃） |
| 2308 | 台達電 | `2308.TW` → `2308.台達電` | twse |
| 6831 | 邁科 | `6831.TW` → `6831.邁科` | 不在最新universe final_pass但records存在，type待查 |
| 6805 | 富世達 | `6805.TWO` → `6805.富世達` | 待查（富世達為上櫃） |
| 3653 | 健策 | `3653.TW` → `3653.健策` | 待查 |
| 2354 | 鴻準 | `2354.TW` → `2354.鴻準` | twse |
| 6591 | 動力-KY | `6591.TW` → `6591.動力-KY` | 待查 |

（3017/3324/3013 已存在於現行 CHINESE_MAPPING，無需新增。上述 `.TW`/`.TWO` 尾碼建議主對話依 `data/snapshots/2026-06/universe.json` records 的 `type` 欄位（`twse`→`.TW`、`tpex`→`.TWO`）逐一核對後再套用，本草案未逐一驗證每檔的上市/上櫃別，僅列出已知的部分。）

### 誠實聲明（本節弱點）

1. 本輪判定基於 subagent 單輪 WebSearch 摘要，非逐一開啟原始法說會 PDF 全文核實，`evidence_date` 精確度不宜高估（尤其 3653 健策未取得確切法說會日期，以落檔執行日代替）。
2. 未觸及任何 E2 證據（無官方散熱主題指數，符合 probe-0008 既有結論）。
3. 6230、6831 在 universe 交集後被排除，反映的是 ADR 0007 universe 篩選規則（流動性/上市天數等），非本次證據判定有誤；登記簿本身仍完整保留這兩筆事件。
4. 2354（鴻準）、6591（動力-KY）目前只有 E3（概念股頁收錄），若後續找到公司自身法說會明確提及散熱業務具體數字，應新增一筆 E1 事件補強（不修改原 E3 事件，append-only）。

---

## 二、Advanced_Packaging（先進封裝）

### 最終入簿清單（12 檔，`data/sector_membership/Advanced_Packaging.json`）

| 股號 | 名稱 | 等級 | segment | evidence_date | 備註 |
|---|---|---|---|---|---|
| 3131 | 弘塑 | E1 | equipment | 2025-11-25 | 法說會：CoWoS/SoIC濕製程設備，2025出貨年增70-100% |
| 3583 | 辛耘 | E1 | equipment | 2026-07-04（精確度低，見誠實聲明） | 法說會：CoWoS濕製程/貼合設備為主線業務 |
| 3680 | 家登 | E1 | component | 2026-03-01（精確度低） | 法說會：CoWoS載具已通過封測龍頭廠驗證 |
| 6640 | 均華 | E1 | equipment | 2026-07-04（精確度低） | 總經理公開表示先進封裝設備占營收75%、目標90%（**起點名單「均華」股號原誤植，已更正為6640**） |
| 2467 | 志聖 | E1 | equipment | 2023-01-01（精確度低，僅知獲獎年度） | 獲台積電優良供應商獎，先進封裝設備營收占比揭露（**起點名單股號原誤植，已更正為2467**） |
| 3711 | 日月光投控 | E1 | downstream | 2026-04-29 | 法說會：LEAP先進封測業務營收上修、CoWoS委外/FoCoS擴產 |
| 6239 | 力成 | E1 | downstream | 2026-02-01（精確度低） | 董事長法說會：FOPLP資本支出400億元、2027年量產 |
| 8027 | 鈦昇 | E3 | equipment | 2026-07-04 | CMoney個股標籤列CoWoS/玻璃基板概念股 |
| 6187 | 萬潤 | E3 | equipment | 2026-07-04 | CMoney個股標籤列CoWoS/3DIC聯盟；CoWoS概念股頁archive確認收錄 |
| 6664 | 群翊 | E3 | equipment | 2026-07-04 | CMoney個股標籤列CoWoS/玻璃基板（PCB/載板乾燥設備商轉型） |
| 3374 | 精材 | E3 | downstream | 2026-07-04 | CMoney CoWoS概念股頁（C50909）收錄，台積電轉投資CIS晶圓級封裝/TSV廠 |
| 6223 | 旺矽 | E3 | equipment | 2026-07-04 | CMoney CoWoS概念股頁（C50909）archive實際解析收錄；旺矽在CPO_Optical_Transceiver.json已有獨立E1證據（CPO測試設備），本筆為先進封裝板塊獨立補強 |

**E1 = 7 檔，E3 = 5 檔。**

### ∩ universe（2026-06 快照，`get_members_in_universe`）後成員（12 檔，全數通過）

`['2467', '3131', '3374', '3583', '3680', '3711', '6187', '6223', '6239', '6640', '6664', '8027']`

無任何一檔被 universe 篩選排除。

### Pending 清單（研究過但證據不足、未入簿）

| 股號 | 名稱 | 缺什麼 |
|---|---|---|
| — | 「萬業」 | 起點名單誤記，查無此股號/公司名稱對應台股標的，建議自起點名單刪除 |
| 6147 | 頎邦 | 僅媒體零星提及WLCSP/FOSiP布局，CMoney無CoWoS/先進封裝標籤，證據不足 |
| 8150 | 南茂 | 僅媒體泛稱「受先進封裝題材帶動」，CMoney無對應標籤 |
| 2369 | 菱生 | 僅媒體提及「切入AI先進封裝布局」觀察中，CMoney無對應標籤 |

### Wayback 存檔

CMoney CoWoS概念股頁 `https://www.cmoney.tw/forum/concept/C50909` 已於 2026-07-04 呼叫 Wayback Save Page Now API 存檔成功（首次呼叫即產生新快照，未需 force 重試）：

- 存檔連結：`https://web.archive.org/web/20260704084611/https://www.cmoney.tw/forum/concept/C50909`
- 已用 curl 驗證：HTTP 200，內容含「CoWoS」「先進封裝」字樣與 3131/3583/3680/3374/6223/6640 等股號，確認存檔內容有效。
- 存檔成功數：1（首次即成功）。

### 建議 sector_specs.json 內容草案

```json
"Advanced_Packaging": {
  "current_generation": "Vera_Rubin",
  "next_generation": "Feynman",
  "future_generation": "Feynman_Next",
  "narrative_hint": "GPU 世代交替下先進封裝（CoWoS/SoIC/FOPLP/玻璃基板）產能與良率瓶頸的直接受益供應鏈：設備／材料商（弘塑、辛耘、均華、志聖）→ 封測代工（日月光投控、力成）雙層結構"
}
```

**世代框架適用性判斷**：先進封裝的世代驅動邏輯同樣鎖定 NVIDIA GPU 世代（CoWoS 產能瓶頸隨每一世代的晶片面積/HBM堆疊層數而變動），沿用既有 `Vera_Rubin`/`Feynman`/`Feynman_Next` 三代框架合理，且比散熱更適合純世代二分法（CoWoS 產能擴建本身就是以世代為單位的資本支出決策，不像液冷滲透率是連續曲線）。建議 segment 欄位在此板塊特別注意 `equipment`（設備/材料商，如弘塑/辛耘/均華/志聖/萬潤/群翊/鈦昇）與 `downstream`（封測代工本體，如日月光投控/力成/精材）兩層區分，比散熱板塊的分類更有意義，可作為後續 narrative 拆解的分析維度（例如個別追蹤「設備先行指標」vs「封測代工實際出貨」的時間差）。

### 建議補入 constants.py CHINESE_MAPPING 對照表

| stock_id | 中文名 | 建議 mapping key | universe type |
|---|---|---|---|
| 6640 | 均華 | `6640.TWO` → `6640.均華` | twse（依 records 顯示，待複核，均華為上櫃股一般應為TWO，需人工核對） |
| 2467 | 志聖 | `2467.TW` → `2467.志聖` | twse |
| 3711 | 日月光投控 | `3711.TW` → `3711.日月光投控` | twse |
| 6239 | 力成 | `6239.TW` → `6239.力成` | twse |
| 6664 | 群翊 | `6664.TWO` → `6664.群翊` | 待查（群翊為上櫃） |
| 3374 | 精材 | `3374.TWO` → `3374.精材` | 待查（精材為上櫃） |

（3131/3583/3680/6187/8027/6223 已存在於現行 CHINESE_MAPPING，無需新增。同樣提醒主對話依 universe 快照 `type` 欄位核對 `.TW`/`.TWO` 尾碼再套用。）

### 誠實聲明（本節弱點）

1. 本輪判定基於 subagent 單輪 WebSearch 摘要，非逐一開啟原始法說會 PDF/公司公告全文核實；3583（辛耘）、3680（家登）、6640（均華）、2467（志聖）、6239（力成）的 `evidence_date` 精確度偏低（未取得單一確切法說會日期，以推估月份或落檔執行日代替），日後應補正為原始文件實際日期。
2. 起點名單本身有 2 處股號誤植（均華誤記、志聖誤記）與 1 處查無對應（「萬業」），已在本文件與登記簿的 `evidence_desc` 中誠實記錄更正過程，不掩蓋研究過程中的錯誤。
3. CMoney CoWoS 概念股頁（C50909）為動態渲染頁面，WebFetch/curl 僅能取得部分靜態內容（archive 驗證有抓到 3131/3583/3680/3374/6223/6640/1560/2449/2330/3711 等股號，但頁面本身宣稱另有約13檔動態載入內容未能完整解析），故本次 E3 判定僅基於「已驗證能解析到的股號」，未逐一驗證頁面宣稱的完整清單，可能有漏收的候選（例如頁面提示但本次未能解析出的其餘個股）。
4. 未觸及任何 E2 證據（無官方先進封裝主題指數，僅半導體業粗分類有官方指數，不適用於此細分題材）。
5. 6223（旺矽）、8027（鈦昇）、6187（萬潤）、3680（家登）、3131（弘塑）、3583（辛耘）同時存在於既有 `CPO_Optical_Transceiver.json`（E3光通訊概念股頁證據）與本次新增的 `Advanced_Packaging.json`，這是刻意的——同一檔股票可以同時屬於多個板塊登記簿，只要各自有獨立證據支撐，不算重複或衝突。

---

## 三、共通事項

- 兩板塊均未觸及 E2 級證據（無官方主題指數），符合 probe-0008 對「新興細分題材缺乏官方指數」的既有結論，非本次執行疏漏。
- 兩份登記簿檔案的 `effective_from` 皆為 `2026-07-04`（forward 凍結起點，比照 ADR 0008 CPO_Optical_Transceiver 的做法），不回填至此日期之前。
- `constants.py` CHINESE_MAPPING 的實際套用（含 `.TW`/`.TWO` 尾碼最終核對）留待主對話後續處理，本次任務範圍僅產出建議對照表，未修改 `constants.py` 本身。
- `data/priors/sector_specs.json` 的實際新增亦留待主對話後續處理，本文件僅提供草案 JSON 片段供複製套用。
