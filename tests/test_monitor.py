import unittest
from unittest import mock
from market_monitor import (
    MarketInformationMonitor,
    CONSENSUS_MAX,
    MEMBERSHIP_SOURCE_REGISTRY,
    MEMBERSHIP_SOURCE_FALLBACK,
)

class TestMarketInformationMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = MarketInformationMonitor()

    def test_high_frequency_pricing(self):
        """測試高頻報價數據結構與趨勢計算"""
        result = self.monitor.get_high_frequency_pricing("CPO_Optical_Transceiver")
        self.assertIn("sector", result)
        self.assertIn("trend", result)
        self.assertIn("weekly_change_pct", result)
        self.assertIn("data_points", result)
        self.assertIsInstance(result["data_points"], list)
        self.assertEqual(len(result["data_points"]), 12)

    def test_supply_chain_schedule(self):
        """測試供應鏈洗牌與內含價值計算"""
        result = self.monitor.get_supply_chain_schedule("Vera_Rubin", "Feynman")
        self.assertEqual(result["current_generation"], "Vera_Rubin")
        self.assertEqual(result["next_generation"], "Feynman")
        self.assertIn("bottlenecks", result)
        self.assertIn("timeline_matrix", result)
        
        # 驗證特定公司的價值佔比是否正確提升
        foci_data = next(x for x in result["timeline_matrix"] if x["company_id"] == "3450.TW")
        self.assertEqual(foci_data["content_value_current"], 4.5)
        self.assertEqual(foci_data["content_value_next"], 14.0)
        self.assertEqual(foci_data["change_pct"], 211.11)

    def test_fetch_real_monthly_revenue(self):
        """測試從證交所開放 API 抓取真實月度營收"""
        result = self.monitor.fetch_real_monthly_revenue()
        self.assertIsInstance(result, dict)
        # 即使 API 斷線，因有 Fallback，它會回傳快取的 dict (可能為空或有資料)
        if len(result) > 0:
            # 隨機抽樣一個代號檢查欄位
            sample_key = list(result.keys())[0]
            item = result[sample_key]
            self.assertIn("revenue_billion", item)
            self.assertIn("yoy_pct", item)
            self.assertIn("date_ym", item)
            self.assertIn("company_name", item)

    def test_simulate_revenue_inflection(self):
        """測試營收基期與 YoY 拐點預測"""
        company_ids = ["3450.TW", "3324.TWO"]
        result = self.monitor.simulate_revenue_inflection(company_ids)
        
        for cid in company_ids:
            self.assertIn(cid, result)
            data = result[cid]
            self.assertIn("name", data)
            self.assertIn("inflection_expected", data)
            self.assertIn("peak_month", data)
            self.assertIn("projected_peak_yoy_pct", data)
            self.assertIn("equipment_lead_active", data)
            self.assertIn("is_golden_accumulation_target", data)
            # 驗證真實數據整合欄位
            self.assertIn("has_real_data", data)
            self.assertIn("real_date_ym", data)
            self.assertIn("real_revenue_billion", data)
            self.assertIn("real_yoy_pct", data)
            # 誠實化欄位：機械外推 / 粗粒度 / 板塊代理訊號標示
            self.assertIn("projection_note", data)
            self.assertIn("granularity_note", data)
            self.assertIn("backlog_signal_note", data)

    def test_consensus_score_is_integer_not_false_precision(self):
        """Consensus 分數須為整數（禁止小數點假精度，見 CONTEXT.md 誠實化修正）"""
        for cid in ["3450.TW", "3324.TWO"]:
            consensus = self.monitor._compute_consensus(cid)
            if consensus is not None:
                self.assertEqual(consensus, round(consensus))
                self.assertIsInstance(consensus, int)

    def test_golden_target_flag_matches_pre_registered_thresholds(self):
        """is_golden_accumulation_target 必須嚴格等於 pre-registered 門檻運算結果，
        不允許任何呼叫端另立更寬鬆的門檻（見 CONTEXT.md / ADR 0003 誠實化修正第 3 點）。"""
        company_ids = ["3450.TW", "3324.TWO"]
        result = self.monitor.simulate_revenue_inflection(company_ids)
        for cid, data in result.items():
            expected = (
                data["consensus_score"] < CONSENSUS_MAX
                and data["equipment_lead_active"]
                and data["last_month_yoy"] < 15.0
            )
            self.assertEqual(data["is_golden_accumulation_target"], expected)
            # 共識度超過門檻者絕不可被標記為黃金標的
            if data["consensus_score"] >= CONSENSUS_MAX:
                self.assertFalse(data["is_golden_accumulation_target"])

