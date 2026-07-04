import os
import sys
import json
import time
import shutil
import argparse
import datetime
import subprocess
from typing import TypedDict, List, Dict, Any
from pydantic import BaseModel, Field, field_validator

# 解決 Windows 終端機 CP950 編碼問題，若為 Windows 平台可進行編碼環境防護
import codecs
if sys.platform.startswith('win'):
    try:
        # 嘗試重新將標準輸出設定為 UTF-8 以防 emoji 或中文字元導致崩潰
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 舊版本無 reconfigure 方法時的安全 fallback
        pass

# LangChain & LangGraph 相關依賴
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

# 自動讀取本地 .env 檔案並寫入環境變數
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, val = stripped.split("=", 1)
                os.environ[key.strip()] = val.strip()

# 匯入數據監控引擎
from market_monitor import (
    MarketInformationMonitor,
    REVENUE_PROJECTION_NOTE,
    CONSENSUS_GRANULARITY_NOTE,
    BACKLOG_SIGNAL_NOTE,
    MEMBERSHIP_SOURCE_FALLBACK,
    MEMBERSHIP_FALLBACK_NOTE,
)

# 1. 狀態定義 (TypedDict) - 升級以包含下下一代能見度、設備訂單與預期差共識分析
class MarketHotspotState(TypedDict):
    target_sector: str                  # 目標行業/技術板塊 (例如: "CPO_Optical_Transceiver")
    current_generation: str             # 當前主流架構 (例如: "Vera_Rubin")；查無板塊規格時為 "N/A"
    next_generation: str                # 下一代架構 (例如: "Feynman")；查無板塊規格時為 "N/A"
    future_generation: str              # 下下一代架構 (例如: "Feynman_Next")；查無板塊規格時為 "N/A"
    narrative_hint: str                 # 板塊敘事框架提示句（來自 sector_specs.json，查無則為空字串）
    sector_spec_missing: bool           # True 表示該板塊未登記世代規格，各 expert 禁止套用 GPU 世代敘事、禁止編造世代名

    # 專家產出資料
    supply_chain_analysis: Dict[str, Any]      # 包含下下世代替代風險分析
    pricing_revenue_analysis: Dict[str, Any]   # 包含設備 Backlog 領先指標分析
    media_story_anticipation: Dict[str, Any]   # 包含共識度過濾與第二層思考操作規劃
    
    # 報告與評審狀態
    feasibility_report_draft: str       # 報告草稿 (Markdown)
    critic_feedback: str                # 評審反饋
    iteration_count: int                # 自我修正迭代次數
    validation_status: str              # 審查狀態: "PASS" 或 "FAIL"
    as_of_date: str                     # 回測基準點時間 (可選，預設空字串表示最新)

# 2. Pydantic 結構化 Critic 輸出定義 - 強制審查超前指標
class CriticDecision(BaseModel):
    validation_status: str = Field(
        ...,
        description="審查報告品質。報告必須同時包含：1. 18-24個月下下世代替代風險；2. 設備拉貨領先度 (Backlog YoY) 定量數據，"
                     "但若該板塊經程式端確認無 equipment 分類成員（Backlog 訊號不適用），此項改以「報告是否誠實標示不適用」為準，"
                     "不得因缺數據判 FAIL（詳見審查訊息中的具體要求）；3. 共識度與預期差 (Consensus Score) 的非共識標的分析。"
                     "滿足則回傳字串 PASS，否則回傳字串 FAIL。只允許 PASS 或 FAIL 兩種值。"
    )

    # GLM-5.2 實測曾回傳 "REJECTED" 等非枚舉字串（2026-07-04 切換 NIM 時發現）。
    # fail-closed 正規化：明確的通過同義詞 → PASS，其餘一律 FAIL。
    @field_validator("validation_status", mode="before")
    @classmethod
    def _normalize_status(cls, v):
        s = str(v).strip().upper()
        if s in ("PASS", "PASSED", "APPROVE", "APPROVED", "ACCEPT", "ACCEPTED", "OK"):
            return "PASS"
        return "FAIL"
    critic_feedback: str = Field(
        ..., 
        description="詳細的審查反饋意見。若 validation_status 為 FAIL，指出哪些超前定量數據或非共識分析缺失。"
    )

# ==================== LLM 三層備援鏈（NIM → DeepSeek 官方 → Claude CLI）====================
# Tier 1：NVIDIA NIM（OpenAI 相容端點，預設 z-ai/glm-5.2），key=NVIDIA_NIM_API_KEY。
# Tier 2：DeepSeek 官方（https://api.deepseek.com，預設 deepseek-v4-pro），key=DEEPSEEK_API_KEY。
# Tier 3：本機 Claude CLI（`claude -p`，訂閱授權）——僅本機可用；CI 環境備援鏈到 Tier 2 為止。
# 降級為 per-process 黏性：一旦降級，本次掃描剩餘呼叫直接使用降級後的層級，不再重撞上層。
# 誠實標示：LLM_PROVIDERS_USED 記錄實際用過的 provider/model，報告尾部逐一列出。

TIER_NIM = 0
TIER_DEEPSEEK = 1
TIER_CLAUDE_CLI = 2

_current_tier = None                 # None = 尚未降級；每次呼叫依環境變數解析起始層
LLM_PROVIDERS_USED: List[str] = []   # 實際使用過的 provider/model（有序去重）


def _reset_llm_failover_state():
    """測試/新流程用：重置黏性降級狀態與 provider 使用紀錄。"""
    global _current_tier
    _current_tier = None
    LLM_PROVIDERS_USED.clear()


def _tier_label(tier: int) -> str:
    """回傳該層級的 provider/model 誠實標示字串。"""
    if tier == TIER_NIM:
        return f"NVIDIA NIM/{os.environ.get('NIM_MODEL', 'z-ai/glm-5.2')}"
    if tier == TIER_DEEPSEEK:
        return f"DeepSeek 官方/{os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-pro')}"
    return "Claude CLI/本機訂閱（claude -p）"


