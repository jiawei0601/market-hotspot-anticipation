import inspect
import os
import unittest
from unittest.mock import patch, MagicMock
import main_agent
from main_agent import app, route_based_on_critic, load_sector_spec, _pick_cv_extremes, get_llm_model

class TestAgentWorkflow(unittest.TestCase):
    def test_graph_structure(self):
        """驗證 LangGraph 狀態機結構與節點是否註冊成功"""
        # 獲取圖中所有註冊的節點名稱
        nodes = app.nodes.keys()
        self.assertIn("supply_chain_expert", nodes)
        self.assertIn("pricing_revenue_expert", nodes)
        self.assertIn("media_story_expert", nodes)
        self.assertIn("report_writer", nodes)
        self.assertIn("quality_critic", nodes)

    def test_route_based_on_critic_fail(self):
        """驗證當 Critic 判定為 FAIL 且迭代次數 < 3 時，路由正確返回 supply_chain_expert 節點"""
        fail_state = {
            "validation_status": "FAIL",
            "iteration_count": 1
        }
        next_step = route_based_on_critic(fail_state)
        self.assertEqual(next_step, "supply_chain_expert")

    def test_route_based_on_critic_pass(self):
        """驗證當 Critic 判定為 PASS 時，路由導向 END 結束狀態"""
        pass_state = {
            "validation_status": "PASS",
            "iteration_count": 1
        }
        next_step = route_based_on_critic(pass_state)
        # 由於 langgraph.graph 中的 END 是一個特殊的常數字串，此處直接與字串做比對
        self.assertEqual(next_step, "__end__")

    def test_route_based_on_critic_max_iterations(self):
        """驗證即使判定為 FAIL，若迭代次數達到上限 3 次，路由依然導向 END 結束狀態"""
        max_state = {
            "validation_status": "FAIL",
            "iteration_count": 3
        }
        next_step = route_based_on_critic(max_state)
        self.assertEqual(next_step, "__end__")

    def test_watchlist_golden_selection_uses_single_source_of_truth(self):
        """run_hotspot_scan 的 watchlist 篩選必須直接讀取
        market_monitor.is_golden_accumulation_target 的判定結果，
        不得在 main_agent.py 內另立獨立的共識度/YoY 門檻（見 CONTEXT.md 誠實化修正第 3 點：
        鈦昇共識度 64.6 > CONSENSUS_MAX=60 卻曾被誤標為黃金標的的根因）。"""
        source = inspect.getsource(main_agent.run_hotspot_scan)
        self.assertIn('data.get("is_golden_accumulation_target"', source)
        # 禁止再出現另立的寬鬆門檻（例如舊版 consensus < 70.0）
        self.assertNotIn("70.0", source)
        self.assertNotIn("_compute_consensus", source)

    def test_run_hotspot_scan_no_longer_hardcodes_generations(self):
        """LLM 研判層板塊參數化：run_hotspot_scan 的 initial_state 世代欄位必須來自
        load_sector_spec() 查表結果，不得再寫死 Vera_Rubin/Feynman/Feynman_Next。"""
        source = inspect.getsource(main_agent.run_hotspot_scan)
        self.assertIn("load_sector_spec", source)
        self.assertNotIn('"Vera_Rubin"', source)
        self.assertNotIn('"Feynman"', source)
        self.assertNotIn('"Feynman_Next"', source)


