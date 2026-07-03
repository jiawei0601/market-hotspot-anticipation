import inspect
import unittest
import main_agent
from main_agent import app, route_based_on_critic

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

if __name__ == "__main__":
    unittest.main()