def _record_provider_used(tier: int) -> None:
    label = _tier_label(tier)
    if label not in LLM_PROVIDERS_USED:
        LLM_PROVIDERS_USED.append(label)


def _resolve_start_tier() -> int:
    """依可用金鑰決定起始層（順序容錯）：缺 NIM 金鑰但有 DeepSeek 金鑰 → 直接從 Tier 2 起跳。"""
    if os.environ.get("NVIDIA_NIM_API_KEY"):
        return TIER_NIM
    if os.environ.get("DEEPSEEK_API_KEY"):
        print("[備援] 缺 NVIDIA_NIM_API_KEY，起始層直接使用 DeepSeek 官方（Tier 2）", flush=True)
        return TIER_DEEPSEEK
    # 兩把金鑰皆缺 → fail loud，不以假數據混淆（Claude CLI 僅作為執行中降級的最後手段，不作起始層）
    raise ValueError(
        "缺少必要的 NVIDIA_NIM_API_KEY 環境變數（亦無 DEEPSEEK_API_KEY 可作備援起始層）。"
        "請在專案設定或 GitHub Secrets 中配置它。"
    )


def _get_current_tier() -> int:
    return _current_tier if _current_tier is not None else _resolve_start_tier()


def _next_tier(tier: int):
    """回傳下一個可嘗試的層級；缺 DEEPSEEK_API_KEY 時跳過 Tier 2。無下一層 → None。"""
    candidate = tier + 1
    if candidate == TIER_DEEPSEEK and not os.environ.get("DEEPSEEK_API_KEY"):
        candidate = TIER_CLAUDE_CLI
    if candidate > TIER_CLAUDE_CLI:
        return None
    return candidate


class ClaudeCliLLM:
    """Tier 3：以本機 Claude CLI（訂閱授權，無需 ANTHROPIC_API_KEY）作為最後彙整手段。

    - 僅本機可用：找不到 claude CLI（如 CI 環境）時，建構即 raise 明確錯誤。
    - 結構化輸出：prompt 強制「只輸出符合 schema 的 JSON、無其他文字」，回傳後
      json.loads + Pydantic 驗證；解析失敗重試 1 次，仍失敗才 raise（fail loud，不捏造）。
    """

    def __init__(self, structured_model=None):
        self._cli_path = shutil.which("claude")
        if not self._cli_path:
            raise RuntimeError(
                "Tier 3（Claude CLI）不可用：找不到 claude CLI（shutil.which('claude') 為 None）。"
                "此層僅限本機訂閱環境；CI 環境備援鏈到 DeepSeek 官方（Tier 2）為止。"
            )
        self._structured_model = structured_model

    def _build_prompt(self, messages) -> str:
        parts = []
        for m in messages:
            content = getattr(m, "content", None)
            parts.append(str(content) if content is not None else str(m))
        prompt = "\n\n".join(parts)
        if self._structured_model is not None:
            schema = json.dumps(self._structured_model.model_json_schema(), ensure_ascii=False)
            prompt += (
                "\n\n【輸出格式強制要求】只輸出一個符合以下 JSON Schema 的 JSON 物件，"
                "不得輸出任何其他文字、說明、前後綴或 Markdown 圍欄：\n" + schema
            )
        return prompt

    def _run_cli(self, prompt: str) -> str:
        result = subprocess.run(
            [self._cli_path, "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI 執行失敗（exit={result.returncode}）：{(result.stderr or '').strip()[:500]}"
            )
        return (result.stdout or "").strip()

    @staticmethod
    def _extract_json(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"回應中找不到 JSON 物件：{text[:200]}")
        return text[start:end + 1]

    def invoke(self, messages):
        prompt = self._build_prompt(messages)
        if self._structured_model is None:
            return AIMessage(content=self._run_cli(prompt))
        last_err = None
        for _attempt in range(2):  # 解析失敗重試 1 次
            raw = self._run_cli(prompt)
            try:
                data = json.loads(self._extract_json(raw))
                return self._structured_model.model_validate(data)
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Claude CLI 結構化輸出解析在重試 1 次後仍失敗：{last_err}")


class DeepSeekStructuredLLM:
    """Tier 2 結構化輸出包裝。

    DeepSeek 官方 deepseek-v4-pro（thinking 模式）實測（2026-07-04）：
    - 預設 json_schema response_format → 400「This response_format type is unavailable now」
    - method="function_calling"（強制 tool_choice）→ 400「Thinking mode does not support this tool_choice」
    - method="json_mode" → 可用，但 DeepSeek 要求 prompt 內必須出現 json 字樣，
      故本包裝在訊息尾端追加「只輸出符合 schema 的 JSON」指令後再呼叫。
    """

    def __init__(self, llm, structured_model):
        self._structured = llm.with_structured_output(structured_model, method="json_mode")
        schema = json.dumps(structured_model.model_json_schema(), ensure_ascii=False)
        self._format_msg = HumanMessage(content=(
            "【輸出格式強制要求】只輸出一個符合以下 JSON Schema 的 json 物件，"
            "不得輸出任何其他文字、說明或 Markdown 圍欄：\n" + schema
        ))

    def invoke(self, messages):
        return self._structured.invoke(list(messages) + [self._format_msg])


def get_llm_model(structured_model=None, tier=None):
    """依當前（或指定）備援層級建立 LLM。缺對應金鑰/CLI 時 fail loud，不以假數據混淆。"""
    if tier is None:
        tier = _get_current_tier()

    if tier == TIER_NIM:
        api_key = os.environ.get("NVIDIA_NIM_API_KEY")
        if not api_key:
            raise ValueError("缺少必要的 NVIDIA_NIM_API_KEY 環境變數。請在專案設定或 GitHub Secrets 中配置它。")
        llm = ChatOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key,
            model=os.environ.get("NIM_MODEL", "z-ai/glm-5.2"),
            temperature=0,
        )
    elif tier == TIER_DEEPSEEK:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("缺少 DEEPSEEK_API_KEY 環境變數，Tier 2（DeepSeek 官方）不可用。")
        llm = ChatOpenAI(
            base_url="https://api.deepseek.com",
            api_key=api_key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            temperature=0,
        )
        if structured_model:
            return DeepSeekStructuredLLM(llm, structured_model)
        return llm
    elif tier == TIER_CLAUDE_CLI:
        return ClaudeCliLLM(structured_model)
    else:
        raise ValueError(f"未知的 LLM 備援層級：{tier}")

    if structured_model:
        return llm.with_structured_output(structured_model)
    return llm


