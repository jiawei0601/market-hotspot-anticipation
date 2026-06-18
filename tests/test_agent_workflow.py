import unittest
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

if __name__ == "__main__":
    unittest.main()