class TestSectorSpecs(unittest.TestCase):
    """板塊參數化：data/priors/sector_specs.json 查表行為。"""

    def test_cpo_sector_spec_matches_existing_behavior(self):
        """CPO_Optical_Transceiver 查表結果必須與舊版寫死值完全等價（回歸測試）。"""
        spec = load_sector_spec("CPO_Optical_Transceiver")
        self.assertEqual(spec["current_generation"], "Vera_Rubin")
        self.assertEqual(spec["next_generation"], "Feynman")
        self.assertEqual(spec["future_generation"], "Feynman_Next")
        self.assertFalse(spec["sector_spec_missing"])
        self.assertIsInstance(spec["narrative_hint"], str)
        self.assertTrue(len(spec["narrative_hint"]) > 0)

    def test_unknown_sector_returns_na_and_missing_flag(self):
        """查無板塊規格時，世代欄位一律為 N/A，且 sector_spec_missing=True，
        避免各 expert 誤套用其他板塊的 GPU 世代敘事或自行編造世代名。"""
        spec = load_sector_spec("Some_Unregistered_Sector_XYZ")
        self.assertEqual(spec["current_generation"], "N/A")
        self.assertEqual(spec["next_generation"], "N/A")
        self.assertEqual(spec["future_generation"], "N/A")
        self.assertTrue(spec["sector_spec_missing"])
        self.assertEqual(spec["narrative_hint"], "")

    def test_supply_chain_expert_prompt_forbids_fabrication_when_spec_missing(self):
        """世代規格缺失時，supply_chain_expert_node 的 prompt 組裝邏輯必須明示
        「禁止套用 GPU 世代敘事、禁止編造世代名」，不得沉默地留白。"""
        source = inspect.getsource(main_agent.supply_chain_expert_node)
        self.assertIn("sector_spec_missing", source)
        self.assertIn("禁止", source)


class TestMediaStoryDynamicRepresentatives(unittest.TestCase):
    """媒體/情緒專家節點的代表股改為動態選取，不得寫死 FOCI/MCT/弘塑/雙鴻。"""

    def test_media_story_prompt_no_longer_hardcodes_tickers(self):
        source = inspect.getsource(main_agent.media_story_expert_node)
        for hardcoded_name in ("FOCI", "MCT", "弘塑", "雙鴻", "聯鈞", "晟銘電"):
            self.assertNotIn(hardcoded_name, source)

    def test_pick_cv_extremes_selects_max_and_min_by_yoy(self):
        raw_revenue = {
            "AAA.TW": {"name": "AAA公司", "real_yoy_pct": 12.0},
            "BBB.TW": {"name": "BBB公司", "last_month_yoy": 80.0},
            "CCC.TW": {"name": "CCC公司", "real_yoy_pct": -5.0},
        }
        highest, lowest = _pick_cv_extremes(raw_revenue)
        self.assertEqual(highest, "BBB公司")
        self.assertEqual(lowest, "CCC公司")

    def test_pick_cv_extremes_prefers_real_yoy_over_mechanical_extrapolation(self):
        raw_revenue = {
            "AAA.TW": {"name": "AAA公司", "real_yoy_pct": 5.0, "last_month_yoy": 999.0},
        }
        highest, lowest = _pick_cv_extremes(raw_revenue)
        self.assertEqual(highest, "AAA公司")
        self.assertEqual(lowest, "AAA公司")

    def test_pick_cv_extremes_returns_empty_when_no_data(self):
        """無資料時必須回傳空字串，呼叫端據此禁止舉例（不得編造代表股）。"""
        highest, lowest = _pick_cv_extremes({})
        self.assertEqual(highest, "")
        self.assertEqual(lowest, "")

        highest2, lowest2 = _pick_cv_extremes(None)
        self.assertEqual(highest2, "")
        self.assertEqual(lowest2, "")


class TestGetLlmModel(unittest.TestCase):
    """get_llm_model 供應商切換至 NVIDIA NIM（GLM-5.2）：無金鑰時 fail loud，不捏造假資料。"""

    def test_raises_when_nvidia_nim_api_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NVIDIA_NIM_API_KEY", None)
            with self.assertRaises(ValueError) as ctx:
                get_llm_model()
            self.assertIn("NVIDIA_NIM_API_KEY", str(ctx.exception))


