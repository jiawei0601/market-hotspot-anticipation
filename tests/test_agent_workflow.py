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
        self.assertIn("至少一家設備商的拉貨領先度 (Backlog YoY) 定量數據", prompt_text)
        self.assertNotIn("Backlog 板塊層訊號不適用（程式端已確認）", prompt_text)


if __name__ == "__main__":
    unittest.main()