def _invoke_with_retry(llm, messages, retries: int = 3, backoff: float = 2.0, structured_model=None):
    """呼叫 LLM，含三層備援降級。fail loud，不捏造假數據。

    - 429（限流）：同層最多重試 2 輪、各等 180 秒，仍 429 → 降到下一層重建 LLM（含 structured schema）再試。
    - 非 429 暫時性錯誤：同層最多 retries 次指數退避，耗盡後同樣降級。
    - 降級為 per-process 黏性（_current_tier）：本次掃描剩餘呼叫直接用降級後的層級，不再重撞上層。
    - 全部層級耗盡 → raise；降級至 Tier 3 但本機無 claude CLI（如 CI）→ 同樣 raise 明確錯誤。
    """
    global _current_tier
    RATE_LIMIT_INTERVAL = 180
    RATE_LIMIT_MAX_ROUNDS = 2

    tier = _get_current_tier()
    last_err = None
    while True:
        rate_limit_rounds = 0
        attempt = 0
        while attempt < retries:
            try:
                result = llm.invoke(messages)
                _record_provider_used(tier)
                return result
            except Exception as e:
                last_err = e
                if "429" in str(e):
                    if rate_limit_rounds < RATE_LIMIT_MAX_ROUNDS:
                        rate_limit_rounds += 1
                        print(
                            f"[限流 429] {_tier_label(tier)}：{RATE_LIMIT_INTERVAL} 秒後同層重試"
                            f"（第 {rate_limit_rounds}/{RATE_LIMIT_MAX_ROUNDS} 輪）", flush=True)
                        time.sleep(RATE_LIMIT_INTERVAL)
                        continue
                    break  # 同層 429 重試耗盡 → 降級
                attempt += 1
                if attempt < retries:
                    time.sleep(backoff * (2 ** attempt))

        next_tier = _next_tier(tier)
        if next_tier is None:
            raise RuntimeError(f"LLM 三層備援全部耗盡，最後錯誤：{last_err}")
        print(
            f"[備援降級] {_tier_label(tier)} 失敗（{str(last_err)[:200]}）"
            f"→ 降級至 {_tier_label(next_tier)}（本次掃描剩餘呼叫黏性沿用）", flush=True)
        tier = next_tier
        _current_tier = tier                                # 黏性降級
        llm = get_llm_model(structured_model, tier=tier)    # 含 structured schema 重建

# 板塊世代規格先驗檔路徑（見 data/priors/sector_specs.json）
_SECTOR_SPECS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "priors", "sector_specs.json")

def load_sector_spec(sector: str) -> Dict[str, Any]:
    """
    查表取得板塊的世代規格（current/next/future generation）與敘事提示句。
    查無該板塊 → 世代欄位一律回傳 "N/A"，並標記 sector_spec_missing=True，
    表示此板塊尚未登記世代規格，禁止套用 GPU 世代敘事、禁止編造世代名。
    """
    specs: Dict[str, Any] = {}
    try:
        import json
        with open(_SECTOR_SPECS_PATH, "r", encoding="utf-8") as f:
            specs = json.load(f)
    except (FileNotFoundError, ValueError):
        specs = {}

    spec = specs.get(sector)
    if spec:
        gens = (
            spec.get("current_generation", "N/A"),
            spec.get("next_generation", "N/A"),
            spec.get("future_generation", "N/A"),
        )
        # 無世代框架板塊（如低軌衛星/邊緣 AI）：specs 有登記但世代欄位全為 N/A
        # → 沿用「禁止套用/編造世代敘事」的防線（sector_spec_missing=True），
        #   但 narrative_hint 照常帶入，讓報告有正確的板塊敘事錨點。
        no_generation_framework = all(g == "N/A" for g in gens)
        return {
            "current_generation": gens[0],
            "next_generation": gens[1],
            "future_generation": gens[2],
            "narrative_hint": spec.get("narrative_hint", ""),
            "sector_spec_missing": no_generation_framework,
        }

    return {
        "current_generation": "N/A",
        "next_generation": "N/A",
        "future_generation": "N/A",
        "narrative_hint": "",
        "sector_spec_missing": True,
    }

# 初始化監控器
monitor = MarketInformationMonitor()

# ==================== Agent 節點 (Nodes) 實作 ====================

