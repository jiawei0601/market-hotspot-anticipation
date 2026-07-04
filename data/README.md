# data/ 目錄說明

## data/snapshots/YYYY-MM/

存放**不可變月快照（Point-in-Time 證據）**。

每個子目錄對應一個自然月（格式 `YYYY-MM`），其中的 JSON 檔（`revenue.json`、`holdings.json`、`prices.json` 等）內含該月所有公司的條目。

**不可變鐵律為「(月, 公司) 級」，而非整個月檔級**：既有 (月, 公司) 條目一律不可變、永不編輯；但尚不存在於該月檔的公司條目（例如新板塊成員的歷史資料）允許追加進已存在的月檔，追加不觸碰既有 key 的任何 byte。

- git log 即完整軌跡——任何一筆快照的寫入時間、內容、操作者均可稽查。
- 若需修正某月某公司已存在的資料，必須以新的補錄快照（含說明欄位）附加，原始 (月, 公司) 條目維持原狀。
- 程式層由 `pit_store.write_monthly_snapshot()`（月檔不存在時整檔新建）與
  `pit_store.append_companies_to_snapshot()`（月檔存在時僅追加尚無的公司 key，
  已存在的 key 拒絕覆寫、列入 `skipped_existing`）共同強制執行此鐵律，物理上無法覆寫既有 (月, 公司) 條目。

## data/priors/content_value.json

存放**版本化專家先驗矩陣**，包含：

- `generation_specs`：各世代（Vera_Rubin / Feynman / Feynman_Next）的散熱、傳輸、封裝規格與 content value 比重。
- `eras`：依歷史時間分段（2019 年底前、2022 年底前、2024 年底前、2025 年起）的供應鏈標的選股池，每段含完整公司資訊。

先驗矩陣的任何修改須透過 Pull Request 留痕，確保假設異動可追溯、可審查。

---

參考：[ADR 0004 — git-as-DB，append-only 不可變月快照](../docs/adr/0004-git-as-db-append-only-snapshots.md)