class TestBacklogNotApplicablePrompting(unittest.TestCase):
    """板塊無 equipment 分類成員時（current_backlog_yoy_pct 全為 None），
    pricing_revenue_expert / report_writer 的 prompt 必須明示「Backlog 不適用」，
    禁止暗示以 0.0 充數；quality_critic 的要求 2 須改為條件式，不得因缺數據判 FAIL。
    """

    NOT_APPLICABLE_RAW_REVENUE = {
        "9999": {
            "name": "散熱元件公司",
            "current_backlog_yoy_pct": None,
            "backlog_yoy_curve_3m": [None, None, None],
            "backlog_not_applicable_note": "本板塊無 equipment 分類成員，Backlog 板塊層訊號不適用",
            "is_golden_accumulation_target": False,
        },
    }

    APPLICABLE_RAW_REVENUE = {
        "3450.TW": {
            "name": "FOCI",
            "current_backlog_yoy_pct": 62.5,
            "backlog_yoy_curve_3m": [62.5, 62.5, 62.5],
            "backlog_not_applicable_note": None,
            "is_golden_accumulation_target": False,
        },
    }

    def _make_fake_llm(self, captured: dict):
        fake_llm = MagicMock()

        def _invoke(messages):
            captured["messages"] = messages
            response = MagicMock()
            response.content = "測試報告內容"
            return response

        fake_llm.invoke.side_effect = _invoke
        return fake_llm

    def test_pricing_revenue_expert_prompt_states_not_applicable_when_no_equipment(self):
        captured = {}
        fake_monitor = MagicMock()
        fake_monitor.resolve_sector_members.return_value = (["9999"], "registry")
        fake_monitor.get_high_frequency_pricing.return_value = {}
        fake_monitor.simulate_revenue_inflection.return_value = self.NOT_APPLICABLE_RAW_REVENUE

        state = {"target_sector": "Thermal_Component_Only_Sector", "as_of_date": ""}

        with patch.object(main_agent, "monitor", fake_monitor), \
             patch.object(main_agent, "get_llm_model", return_value=self._make_fake_llm(captured)):
            main_agent.pricing_revenue_expert_node(state)

        prompt_text = captured["messages"][-1].content
        self.assertIn("本板塊無 equipment 分類成員，Backlog 訊號不適用", prompt_text)
        # 禁止暗示以 0.0 充數的措辭不應出現在 Backlog 段落指示中
        self.assertNotIn("大於 50%", prompt_text)

    def test_pricing_revenue_expert_prompt_unchanged_when_equipment_present(self):
        """CPO 回歸：有 equipment 成員時，Backlog 領先性提問維持原樣。"""
        captured = {}
        fake_monitor = MagicMock()
        fake_monitor.resolve_sector_members.return_value = (["3450.TW"], "registry")
        fake_monitor.get_high_frequency_pricing.return_value = {}
        fake_monitor.simulate_revenue_inflection.return_value = self.APPLICABLE_RAW_REVENUE

        state = {"target_sector": "CPO_Optical_Transceiver", "as_of_date": ""}

        with patch.object(main_agent, "monitor", fake_monitor), \
             patch.object(main_agent, "get_llm_model", return_value=self._make_fake_llm(captured)):
            main_agent.pricing_revenue_expert_node(state)

        prompt_text = captured["messages"][-1].content
        self.assertIn("設備 Backlog YoY 是否已率先爆發 (大於 50%)", prompt_text)
        self.assertNotIn("Backlog 訊號不適用", prompt_text)

    def test_report_writer_prompt_states_not_applicable_when_no_equipment(self):
        captured = {}
        state = {
            "target_sector": "Thermal_Component_Only_Sector",
            "current_generation": "N/A",
            "next_generation": "N/A",
            "future_generation": "N/A",
            "sector_spec_missing": True,
            "supply_chain_analysis": {"summary": "供應鏈摘要"},
            "pricing_revenue_analysis": {
                "summary": "價格摘要",
                "raw_revenue": self.NOT_APPLICABLE_RAW_REVENUE,
            },
            "media_story_anticipation": {"summary": "媒體摘要"},
        }

        with patch.object(main_agent, "get_llm_model", return_value=self._make_fake_llm(captured)):
            main_agent.report_writer_node(state)

        prompt_text = captured["messages"][-1].content
        self.assertIn("本板塊無 equipment 分類成員，Backlog 訊號不適用", prompt_text)

    def test_report_writer_prompt_unchanged_when_equipment_present(self):
        captured = {}
        state = {
            "target_sector": "CPO_Optical_Transceiver",
            "current_generation": "Vera_Rubin",
            "next_generation": "Feynman",
            "future_generation": "Feynman_Next",
            "sector_spec_missing": False,
            "supply_chain_analysis": {"summary": "供應鏈摘要"},
            "pricing_revenue_analysis": {
                "summary": "價格摘要",
                "raw_revenue": self.APPLICABLE_RAW_REVENUE,
            },
            "media_story_anticipation": {"summary": "媒體摘要"},
        }

        with patch.object(main_agent, "get_llm_model", return_value=self._make_fake_llm(captured)):
            main_agent.report_writer_node(state)

        prompt_text = captured["messages"][-1].content
        self.assertIn("設備 Backlog 增幅", prompt_text)
        self.assertNotIn("Backlog 訊號不適用", prompt_text)

    def test_quality_critic_requirement_conditional_when_no_equipment(self):
        """無 equipment 成員時，critic 的要求 2 必須改為條件式（誠實標示即算通過），
        不得要求設備商 Backlog YoY 定量數據。"""
        captured = {}
        state = {
            "feasibility_report_draft": "本板塊無 equipment 分類成員，Backlog 訊號不適用。",
            "iteration_count": 0,
            "future_generation": "N/A",
            "sector_spec_missing": True,
            "pricing_revenue_analysis": {"raw_revenue": self.NOT_APPLICABLE_RAW_REVENUE},
        }

        fake_structured_llm = MagicMock()

        def _invoke(messages):
            captured["messages"] = messages
            return main_agent.CriticDecision(validation_status="PASS", critic_feedback="")

        fake_structured_llm.invoke.side_effect = _invoke

        with patch.object(main_agent, "get_llm_model", return_value=fake_structured_llm):
            main_agent.quality_critic_node(state)

        prompt_text = captured["messages"][-1].content
        system_text = captured["messages"][0].content
        self.assertIn("Backlog 板塊層訊號不適用", prompt_text)
        self.assertNotIn("至少一家設備商的拉貨領先度 (Backlog YoY) 定量數據", prompt_text)
        self.assertIn("不得因缺乏設備商 Backlog 數據而判 FAIL", system_text)

    def test_quality_critic_requirement_unchanged_when_equipment_present(self):
        """CPO 回歸：有 equipment 成員時，critic 的要求 2 維持原本的定量數據要求。"""
        captured = {}
        state = {
            "feasibility_report_draft": "報告內容含 Backlog YoY 62.5%",
            "iteration_count": 0,
            "future_generation": "Feynman_Next",
            "sector_spec_missing": False,
            "pricing_revenue_analysis": {"raw_revenue": self.APPLICABLE_RAW_REVENUE},
        }

        fake_structured_llm = MagicMock()

        def _invoke(messages):
            captured["messages"] = messages
            return main_agent.CriticDecision(validation_status="PASS", critic_feedback="")

        fake_structured_llm.invoke.side_effect = _invoke

        with patch.object(main_agent, "get_llm_model", return_value=fake_structured_llm):
            main_agent.quality_critic_node(state)

        prompt_text = captured["messages"][-1].content
        # 2026-07-05 修訂：要求 2 對齊系統設計——Backlog 本為板塊層代理訊號，
        # critic 不得要求「單一設備商訂單」這種系統不產出的數據（CPO 重掃曾因此三輪 FAIL）。
        self.assertIn("板塊層代理訊號", prompt_text)
        self.assertIn("不得要求報告提供系統設計上不存在的『單一設備商訂單』數據", prompt_text)
        self.assertNotIn("Backlog 板塊層訊號不適用（程式端已確認）", prompt_text)