def supply_chain_expert_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    供應鏈洗牌專家節點：
    - 推演 18-24 個月能見度窗口下，物理規格變更對現有供應商的正面與反面影響。
    - 特別辨識哪些廠商雖然在當前代大賺，但已面臨下世代被替代、價值歸零的風險。
    """
    current_gen = state.get("current_generation", "N/A")
    next_gen = state.get("next_generation", "N/A")
    future_gen = state.get("future_generation", "N/A")
    sector = state.get("target_sector")
    spec_missing = state.get("sector_spec_missing", False)
    narrative_hint = state.get("narrative_hint", "")

    # 呼叫數據監控引擎，支援 point-in-time 歷史回測截斷
    as_of_date = state.get("as_of_date")
    raw_schedule = monitor.get_supply_chain_schedule(
        current_gen, next_gen,
        as_of_date=as_of_date if as_of_date else None,
        sector=sector,
        future_gen=state.get("future_generation", "Feynman_Next"),
    )

    membership_warning = (
        f"\n\n【板塊名單來源警語】{MEMBERSHIP_FALLBACK_NOTE}"
        if raw_schedule.get("membership_source") == MEMBERSHIP_SOURCE_FALLBACK else ""
    )

    if spec_missing:
        generation_framing = (
            f"【重要】本板塊（{sector}）尚未登記世代規格，data/priors/sector_specs.json 查無對應項目。"
            f"世代欄位一律為 N/A。禁止套用 GPU 世代（如 Vera_Rubin/Feynman）敘事框架，"
            f"禁止自行編造世代名稱或架構代號。請改以該板塊實際的技術迭代脈絡進行洗牌分析。"
        )
    else:
        hint_line = f"\n板塊敘事框架：{narrative_hint}" if narrative_hint else ""
        generation_framing = (
            f"請針對當前世代 {current_gen}、下一代 {next_gen}，"
            f"特別是超前 18-24 個月的下下一代架構 {future_gen} 的物理變革進行洗牌分析。{hint_line}"
        )

    prompt = (
        f"你是一個資深半導體與科技硬體供應鏈專家。\n"
        f"{generation_framing}\n"
        f"實體監控數據如下：\n{raw_schedule}\n\n"
        f"你的分析必須專注於：\n"
        f"1. **Content Value (CV) 的正反面演進**：哪些廠商在新架構下價值暴漲？哪些廠商在下下一代"
        f"{'（因本板塊無世代規格，此問題不適用，請略過世代替代風險分析，改以一般競爭替代風險描述）' if spec_missing else f' {future_gen}'}"
        f"因為技術被整合或替代而面臨 CV 暴跌/歸零風險？\n"
        f"2. **Design Win 與試產放量時程**：指出設備端放量比元件端領先的關鍵時間點。"
        f"{membership_warning}"
    )

    if state.get("critic_feedback"):
        prompt += f"\n\n[注意] 前一輪 Critic 提出的修正意見為：{state['critic_feedback']}。請針對此建議修正分析。"

    llm = get_llm_model()
    response = _invoke_with_retry(llm, [
        SystemMessage(content="你是一個資深科技產業分析師，精通半導體價值量 (Content Value) 洗牌與超前世代替代風險評估。"),
        HumanMessage(content=prompt)
    ])
    analysis_text = response.content

    return {
        "supply_chain_analysis": {
            "summary": analysis_text,
            "raw_data": raw_schedule
        }
    }

def pricing_revenue_expert_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    價格與營收專家節點：
    - 解析高頻報價趨勢。
    - **核心優化**：解讀上游設備 Backlog 訂單 (Equipment Backlog)，該指標領分成品營收 6 個月，藉此捕捉股價起漲的先行信號。
    """
    sector = state["target_sector"]
    as_of_date = state.get("as_of_date")
    company_ids, membership_source = monitor.resolve_sector_members(sector, as_of_date if as_of_date else None)

    # 呼叫數據監控引擎，支援 point-in-time 歷史回測截斷
    pricing_data = monitor.get_high_frequency_pricing(sector, as_of_date=as_of_date if as_of_date else None)
    revenue_data = monitor.simulate_revenue_inflection(
        company_ids,
        as_of_date=as_of_date if as_of_date else None,
        sector=sector,
    )

    membership_warning = (
        f"\n\n【板塊名單來源警語】{MEMBERSHIP_FALLBACK_NOTE}"
        if membership_source == MEMBERSHIP_SOURCE_FALLBACK else ""
    )

    # 板塊是否有 equipment 分類成員，由程式（market_monitor）判定後的事實，
    # 不交由 LLM 自行判斷/猜測。任一標的的 current_backlog_yoy_pct 為 None
    # 即代表本板塊無 equipment 成員，Backlog 板塊層訊號不適用。
    backlog_applicable = any(
        data.get("current_backlog_yoy_pct") is not None for data in revenue_data.values()
    )
    backlog_instruction = (
        f"2. **設備訂單 (Backlog) 的領先性**：設備 Backlog YoY 是否已率先爆發 (大於 50%)，即使此時下游成品營收依然在谷底？\n"
        if backlog_applicable else
        f"2. **本板塊無 equipment 分類成員，Backlog 訊號不適用**：`current_backlog_yoy_pct` 為 None，"
        f"禁止以 0.0 或任何自行估算的數字充數，請在分析中明示『本板塊無 equipment 分類成員，Backlog 訊號不適用』，"
        f"並改以其他既有量化訊號（真實營收 YoY、Consensus Score）作為領先性討論依據。\n"
    )
    backlog_honesty_rule = (
        f"- `current_backlog_yoy_pct` / `backlog_yoy_curve_3m` 是「{BACKLOG_SIGNAL_NOTE}」，"
        f"呈現時必須註明『板塊層代理訊號，非公司別訂單資料』，不得寫成該公司自己的訂單數據。"
        if backlog_applicable else
        f"- 本板塊 `current_backlog_yoy_pct` 為 None（`backlog_not_applicable_note` 已標明原因）："
        f"禁止以 0.0 或任何編造數字呈現 Backlog 板塊層訊號，一律明示『本板塊無 equipment 分類成員，Backlog 訊號不適用』。"
    )

    prompt = (
        f"你是一個量化金融與產業營收分析專家。\n"
        f"請針對高頻報價走勢與各供應鏈廠商的成品營收 YoY、設備 Backlog 訂單 YoY 數據進行定量解析。\n"
        f"高頻價格數據：\n{pricing_data}\n"
        f"營收與設備 Backlog 數據（包含來自台灣證券交易所開放 API 的真實營收）：\n{revenue_data}\n\n"
        f"你的分析必須專注於：\n"
        f"1. **優先呈現真實數據**：如果數據中包含真實的公開月度營收（即 `has_real_data` 為 True 的標的），請在分析中優先指出該公司最新的實際營收金額（單位：億元）、實際 YoY 成長率，並基於這些真實基期對未來的營收與訂單拐點進行合理推演，而非僅依賴模擬數據。\n"
        f"{backlog_instruction}"
        f"3. **尋找黃金潛伏標的**：只有 `is_golden_accumulation_target` 欄位為 True 的公司，才可以稱為『非共識黃金潛伏標的』；其餘一律稱為『觀察名單（未過共識門檻）』，不得混用兩者的措辭。\n\n"
        f"【誠實化強制規則，違反視為分析不合格】：\n"
        f"- `projected_peak_yoy_pct` 與 `future_3m_yoy` 欄位是「{REVENUE_PROJECTION_NOTE}」，"
        f"你只能稱其為『機械外推情境』，嚴禁描述為『預測』『基本面預測』『模型預測』或任何暗示其為研究判斷結果的詞語。\n"
        f"- `consensus_score` 為粗粒度分數（{CONSENSUS_GRANULARITY_NOTE}），"
        f"呈現時一律標註『共識度 XX（粗粒度，±8 分為雜訊）』，不得暗示個位以下精度。\n"
        f"{backlog_honesty_rule}"
        f"{membership_warning}"
    )

    if state.get("critic_feedback"):
        prompt += f"\n\n[注意] 前一輪 Critic 提出的修正意見為：{state['critic_feedback']}。請針對此建議修正分析。"

    llm = get_llm_model()
    response = _invoke_with_retry(llm, [
        SystemMessage(content="你精通量化分析、設備訂單 (Backlog) 領先週期判斷與營收 YoY 拐點定量估算。"),
        HumanMessage(content=prompt)
    ])
    analysis_text = response.content

    return {
        "pricing_revenue_analysis": {
            "summary": analysis_text,
            "raw_pricing": pricing_data,
            "raw_revenue": revenue_data
        }
    }

