# ADR 0005: Agent 層「不捏造、失敗即顯」契約（no-fabrication / fail-loud）

狀態：已採納

## 脈絡
`main_agent.py` 各 Agent 節點原本在 LLM 呼叫失敗（含無 API key）時，於 `except` 中產出**硬編碼、帶具體假百分比**的「樣板」分析（如 FOCI -42.86%、弘塑 Backlog 84.50%），Critic 例外時預設 PASS，且跑滿 3 次迭代仍 FAIL 仍照常把報告寫入 `reports/`。這與 `get_llm_model` 自身註解「不以假數據混淆」及 [ADR 0003](0003-market-monitor-synthetic-to-pit-engine.md) 的可稽核原則直接衝突——一個金融分析工具會在失敗時**靜默輸出看似可信的捏造報告**，讀者無從分辨。

## 決策
Agent 層採「不捏造、失敗即顯」契約：

1. **移除所有專家節點的硬編碼 fallback**。LLM 不可用／回應錯誤即讓該 run 報錯，絕不產出假分析。
2. **Critic 例外 → raise**，不再 auto-PASS（移除橡皮圖章）。
3. **有限重試**：對暫時性錯誤（限流／逾時／網路）重試 2–3 次並退避，耗盡才 raise；重試 ≠ 造假。
4. **跑滿迭代仍未 PASS → 大聲失敗、不發布**：未通過品質審查的報告不得寫入 `reports/`；`run_hotspot_scan` 須檢查 `validation_status == "PASS"` 才發布。

## 後果
- CI 週報在缺 key 或 Gemini 持續錯誤時會**明顯失敗**（而非靜默產假報告）——預期且正確。`--daily-update`（不呼叫 LLM）不受影響。
- 未通過審查＝當週無報告，需人工或下次排程重跑。
- 任何「離線可跑」需求都不得以捏造數字達成；若未來要離線模式，僅能複述 market_monitor 實算值並強制標示降級（本 ADR 範圍內預設無此模式）。
