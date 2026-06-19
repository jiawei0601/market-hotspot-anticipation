import unittest
import datetime
from market_monitor import MarketInformationMonitor

class TestPointInTimeBacktest(unittest.TestCase):
    def setUp(self):
        self.monitor = MarketInformationMonitor()

    def test_pricing_point_in_time_truncation(self):
        """
        驗證當設定 2021-06-01 作為 as_of_date 時，價格與日期的上限沒有超過 2021-06-01。
        """
        as_of = "2021-06-01"
        res = self.monitor.get_high_frequency_pricing("CPO_Optical_Transceiver", as_of_date=as_of)
        
        # 取得最後一筆報價的日期
        last_date_str = res["data_points"][-1]["date"]
        last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        
        limit_date = datetime.datetime.strptime(as_of, "%Y-%m-%d").date()
        
        self.assertTrue(last_date <= limit_date, f"最後一筆日期 {last_date_str} 超出了回測截止日 {as_of}")

    def test_revenue_point_in_time_reporting_lag(self):
        """
        PIT 日粒度驗證：as_of=2020-04-05 時，3 月份營收尚未公告（announce_date=2020-04-10），
        歷史快照仍有舊期資料（has_real_data=True），但最新可見期應為 2020-02，而非 2020-03。

        資料來源：data/snapshots/2020-04/revenue.json 的 3131 記錄
        announce_date=2020-04-10 > 2020-04-05，所以該期被跳過；
        data/snapshots/2020-03/revenue.json 的 3131 記錄
        announce_date=2020-03-10 <= 2020-04-05，period=2020-02，被納入。
        """
        as_of = "2020-04-05"
        res = self.monitor.simulate_revenue_inflection(["3131.TWO"], as_of_date=as_of)
        target = res.get("3131.TWO", {})

        self.assertTrue(target.get("has_real_data", False),
                        "PIT 快照應有歷史真實資料（非最新月份，但仍有舊期）")
        real_period = target.get("real_date_ym", "")
        self.assertEqual(real_period, "2020-02",
                         f"2020-04-05 最新可見期應為 2020-02（3 月 announce_date=2020-04-10 未到），但得到 {real_period}")

    def test_backlog_lead_real_data(self):
        """get_backlog_lead 應從 PIT 快照回傳真實 YoY（非合成），且日粒度 PIT 正確。"""
        # live：應有真實非零值
        bl_live = self.monitor.get_backlog_lead()
        self.assertIsInstance(bl_live, float)

        # PIT 2020-04-15：announce_date=2020-04-10 已過 → 應有 Mar 2020 YoY
        bl_april = self.monitor.get_backlog_lead("2020-04-15")
        self.assertNotEqual(bl_april, 0.0, "2020-04-15 後 3 月 YoY 應可見，不應為 0")

        # PIT 2020-04-05：announce_date=2020-04-10 未到 → 回退至 Feb YoY，非 0
        bl_before = self.monitor.get_backlog_lead("2020-04-05")
        self.assertNotEqual(bl_before, 0.0, "應 fallback 至 2020-02 期 YoY，非 0")

    def test_consensus_real_data(self):
        """_compute_consensus 應從持股快照回傳 0-100 值；資料不足時回傳 None。"""
        c = self.monitor._compute_consensus("3131.TWO")
        self.assertIsNotNone(c)
        self.assertGreaterEqual(c, 0.0)
        self.assertLessEqual(c, 100.0)

        # 遠早於快照起始（2013-01），資料不足 → None
        c_old = self.monitor._compute_consensus("3131.TWO", as_of_date="2013-06-01")
        self.assertIsNone(c_old, "2013 年前無快照，應回傳 None")

    def test_simulate_uses_real_yoy(self):
        """simulate_revenue_inflection 應使用 PIT 快照真實 YoY，非合成亂數。"""
        as_of = "2024-06-30"
        res = self.monitor.simulate_revenue_inflection(["3131.TWO"], as_of_date=as_of)
        data = res["3131.TWO"]

        self.assertTrue(data["has_real_data"], "2024-06 快照存在，應為真實資料")
        self.assertIsNotNone(data["real_yoy_pct"], "real_yoy_pct 不應為 None")
        self.assertIsInstance(data["current_backlog_yoy_pct"], float)

        # 確認 yoy 不是由全零陣列驅動
        last_yoy = data["last_month_yoy"]
        self.assertNotEqual(last_yoy, 0.0,
                            "真實 YoY 不應恰好為 0.0（合成 fallback 才會如此）")


if __name__ == "__main__":
    unittest.main()