def _pick_cv_extremes(raw_revenue: Dict[str, Any]) -> "tuple[str, str]":
    """
    從實際成員資料中，動態選出 CV（內容價值/成長）增幅最大與最小的代表股，
    取代寫死的個股名稱。以 `real_yoy_pct`（真實 YoY，優先）或 `last_month_yoy`
    （機械外推 YoY，次選）作為 CV 增幅代理指標。無資料時回傳空字串，呼叫端不得舉例。
    """
    scored = []
    for cid, data in (raw_revenue or {}).items():
        yoy = data.get("real_yoy_pct")
        if yoy is None:
            yoy = data.get("last_month_yoy")
        if yoy is None:
            continue
        name = data.get("name", cid)
        scored.append((yoy, name))

    if not scored:
        return "", ""

    scored.sort(key=lambda x: x[0])
    lowest_name = scored[0][1]
    highest_name = scored[-1][1]
    return highest_name, lowest_name

def media_story_expert_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    新聞與情緒預判專家節點：
    - **核心優化**：解析「共識度 (Consensus Score)」，排除市場已經大幅反映的 Consensus 標的。
    - 專注於「低共識 + 高預期差」的標的，規劃超前於媒體報導的潛伏佈局操作。
    """
    raw_revenue = state.get("pricing_revenue_analysis", {}).get("raw_revenue", {})
    highest_cv_name, lowest_cv_name = _pick_cv_extremes(raw_revenue)
    narrative_hint = state.get("narrative_hint", "")

    consensus_example = (
        f"（如 CV 增幅最大代表股 {highest_cv_name}）" if highest_cv_name else "（本次無足夠資料舉例，不得自行編造標的名稱）"
    )
    non_consensus_example = (
        f"（如 CV 增幅最小代表股 {lowest_cv_name}）" if lowest_cv_name else "（本次無足夠資料舉例，不得自行編造標的名稱）"
    )
    storytelling_hint = narrative_hint if narrative_hint else "板塊潛在受益敘事（依實際供應鏈分析結論歸納，不得套用其他板塊敘事）"

    prompt = (
        f"你是一個行為金融學與財經媒體炒作週期專家。\n"
        f"請分析供應鏈與營收/設備指標的結論，並結合各廠商的『共識度得分 (Consensus Score)』進行預期差過濾。\n\n"
        f"請規劃操作策略：\n"
        f"1. **排除 Consensus 標的**：對於媒體已經寫爆、市場高度共識 (Consensus > 80) 的股票"
        f"{consensus_example}，提出『已充分反映』與『下世代替代風險』的警告。\n"
        f"2. **規劃非共識 (Non-Consensus) 潛伏期**：針對低共識度 (Consensus < 60) 且設備訂單先行暴增的標的"
        f"{non_consensus_example}，模擬未來 2-3 個月新聞會如何包裝（從『無人關注的冷門設備』到『{storytelling_hint}』的 Storytelling 傳導），並制定精確的潛伏與退場時間表。\n\n"
        f"【誠實化強制規則，違反視為分析不合格】：\n"
        f"- 只有前一節分析中明確標記 `is_golden_accumulation_target` 為 True 的公司，才可稱為『非共識黃金潛伏標的』；"
        f"其餘一律稱為『觀察名單（未過共識門檻）』，即使共識度數字看起來偏低也不可越級標記為黃金標的。\n"
        f"- Consensus Score 是{CONSENSUS_GRANULARITY_NOTE}，呈現時不得暗示個位以下精度，並附註粗粒度警語。\n"
        f"- 舉例個股時只能使用上方提供的代表股名稱或前一節分析結論中出現的實際公司名稱，禁止自行編造或沿用其他板塊的個股名稱。"
    )

    if state.get("critic_feedback"):
        prompt += f"\n\n[注意] 前一輪 Critic 提出的修正意見為：{state['critic_feedback']}。請針對此建議修正分析。"

    context = (
        f"供應鏈洗牌結論：\n{state['supply_chain_analysis']['summary']}\n\n"
        f"價格與營收結論：\n{state['pricing_revenue_analysis']['summary']}"
    )
    llm = get_llm_model()
    response = _invoke_with_retry(llm, [
        SystemMessage(content="你擅長預判財經新聞 Storytelling 的集體發酵點，並利用共識度過濾『股價已反映』標的。"),
        HumanMessage(content=f"{context}\n\n{prompt}")
    ])
    analysis_text = response.content

    return {
        "media_story_anticipation": {
            "summary": analysis_text
        }
    }

def report_writer_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    報告撰寫節點：整合專家成果，撰寫繁體中文學術級 18-24 個月超前能見度可行性評估報告。
    """
    future_gen = state.get("future_generation", "N/A")
    spec_missing = state.get("sector_spec_missing", False)

    if spec_missing:
        generation_line = f"產品世代演進：本板塊尚未登記世代規格（N/A），不適用 GPU 世代替代框架，請改以該板塊實際技術迭代脈絡描述。\n"
        section_one_title = "  一、 技術物理限制與超前 18-24 個月洗牌框架（本板塊無世代規格，禁止套用 GPU 世代敘事或編造世代名）\n"
    else:
        generation_line = f"產品世代演進：{state['current_generation']} --> {state['next_generation']} --> {future_gen} (超前 18-24 個月)\n"
        section_one_title = f"  一、 技術物理限制與超前 18-24 個月 ({future_gen}) 洗牌框架\n"

    # 板塊是否有 equipment 分類成員，由程式（market_monitor）判定後的事實注入 prompt，
    # 不交由 LLM 自行猜測。任一標的的 current_backlog_yoy_pct 為 None 即代表不適用。
    raw_revenue = state.get("pricing_revenue_analysis", {}).get("raw_revenue", {})
    backlog_applicable = any(
        data.get("current_backlog_yoy_pct") is not None for data in raw_revenue.values()
    )
    section_three_title = (
        f"  三、 領先 6-9 個月之設備 Backlog 訂單與營收基期定量預測\n"
        if backlog_applicable else
        f"  三、 設備 Backlog 訊號不適用說明（本板塊無 equipment 分類成員）與營收基期定量預測\n"
    )
    backlog_honesty_rule = (
        f"4. 設備 Backlog YoY 數據，一律標示為『板塊層代理訊號（equipment 分類公司月營收 YoY 中位數），非公司別訂單資料』，"
        f"不得寫成該公司自身的訂單或拉貨數字。\n"
        if backlog_applicable else
        f"4. 本板塊無 equipment 分類成員，`current_backlog_yoy_pct` 為 None：全篇禁止以 0.0 或任何編造數字呈現"
        f"設備 Backlog 板塊層訊號，第三部分必須明示『本板塊無 equipment 分類成員，Backlog 訊號不適用』，"
        f"改以真實營收 YoY 與 Consensus Score 作為該部分的定量依據。\n"
    )

    prompt = (
        f"請將以下三位專家的研判結果整合，撰寫一份架構極其嚴謹、具備學術研究報告深度的傳統中文（繁體中文）可行性評估報告。\n"
        f"目標技術板塊：{state['target_sector']}\n"
        f"{generation_line}\n"
        f"【供應鏈專家洗牌分析】：\n{state['supply_chain_analysis']['summary']}\n\n"
        f"【價格與設備訂單分析】：\n{state['pricing_revenue_analysis']['summary']}\n\n"
        f"【共識過濾與新聞情緒分析】：\n{state['media_story_anticipation']['summary']}\n\n"
        f"報告撰寫格式要求：\n"
        f"- 必須明確分為以下五大部分：\n"
        f"{section_one_title}"
        f"  二、 供應鏈內容價值 (Content Value) 正反面推演與下世代替代風險警告\n"
        f"{section_three_title}"
        f"  四... 預期差與共識度 (Consensus Score) 過濾操作策略\n"
        f"  五、 結論與非共識 (Non-Consensus) 投資建議\n"
        f"- **定量指標比率不可低於 40%**。必須包含：各代 Content Value 變動比率、Consensus Score、預估 YoY 峰值"
        f"{'、設備 Backlog 增幅' if backlog_applicable else '（本板塊 Backlog 不適用，此欄以真實營收 YoY 幅度替代）'}。\n"
        f"- 採用嚴謹、具備學術感且流暢的繁體中文撰寫。\n\n"
        f"【誠實化強制規則，全篇適用，違反視為報告不合格】：\n"
        f"1. 任何『預估 YoY 峰值』『未來 3 個月 YoY』數字，一律標示為『機械外推情境（末值 × 固定加速係數），非模型預測』，"
        f"禁止使用『預測』『展望』等暗示基本面研判的詞語描述該數字。\n"
        f"2. Consensus Score 呈現時須註明『共識度 XX（粗粒度：12 檔樣本，±8 分為雜訊）』，不得暗示個位以下精度。\n"
        f"3. 只有前段分析中明確標記 `is_golden_accumulation_target` 為 True 的公司，才可在結論中稱為『非共識黃金潛伏標的』；"
        f"其餘一律稱為『觀察名單（未過共識門檻）』。\n"
        f"{backlog_honesty_rule}"
        f"5. 若本次無任何公司通過黃金潛伏門檻，誠實陳述『無標的通過』即止；"
        f"嚴禁虛構『假設性標的』『模擬情境』或以任何不符合條件的公司示範進場策略——寧可報告短，不可捏造情境。"
        + ("\n6. 本板塊無世代規格登記，全篇禁止出現 Vera_Rubin/Feynman/Feynman_Next 等 GPU 世代名稱或任何自行編造的世代代號。" if spec_missing else "")
    )
    
    llm = get_llm_model()
    response = _invoke_with_retry(llm, [
        SystemMessage(content="你是頂尖的量化投資機構首席分析師，撰寫風格嚴謹，精通第二層思考與非共識正確分析，使用繁體中文。"),
        HumanMessage(content=prompt)
    ])
    report_text = response.content
    if isinstance(report_text, list):
        report_text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in report_text
        )

    return {"feasibility_report_draft": report_text}