class TestTickerDisplayFormatRules(unittest.TestCase):
    """報告提及任何標的一律「代號＋中文名」並列（見交辦：3324 雙鴻範例）。
    report_writer 的誠實化規則須新增此條，quality_critic 的審查清單須新增對應檢查項。"""

    NOT_APPLICABLE_RAW_REVENUE = TestBacklogNotApplicablePrompting.NOT_APPLICABLE_RAW_REVENUE
    APPLICABLE_RAW_REVENUE = TestBacklogNotApplicablePrompting.APPLICABLE_RAW_REVENUE

    def _make_fake_llm(self, captured: dict):
        fake_llm = MagicMock()

        def _invoke(messages):
            captured["messages"] = messages
            response = MagicMock()
            response.content = "測試報告內容"
            return response

        fake_llm.invoke.side_effect = _invoke
        return fake_llm

    def test_report_writer_prompt_requires_ticker_and_chinese_name_pair(self):
        """report_writer 的誠實化規則須明文要求「代號 中文名」並列格式，
        並禁止只寫代號、只寫名稱或使用英文代稱。"""
        captured = {}
        state = {
            "target_sector": "CPO_Optical_Transceiver",
            "current_generation": "Vera_Rubin",
            "next_generation": "Feynman",
            "future_generation": "Feynman_Next",
            "sector_spec_missing": False,
            "supply_chain_analysis": {"summary": "供應鏈摘要"},
            "pricing_revenue_analysis": {
                "summary": "價格摘要",
                "raw_revenue": self.APPLICABLE_RAW_REVENUE,
            },
            "media_story_anticipation": {"summary": "媒體摘要"},
        }

        with patch.object(main_agent, "get_llm_model", return_value=self._make_fake_llm(captured)):
            main_agent.report_writer_node(state)

        prompt_text = captured["messages"][-1].content
        self.assertIn("代號 中文名", prompt_text)
        self.assertIn("3324 雙鴻", prompt_text)
        self.assertIn("禁止只寫代號、只寫名稱或使用英文代稱", prompt_text)

    def test_report_writer_prompt_ticker_rule_present_when_spec_missing_too(self):
        """世代規格缺失（無 GPU 世代框架）板塊，新規則同樣須存在，不受 spec_missing 分支影響。"""
        captured = {}
        state = {
            "target_sector": "Thermal_Component_Only_Sector",
            "current_generation": "N/A",
            "next_generation": "N/A",
            "future_generation": "N/A",
            "sector_spec_missing": True,
            "supply_chain_analysis": {"summary": "供應鏈摘要"},
            "pricing_revenue_analysis": {
                "summary": "價格摘要",
                "raw_revenue": self.NOT_APPLICABLE_RAW_REVENUE,
            },
            "media_story_anticipation": {"summary": "媒體摘要"},
        }

        with patch.object(main_agent, "get_llm_model", return_value=self._make_fake_llm(captured)):
            main_agent.report_writer_node(state)

        prompt_text = captured["messages"][-1].content
        self.assertIn("代號 中文名", prompt_text)
        self.assertIn("禁止只寫代號、只寫名稱或使用英文代稱", prompt_text)

    def test_quality_critic_prompt_includes_ticker_format_check(self):
        """quality_critic 的審查清單須新增個股呈現格式檢查項：通篇只有代號無中文名、
        或只有名稱無代號時應判 FAIL 並具體指出。"""
        captured = {}
        state = {
            "feasibility_report_draft": "報告內容含 3324 雙鴻 與 Backlog YoY 62.5%",
            "iteration_count": 0,
            "future_generation": "Feynman_Next",
            "sector_spec_missing": False,
            "pricing_revenue_analysis": {"raw_revenue": self.APPLICABLE_RAW_REVENUE},
        }

        fake_structured_llm = MagicMock()

        def _invoke(messages):
            captured["messages"] = messages
            return main_agent.CriticDecision(validation_status="PASS", critic_feedback="")

        fake_structured_llm.invoke.side_effect = _invoke

        with patch.object(main_agent, "get_llm_model", return_value=fake_structured_llm):
            main_agent.quality_critic_node(state)

        prompt_text = captured["messages"][-1].content
        self.assertIn("個股呈現格式", prompt_text)
        self.assertIn("代號 中文名", prompt_text)
        self.assertIn("一律判 FAIL", prompt_text)


