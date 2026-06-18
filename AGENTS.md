# AGENTS.md — 專案統一規則（Claude Code 與 Antigravity 共用）

> Claude Code 透過 CLAUDE.md（內含 @AGENTS.md）讀本檔；Antigravity 原生讀本檔。
> 一份規則，兩邊共用，不分叉。

## 專案慣例
- 語言 / 框架：Python 3.10+，使用 LangGraph (StateGraph) 管理多 Agent 狀態，Pydantic v2 限制結構化輸出，pandas_ta/pandas 用於數據運算。
- 風格 / 命名：
  - 變數與函式命名採用 `snake_case`。
  - 類別名稱採用 `PascalCase`。
  - 核心狀態變數名稱與 PRD 中的 `MarketHotspotState` 定義嚴格對齊。
- 測試怎麼跑：使用 pytest。執行 `pytest tests/`。
- build / run：
  - 安裝依賴：`pip install -r requirements.txt`
  - 執行掃描：`python main_agent.py --sector <SECTOR_NAME>`，例如 `python main_agent.py --sector CPO_Optical_Transceiver`

## 跨 agent 交接紀律
- repo 是唯一真相來源；交接資訊一律寫進 repo，不可只留私有記憶（Claude memory / Antigravity KI）。
- 交出前：測試綠 → commit 乾淨（絕不交髒工作區）→ 更新 HANDOFF.md → 更新 issue。
- 接手前：clean tree + pull → 讀 HANDOFF.md / issue / git log / 本檔 → 先複述現況與下一步再動手。
- 架構決策寫 docs/adr/；任務狀態走 issues。