class TestResolveSectorMembers(unittest.TestCase):
    """
    板塊成員解析單一入口的來源切換測試（見 HANDOFF 板塊登記簿 ∩ universe 快照改版）。
    sector_membership 模組以 monkeypatch 模擬（模組雖已存在但登記簿尚未 seed 任何板塊，
    真實呼叫一律回傳 []，故用 mock 明確驗證兩條路徑的分岔行為）。
    """

    def setUp(self):
        self.monitor = MarketInformationMonitor()

    def test_registry_path_when_members_found(self):
        """登記簿有紀錄（非空清單）時，來源應標記 registry，且直接採用登記簿清單。"""
        import sector_membership
        with mock.patch.object(sector_membership, "get_members_in_universe",
                               return_value=["1101", "2330", "3131"]):
            members, source = self.monitor.resolve_sector_members("CPO_Optical_Transceiver", "2026-06-30")

        self.assertEqual(source, MEMBERSHIP_SOURCE_REGISTRY)
        self.assertEqual(sorted(members), ["1101", "2330", "3131"])

    def test_fallback_path_when_registry_empty(self):
        """登記簿無紀錄（回傳 []）時，應 fallback 至現行 content_value era 名單，
        且名單須與 get_point_in_time_matrix 完全一致（驗收關鍵：fallback = 現狀等價）。"""
        import sector_membership
        with mock.patch.object(sector_membership, "get_members_in_universe", return_value=[]):
            members, source = self.monitor.resolve_sector_members("CPO_Optical_Transceiver", "2024-06-30")

        expected = [it["company_id"] for it in self.monitor.get_point_in_time_matrix("2024-06-30")]
        self.assertEqual(source, MEMBERSHIP_SOURCE_FALLBACK)
        self.assertEqual(sorted(members), sorted(expected))

    def test_fallback_path_when_registry_module_missing(self):
        """sector_membership 模組不可 import（ImportError）時同樣視為無登記簿資料，走 fallback。"""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "sector_membership":
                raise ImportError("simulated: sector_membership not yet available")
            return real_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", side_effect=fake_import):
            members, source = self.monitor.resolve_sector_members("CPO_Optical_Transceiver", None)

        expected = [it["company_id"] for it in self.monitor.get_point_in_time_matrix(None)]
        self.assertEqual(source, MEMBERSHIP_SOURCE_FALLBACK)
        self.assertEqual(sorted(members), sorted(expected))

    def test_current_fallback_produces_legacy_12_stock_list(self):
        """驗收關鍵：登記簿尚未 seed（現況）時，resolve_sector_members 的實際輸出
        （不 mock，走真實 import）名單應與改版前的 get_point_in_time_matrix 結果一致。"""
        members, source = self.monitor.resolve_sector_members("CPO_Optical_Transceiver", None)
        expected = [it["company_id"] for it in self.monitor.get_point_in_time_matrix(None)]

        self.assertEqual(source, MEMBERSHIP_SOURCE_FALLBACK)
        self.assertEqual(sorted(members), sorted(expected))
        self.assertEqual(len(members), 12, "現行 Feynman 世代（最新 era）應為 12 檔手選名單")


if __name__ == "__main__":
    unittest.main()
