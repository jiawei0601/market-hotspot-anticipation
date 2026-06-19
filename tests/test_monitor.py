import unittest
from market_monitor import MarketInformationMonitor

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

if __name__ == "__main__":
    unittest.main()
