# data/ 目錄說明

## data/snapshots/YYYY-MM/

存放**不可變月快照（Point-in-Time 證據）**。

每個子目錄對應一個自然月（格式 `YYYY-MM`），其中的 JSON 檔（`revenue.json`、`holdings.json`、`prices.json` 等）於月份結束後一次寫入，**永不編輯過去月份**。

- git log 即完整軌跡——任何一筆快照的寫入時間、內容、操作者均可稽查。
- 若需修正某月資料，必須以新的補錄快照（含說明欄位）附加，原始檔維持原狀。
- 程式層由 `pit_store.write_monthly_snapshot()` 強制執行 append-only 鐵律：目標檔已存在即 raise `SnapshotExistsError`，物理上無法覆寫。

## data/priors/content_value.json

存放**版本化專家先驗矩陣**，包含：

- `generation_specs`：各世代（Vera_Rubin / Feynman / Feynman_Next）的散熱、傳輸、封裝規格與 content value 比重。
- `eras`：依歷史時間分段（2019 年底前、2022 年底前、2024 年底前、2025 年起）的供應鏈標的選股池，每段含完整公司資訊。

先驗矩陣的任何修改須透過 Pull Request 留痕，確保假設異動可追溯、可審查。

---

參考：[ADR 0004 — git-as-DB，append-only 不可變月快照](../docs/adr/0004-git-as-db-append-only-snapshots.md)
