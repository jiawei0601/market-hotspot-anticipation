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
        驗證營收 Point-in-Time 發佈滯後：2020-04-05 時，因為 3 月份營收最快要 4/10 申報，
        因此 3 月營收不可見，has_real_data 必須符合發佈條件。
        """
        # 回測點在 4/5，尚未到 4/10，所以 3 月營收 (即最新月份) 應該被視為不可見 (不開啟真實營收)
        as_of = "2020-04-05"
        res = self.monitor.simulate_revenue_inflection(["3131.TWO"], as_of_date=as_of)
        
        target = res.get("3131.TWO", {})
        
        # 在此點時間，雖然 TWSE 資料庫有今日的資料，但在歷史 2020-04-05 還不應該發布該月份數據
        self.assertFalse(target.get("has_real_data", False), "在申報截止日前不應取得未來或當月尚未申報之真實營收數據")

if __name__ == "__main__":
    unittest.main()