class TestLlmFailoverChain(unittest.TestCase):
    """LLM 三層備援鏈（NIM → DeepSeek 官方 → Claude CLI）：不打真網路，全部 fake/monkeypatch。"""

    def setUp(self):
        main_agent._reset_llm_failover_state()

    def tearDown(self):
        main_agent._reset_llm_failover_state()

    @staticmethod
    def _ok_response(text="OK"):
        resp = MagicMock()
        resp.content = text
        return resp

    @patch.dict(os.environ, {"NVIDIA_NIM_API_KEY": "fake-nim", "DEEPSEEK_API_KEY": "fake-ds"})
    def test_429_two_rounds_then_degrade_to_deepseek(self):
        """429 同層最多重試 2 輪（各等 180 秒），仍 429 → 降級至 Tier 2（DeepSeek）。"""
        tier1_llm = MagicMock()
        tier1_llm.invoke.side_effect = Exception("Error code: 429 - rate limit exceeded")
        tier2_llm = MagicMock()
        tier2_llm.invoke.return_value = self._ok_response("DeepSeek 回應")

        with patch.object(main_agent.time, "sleep") as fake_sleep, \
             patch.object(main_agent, "get_llm_model", return_value=tier2_llm) as fake_get:
            result = main_agent._invoke_with_retry(tier1_llm, [])

        self.assertEqual(result.content, "DeepSeek 回應")
        # 同層 429 等待恰為 2 輪、各 180 秒
        sleeps_180 = [c for c in fake_sleep.call_args_list if c.args and c.args[0] == 180]
        self.assertEqual(len(sleeps_180), 2)
        # 同層共嘗試 3 次（原始 1 次 + 限流重試 2 輪）後才降級
        self.assertEqual(tier1_llm.invoke.call_count, 3)
        # 降級時以 tier 參數重建 LLM（含 structured schema 路徑）
        fake_get.assert_called_once_with(None, tier=main_agent.TIER_DEEPSEEK)

    @patch.dict(os.environ, {"NVIDIA_NIM_API_KEY": "fake-nim", "DEEPSEEK_API_KEY": "fake-ds"})
    def test_degradation_is_sticky_per_process(self):
        """降級後 _current_tier 黏性生效：後續 get_llm_model() 不再回到 NIM。"""
        tier1_llm = MagicMock()
        tier1_llm.invoke.side_effect = Exception("Error code: 429 - rate limit exceeded")
        tier2_llm = MagicMock()
        tier2_llm.invoke.return_value = self._ok_response()

        with patch.object(main_agent.time, "sleep"), \
             patch.object(main_agent, "get_llm_model", return_value=tier2_llm):
            main_agent._invoke_with_retry(tier1_llm, [])

        self.assertEqual(main_agent._current_tier, main_agent.TIER_DEEPSEEK)
        # 黏性：不經 patch 的真 get_llm_model 也直接建出 DeepSeek 端點
        llm = main_agent.get_llm_model()
        self.assertIn("api.deepseek.com", str(llm.openai_api_base))

    def test_start_tier_skips_to_deepseek_when_nim_key_missing(self):
        """順序容錯：缺 NVIDIA_NIM_API_KEY 但有 DEEPSEEK_API_KEY → 直接從 Tier 2 起跳。"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake-ds"}, clear=True):
            llm = main_agent.get_llm_model()
            self.assertIn("api.deepseek.com", str(llm.openai_api_base))

    def test_raises_when_both_keys_missing(self):
        """兩把金鑰皆缺 → raise（Claude CLI 不作起始層）。"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                main_agent.get_llm_model()
            self.assertIn("NVIDIA_NIM_API_KEY", str(ctx.exception))

    def test_claude_cli_tier_raises_when_cli_missing(self):
        """Tier 3 在找不到 claude CLI（如 CI 環境）時，建構即 raise 明確錯誤。"""
        with patch.object(main_agent.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                main_agent.get_llm_model(tier=main_agent.TIER_CLAUDE_CLI)
            self.assertIn("claude", str(ctx.exception).lower())

    def test_degrade_to_claude_cli_raises_in_ci_like_env(self):
        """缺 DEEPSEEK_API_KEY 時跳過 Tier 2；降到 Tier 3 但無 CLI → raise（CI 情境 fail loud）。"""
        failing_llm = MagicMock()
        failing_llm.invoke.side_effect = Exception("Error code: 429 - rate limit exceeded")

        with patch.dict(os.environ, {"NVIDIA_NIM_API_KEY": "fake-nim"}, clear=True), \
             patch.object(main_agent.time, "sleep"), \
             patch.object(main_agent.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                main_agent._invoke_with_retry(failing_llm, [])
            self.assertIn("claude", str(ctx.exception).lower())

    @patch.dict(os.environ, {"NVIDIA_NIM_API_KEY": "fake-nim"})
    def test_provider_usage_recorded_on_success(self):
        """誠實標示：成功呼叫後 LLM_PROVIDERS_USED 記錄實際使用的 provider/model。"""
        llm = MagicMock()
        llm.invoke.return_value = self._ok_response()
        main_agent._invoke_with_retry(llm, [])
        self.assertEqual(len(main_agent.LLM_PROVIDERS_USED), 1)
        self.assertIn("NVIDIA NIM", main_agent.LLM_PROVIDERS_USED[0])

    def test_deepseek_structured_uses_json_mode_wrapper(self):
        """Tier 2 結構化輸出必須走 DeepSeekStructuredLLM（json_mode + schema 指令），
        因 deepseek-v4-pro thinking 模式不支援 json_schema response_format 與強制 tool_choice
        （2026-07-04 實測皆 400）。"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake-ds"}):
            llm = main_agent.get_llm_model(main_agent.CriticDecision, tier=main_agent.TIER_DEEPSEEK)
        self.assertIsInstance(llm, main_agent.DeepSeekStructuredLLM)
        # 包裝會在訊息尾端追加含 json 字樣的 schema 指令（DeepSeek json_mode 硬性要求）
        inner = MagicMock()
        llm._structured = inner
        llm.invoke([main_agent.HumanMessage(content="審查測試")])
        sent_messages = inner.invoke.call_args.args[0]
        self.assertIn("JSON Schema", sent_messages[-1].content)
        self.assertIn("validation_status", sent_messages[-1].content)

    def test_claude_cli_structured_output_parse_retry_then_success(self):
        """Tier 3 結構化輸出：第一次回非 JSON → 重試 1 次成功解析 + Pydantic 驗證。"""
        with patch.object(main_agent.shutil, "which", return_value="C:/fake/claude.cmd"):
            cli_llm = main_agent.get_llm_model(main_agent.CriticDecision, tier=main_agent.TIER_CLAUDE_CLI)

        with patch.object(cli_llm, "_run_cli",
                          side_effect=["這不是 JSON",
                                       '{"validation_status": "PASS", "critic_feedback": "合格"}']):
            decision = cli_llm.invoke([main_agent.HumanMessage(content="審查測試")])

        self.assertEqual(decision.validation_status, "PASS")
        self.assertEqual(decision.critic_feedback, "合格")

    def test_claude_cli_structured_output_raises_after_retry_exhausted(self):
        """Tier 3 結構化輸出：重試 1 次後仍解析失敗 → raise（不捏造）。"""
        with patch.object(main_agent.shutil, "which", return_value="C:/fake/claude.cmd"):
            cli_llm = main_agent.get_llm_model(main_agent.CriticDecision, tier=main_agent.TIER_CLAUDE_CLI)

        with patch.object(cli_llm, "_run_cli", side_effect=["垃圾輸出一", "垃圾輸出二"]):
            with self.assertRaises(RuntimeError):
                cli_llm.invoke([main_agent.HumanMessage(content="審查測試")])


if __name__ == "__main__":
    unittest.main()