def quality_critic_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    評審節點：檢查報告是否明確包含：下下一代替代風險、設備拉貨領先度 (Backlog)、共識度/預期差得分。
    """
    report = state.get("feasibility_report_draft", "")
    iteration = state.get("iteration_count", 0) + 1
    future_gen = state.get("future_generation", "N/A")
    spec_missing = state.get("sector_spec_missing", False)

    generation_requirement = (
        "1. 18-24個月下下世代洗牌與替代風險警告（本板塊無世代規格，不得要求報告出現 Feynman_Next 等其他板塊的世代名稱）；\n"
        if spec_missing else
        f"1. 18-24個月下下世代 ({future_gen}) 洗牌與替代風險警告；\n"
    )

    # 板塊是否有 equipment 分類成員，由程式（market_monitor）判定後的事實注入 critic prompt，
    # 不交由 LLM 自行猜測。任一標的的 current_backlog_yoy_pct 為 None 即代表不適用。
    raw_revenue = state.get("pricing_revenue_analysis", {}).get("raw_revenue", {})
    backlog_applicable = any(
        data.get("current_backlog_yoy_pct") is not None for data in raw_revenue.values()
    )
    backlog_requirement = (
        "2. 至少一家設備商的拉貨領先度 (Backlog YoY) 定量數據；\n"
        if backlog_applicable else
        "2.【本板塊無 equipment 分類成員，Backlog 板塊層訊號不適用（程式端已確認）】"
        "此項審查標準改為：報告是否誠實標示『本板塊無 equipment 分類成員，Backlog 訊號不適用』。"
        "只要報告有做到這一點即視為滿足本項，不得因報告缺少設備商 Backlog YoY 定量數據而判 FAIL；"
        "若報告反而捏造 0.0 或任何數字冒充 Backlog 定量數據，則仍應判 FAIL。\n"
    )

    prompt = (
        f"請審查以下可行性研究報告是否滿足超前指標完整性。\n"
        f"要求報告中必須清晰包含：\n"
        f"{generation_requirement}"
        f"{backlog_requirement}"
        f"3. 供應鏈公司的共識度得分 (Consensus Score) 與預期差非共識判定。\n\n"
        f"另須檢查【捏造禁令】：若報告在「無標的通過黃金潛伏門檻」的情況下，"
        f"出現『假設性標的』『模擬情境』或以不符合條件的公司示範進場/退場策略，一律判 FAIL 並要求刪除該段。\n\n"
        f"【報告內容】：\n{report}\n"
    )

    critic_system_message = (
        "你是投審會主席，嚴格執行第二層思考審查，絕不接受缺少下下世代替代風險或共識度過濾分析的報告。"
        + ("缺少設備 Backlog 定量數據的報告同樣不可接受。"
           if backlog_applicable else
           "本板塊無 equipment 分類成員，Backlog 板塊層訊號不適用——審查 Backlog 項目時，"
           "只要報告誠實標示『不適用』即算通過，不得因缺乏設備商 Backlog 數據而判 FAIL。")
    )

    critic_llm = get_llm_model(CriticDecision)
    decision = _invoke_with_retry(critic_llm, [
        SystemMessage(content=critic_system_message),
        HumanMessage(content=prompt)
    ], structured_model=CriticDecision)
    status = decision.validation_status
    feedback = decision.critic_feedback

    print(f"[Critic 評審] 迭代次數: {iteration} | 狀態: {status} | 反饋: {feedback}")
    
    return {
        "validation_status": status,
        "critic_feedback": feedback if status == "FAIL" else "",
        "iteration_count": iteration
    }

# ==================== 路由控制與編譯 ====================

def route_based_on_critic(state: MarketHotspotState) -> str:
    """
    決定下一步路徑。如果品質不合格且迭代次數 < 3，退回專家重新優化；否則結束。
    """
    # fail-closed：只有明確 PASS 才放行；任何非 PASS 值（含模型回傳的非枚舉字串）都觸發重修
    if state["validation_status"] != "PASS" and state["iteration_count"] < 3:
        print("--> 審查未通過，觸發自我修正 (Self-Correction) 機制，回溯至專家節點...")
        return "supply_chain_expert"
    print("--> 審查通過或達迭代上限，導向結束節點。")
    return END

# 建立並編譯狀態機圖
workflow = StateGraph(MarketHotspotState)

# 註冊節點
workflow.add_node("supply_chain_expert", supply_chain_expert_node)
workflow.add_node("pricing_revenue_expert", pricing_revenue_expert_node)
workflow.add_node("media_story_expert", media_story_expert_node)
workflow.add_node("report_writer", report_writer_node)
workflow.add_node("quality_critic", quality_critic_node)

# 設定邊
workflow.add_edge(START, "supply_chain_expert")
workflow.add_edge("supply_chain_expert", "pricing_revenue_expert")
workflow.add_edge("pricing_revenue_expert", "media_story_expert")
workflow.add_edge("media_story_expert", "report_writer")
workflow.add_edge("report_writer", "quality_critic")

# 條件邊
workflow.add_conditional_edges(
    "quality_critic",
    route_based_on_critic,
    {
        "supply_chain_expert": "supply_chain_expert",
        END: END
    }
)

# 編譯 App
app = workflow.compile()

# ==================== 命令列進入點 ====================

def run_daily_price_update():
    """
    僅執行每日股價追蹤與觀察名單更新，不調用 LLM，節省 Tokens。
    """
    print(f"==================================================")
    print(f"[*] 啟動每日觀察名單股價追蹤與績效報告更新")
    print(f"當前時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"==================================================")
    try:
        import performance_tracker
        performance_tracker.update_watchlist_daily_prices()
        performance_tracker.generate_performance_report()
        print(f"[OK] 每日股價追蹤與績效報告更新完成！")
    except Exception as e:
        print(f"[❌ 錯誤] 執行每日股價追蹤出錯: {e}")
        sys.exit(1)

def run_hotspot_scan(sector: str, as_of_date: str = ""):
    print(f"==================================================")
    print(f"[*] 啟動 12-18 個月市場熱點預見多 Agent 系統")
    print(f"目標板塊: {sector}")
    if as_of_date:
        print(f"模擬歷史時間點: {as_of_date}")
    print(f"當前時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"==================================================")
    
    sector_spec = load_sector_spec(sector)
    if sector_spec["sector_spec_missing"]:
        print(f"[WARN] 板塊 {sector} 未登記世代規格（data/priors/sector_specs.json 查無此項目），世代欄位一律為 N/A。")

    # 每次掃描重置 provider 使用紀錄（黏性降級層級保留：同 process 連掃多板塊時不重撞已失敗的上層）
    LLM_PROVIDERS_USED.clear()

    initial_state: MarketHotspotState = {
        "target_sector": sector,
        "current_generation": sector_spec["current_generation"],
        "next_generation": sector_spec["next_generation"],
        "future_generation": sector_spec["future_generation"],
        "narrative_hint": sector_spec["narrative_hint"],
        "sector_spec_missing": sector_spec["sector_spec_missing"],
        "supply_chain_analysis": {},
        "pricing_revenue_analysis": {},
        "media_story_anticipation": {},
        "feasibility_report_draft": "",
        "critic_feedback": "",
        "iteration_count": 0,
        "validation_status": "",
        "as_of_date": as_of_date
    }
    
    # 執行狀態機
    final_output = app.invoke(initial_state)
    
    # 僅在審查通過 (PASS) 時發布報告，依 ADR 0005 不捏造、不發布未通過的報告
    if final_output["validation_status"] == "PASS":
        os.makedirs("reports", exist_ok=True)
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        report_filename = f"reports/{today_str}-{sector}-feasibility-report.md"

        # 誠實標示：報告尾部逐一列出本次實際使用的 provider/model（降級混用多家時全部列出）
        providers_line = "、".join(LLM_PROVIDERS_USED) if LLM_PROVIDERS_USED else "（未記錄到任何 LLM 供應商）"
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(final_output["feasibility_report_draft"])
            f.write(f"\n\n---\n本報告由 {providers_line} 生成\n")

        print(f"[LLM 供應商] 本次掃描實際使用：{providers_line}")
        print(f"\n[OK] 任務成功完成！報告已儲存至: {report_filename}")
        print(f"最終狀態: {final_output['validation_status']} | 迭代次數: {final_output['iteration_count']}")
    else:
        print(f"\n[FAIL] 報告未通過品質審查（validation_status={final_output['validation_status']}），依 ADR 0005 不發布。")
        sys.exit(1)

    # 當審查通過時，將新出現之「非共識黃金建倉標的」加入 watchlist 並更新價格與勝率
    if final_output["validation_status"] == "PASS":
        try:
            import performance_tracker
            import yfinance as yf
            
            pricing_rev_analysis = final_output.get("pricing_revenue_analysis", {})
            raw_rev = pricing_rev_analysis.get("raw_revenue", {})
            
            for cid, data in raw_rev.items():
                # 黃金建倉條件：與 market_monitor.is_golden_accumulation_target 同一判定，
                # 禁止在此另立門檻（見 CONTEXT.md / ADR 0003：pre-registered 門檻不可回測 tune）。
                is_golden = data.get("is_golden_accumulation_target", False)
                if not is_golden:
                    continue

                entry_price = None

                # 以 yfinance 拉取今天最新真實收盤價
                try:
                    ticker = yf.Ticker(cid)
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        entry_price = float(hist["Close"].iloc[-1])
                except Exception:
                    pass

                # fallback：讀最新 PIT 股價快照
                if entry_price is None:
                    try:
                        import pit_store, datetime as _dt
                        snap = pit_store.read_snapshot("prices", _dt.date.today().strftime("%Y-%m-%d"))
                        pure_cid = cid.split(".")[0]
                        if snap and pure_cid in snap:
                            entry_price = float(snap[pure_cid]["close"])
                    except Exception:
                        pass

                if entry_price is None:
                    print(f"[WARN] 無法取得 {cid} 進場價，跳過加入 watchlist")
                    continue

                performance_tracker.add_to_watchlist(
                    company_id=cid,
                    name=data.get("name", cid),
                    entry_price=entry_price,
                    sector=sector,
                    entry_date=as_of_date
                )
            
            # 更新名單中所有標的的 K 線與回報率，並生成統計報告
            performance_tracker.update_watchlist_daily_prices(as_of_date=as_of_date)
            performance_tracker.generate_performance_report()
            
        except Exception as e:
            print(f"[⚠️ 警告] 自動更新績效追蹤名單出錯: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="市場熱點預見與多 Agent 系統")
    parser.add_argument("--sector", type=str, default="CPO_Optical_Transceiver", help="目標板塊名稱")
    parser.add_argument("--as-of-date", type=str, default="", help="歷史模擬時間點 (YYYY-MM-DD)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--daily-update", action="store_true", help="僅執行每日股價追蹤與觀察名單更新")
    group.add_argument("--weekly-report", action="store_true", help="執行完整每週多 Agent 報告研判與生成")
    args = parser.parse_args()
    
    if args.daily_update:
        run_daily_price_update()
    else:
        # 預設或指定 --weekly-report 時，進行完整掃描研判
        run_hotspot_scan(args.sector, as_of_date=args.as_of_date)
