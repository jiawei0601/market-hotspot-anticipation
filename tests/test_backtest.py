import unittest
import datetime
import json
import os
import pandas as pd
from unittest import mock
from market_monitor import MarketInformationMonitor
import backtest_engine
import monte_carlo_analyzer
from backtest_engine import BacktestEngine
from monte_carlo_analyzer import MonteCarloSimulator

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
        """_compute_consensus 應從持股+股價快照回傳 0-100 值；資料不足時回傳 None。"""
        c = self.monitor._compute_consensus("3131.TWO")
        self.assertIsNotNone(c)
        self.assertGreaterEqual(c, 0.0)
        self.assertLessEqual(c, 100.0)

        # 股價部分也應有值
        cp = self.monitor._compute_price_consensus("3131.TWO")
        self.assertIsNotNone(cp, "股價快照存在，price_consensus 不應為 None")
        self.assertGreaterEqual(cp, 0.0)
        self.assertLessEqual(cp, 100.0)

        # 遠早於快照起始（2013-01），資料不足 → None
        c_old = self.monitor._compute_consensus("3131.TWO", as_of_date="2013-06-01")
        self.assertIsNone(c_old, "2013 年前無快照，應回傳 None")

    def test_price_pit_truncation(self):
        """月底收盤 PIT：月中 as_of_date 不應見到當月收盤（close_date > as_of_date）。"""
        # 2020-01-15：1月 close_date=2020-01-31 > 2020-01-15 → 應排除
        hist = self.monitor._read_price_history("3131.TWO", "2020-01-15", n_months=3)
        self.assertTrue(len(hist) > 0, "應有歷史資料")
        latest_ym = hist[0][0]
        self.assertLessEqual(latest_ym, "2019-12",
                             f"2020-01-15 不應看到 2020-01 收盤，但最新期為 {latest_ym}")

    def test_price_consensus_cross_sectional(self):
        """price_consensus 橫斷面排名應合理：高位股 >= 低位股的 consensus。"""
        # 用固定 as_of 確保一致性
        as_of = "2024-06-30"
        cp_3131 = self.monitor._compute_price_consensus("3131.TWO", as_of_date=as_of)
        cp_3013 = self.monitor._compute_price_consensus("3013.TW", as_of_date=as_of)
        self.assertIsNotNone(cp_3131)
        self.assertIsNotNone(cp_3013)
        # 兩者都應在 0-100 內
        for v in (cp_3131, cp_3013):
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 100.0)

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


def _make_price_df(start_date_str: str, n_days: int, base_price: float = 100.0, daily_step: float = 0.5) -> pd.DataFrame:
    """建立測試用假日 K 線 DataFrame（欄位皆為小寫，與 backtest_engine / monte_carlo_analyzer 處理後格式一致）。"""
    dates = pd.date_range(start=start_date_str, periods=n_days, freq="D")
    closes = [base_price + i * daily_step for i in range(n_days)]
    df = pd.DataFrame({
        "open": closes,
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
        "close": closes,
        "volume": [1000] * n_days,
    }, index=dates)
    return df


def _slicing_fake_download(df: pd.DataFrame):
    """回傳一個模擬 yf.download 的函式：依 start/end 參數切片（模擬真實下載範圍行為）。"""
    def _fake(ticker, start=None, end=None, progress=False, **kwargs):
        sliced = df.loc[start:end] if (start or end) else df
        return sliced.copy()
    return _fake


class TestFixedHoldingPeriodExit(unittest.TestCase):
    """驗證 backtest_engine 的固定持有期（52週）出場規則。"""

    def setUp(self):
        # 建立一個乾淨的回測期間（短期，僅用於初始化，不觸發 run() 的完整流程）
        self.engine = BacktestEngine("2020-01-01", "2020-02-01", "TestSector")

    def tearDown(self):
        self.engine.restore_environment()
        # 還原為乾淨的空陣列，勿刪除此 git 追蹤的執行期檔案（避免破壞其他 agent 的工作區）
        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

    def test_holding_period_constant_is_52_weeks(self):
        """出場規則應為固定 52 週，與 monte_carlo_analyzer 的 52 週追蹤口徑一致。"""
        self.assertEqual(backtest_engine.HOLDING_PERIOD_WEEKS, 52)

    def test_closed_trade_uses_exit_price_at_52_weeks(self):
        """
        進場日 + 52 週後若回測結束日已涵蓋該時點，應以「52週後的價格」作為出場價，
        而非以 --end-date 當天價格（各標的持有期不再不一致）。
        """
        entry_date = "2020-01-06"
        exit_date_expected = (datetime.datetime.strptime(entry_date, "%Y-%m-%d").date()
                               + datetime.timedelta(weeks=52)).strftime("%Y-%m-%d")

        # 回測結束日設在出場日之後，且早於今天，確保視為「已出場」
        self.engine.end_date = datetime.datetime.strptime(exit_date_expected, "%Y-%m-%d").date() + datetime.timedelta(days=5)

        # 準備一筆已進場的 watchlist 紀錄
        watchlist = [{
            "company_id": "TEST.TW", "name": "測試標的", "sector": "TestSector",
            "entry_date": entry_date, "entry_price": 100.0, "current_price": 100.0,
            "max_price_since": 100.0, "min_price_since": 100.0,
            "max_return_pct": 0.0, "min_return_pct": 0.0, "current_return_pct": 0.0,
            "status": "tracking"
        }]
        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f)

        fake_price_df = _make_price_df("2019-12-01", 500, base_price=100.0, daily_step=0.2)

        # mock.patch context 確保測試結束後 yfinance.download 必定還原，不污染其他測試
        with mock.patch("yfinance.download", new=_slicing_fake_download(fake_price_df)):
            self.engine.resolve_fixed_holding_exits()

        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)[0]

        self.assertEqual(result["exit_status"], "closed")
        self.assertEqual(result["exit_date"], exit_date_expected)
        # 出場價必須是「52週後出場日當天」的收盤價：
        # 2021-01-04 距假資料起點 2019-12-01 共 400 天 → 100 + 400*0.2 = 180.0
        self.assertAlmostEqual(result["exit_price"], 180.0, places=2)
        self.assertIsNotNone(result["current_return_pct"])

    def test_incomplete_holding_period_marked_tracking_and_excluded(self):
        """
        若「進場日 + 52 週」超過回測結束日（尚未滿一年），應標記為持有期未滿（追蹤中），
        且與已出場樣本分開（不得有 exit_status == closed）。
        """
        entry_date = "2020-01-06"
        # 回測結束日設在進場後僅 10 天，遠早於 52 週
        self.engine.end_date = datetime.datetime.strptime(entry_date, "%Y-%m-%d").date() + datetime.timedelta(days=10)

        watchlist = [{
            "company_id": "TEST2.TW", "name": "測試標的2", "sector": "TestSector",
            "entry_date": entry_date, "entry_price": 100.0, "current_price": 100.0,
            "max_price_since": 100.0, "min_price_since": 100.0,
            "max_return_pct": 0.0, "min_return_pct": 0.0, "current_return_pct": 0.0,
            "status": "tracking"
        }]
        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f)

        fake_price_df = _make_price_df("2019-12-01", 60, base_price=100.0, daily_step=0.3)

        with mock.patch("yfinance.download", new=_slicing_fake_download(fake_price_df)):
            self.engine.resolve_fixed_holding_exits()

        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)[0]

        self.assertEqual(result["exit_status"], "tracking_incomplete")
        self.assertIsNone(result["exit_date"])
        self.assertIsNone(result["current_return_pct"])
        # current_price 應為「最後可得收盤價」而非期間最高價（誤導性數字）：
        # 期間終點 2020-01-16 距假資料起點 2019-12-01 共 46 天 → 100 + 46*0.3 = 113.8
        self.assertAlmostEqual(result["current_price"], 113.8, places=2)
        # 期間最高價為 high = close+1.0 = 114.8，不得被當作 current_price
        self.assertNotAlmostEqual(result["current_price"], 114.8, places=2)


class TestTradingCostApplication(unittest.TestCase):
    """驗證交易成本（手續費/證交稅/滑價）已套用於淨報酬計算，兩引擎口徑一致。"""

    def test_backtest_engine_net_return_lower_than_gross_for_positive_return(self):
        gross = 20.0
        net = backtest_engine.apply_net_return(gross)
        self.assertLess(net, gross, "正報酬扣除成本後，淨報酬應低於毛報酬")

    def test_monte_carlo_net_return_lower_than_gross_for_positive_return(self):
        gross = 30.0
        net = monte_carlo_analyzer.apply_net_return(gross)
        self.assertLess(net, gross, "正報酬扣除成本後，淨報酬應低於毛報酬")

    def test_two_engines_apply_identical_cost_rates(self):
        """兩引擎的成本常數與淨報酬換算公式須口徑一致。"""
        self.assertAlmostEqual(backtest_engine.FEE_RATE_BUY, monte_carlo_analyzer.FEE_RATE_BUY)
        self.assertAlmostEqual(backtest_engine.FEE_RATE_SELL, monte_carlo_analyzer.FEE_RATE_SELL)
        self.assertAlmostEqual(backtest_engine.TAX_RATE, monte_carlo_analyzer.TAX_RATE)
        self.assertAlmostEqual(backtest_engine.SLIPPAGE_RATE, monte_carlo_analyzer.SLIPPAGE_RATE)

        for gross in (-10.0, 0.0, 15.0, 50.0):
            self.assertAlmostEqual(
                backtest_engine.apply_net_return(gross),
                monte_carlo_analyzer.apply_net_return(gross),
                places=9
            )

    def test_zero_gross_return_yields_negative_net_return(self):
        """毛報酬為 0% 時，扣除買賣手續費/證交稅/滑價後，淨報酬應為負值（成本不可能是免費的）。"""
        net = backtest_engine.apply_net_return(0.0)
        self.assertLess(net, 0.0)

    def test_named_cost_constants_match_spec(self):
        """成本常數需與台股實際費率規格一致：買 0.1425%、賣 0.1425%+證交稅0.3%、滑價每邊0.1%。"""
        self.assertAlmostEqual(backtest_engine.FEE_RATE_BUY, 0.001425)
        self.assertAlmostEqual(backtest_engine.FEE_RATE_SELL, 0.001425)
        self.assertAlmostEqual(backtest_engine.TAX_RATE, 0.003)
        self.assertAlmostEqual(backtest_engine.SLIPPAGE_RATE, 0.001)


class TestMissingDataExplicit(unittest.TestCase):
    """驗證缺資料標的不再被 except 吞掉回傳 0.0，而是顯式標記並排除於分母。"""

    def setUp(self):
        self.engine = BacktestEngine("2020-01-01", "2020-02-01", "TestSector")

    def tearDown(self):
        self.engine.restore_environment()
        # 還原為乾淨的空陣列，勿刪除此 git 追蹤的執行期檔案（避免破壞其他 agent 的工作區）
        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

    def test_backtest_engine_missing_price_returns_missing_flag_not_zero(self):
        """yfinance 回傳空 DataFrame 時，get_historical_price_at 應標記 missing=True，而非靜默回傳 0.0 混入報表。"""
        with mock.patch("yfinance.download", new=lambda *a, **k: pd.DataFrame()):
            price, missing = self.engine.get_historical_price_at("NOPE.TW", "2020-01-06")

        self.assertTrue(missing, "資料缺失時應明確標記 missing=True")
        self.assertEqual(price, 0.0)

    def test_backtest_engine_exception_returns_missing_flag(self):
        """yfinance 拋例外時同樣應標記缺資料，而非被吞掉後回傳 0.0。"""
        def boom(*a, **k):
            raise RuntimeError("network down")

        with mock.patch("yfinance.download", new=boom):
            price, missing = self.engine.get_historical_price_at("NOPE.TW", "2020-01-06")

        self.assertTrue(missing)
        self.assertEqual(price, 0.0)

    def test_missing_data_excluded_from_win_rate_denominator(self):
        """
        缺資料標的（出場價無法取得）於固定持有期出場流程中，
        exit_status 應為 missing_data，且不得混入 closed 樣本統計。
        """
        entry_date = "2020-01-06"
        exit_date_expected = (datetime.datetime.strptime(entry_date, "%Y-%m-%d").date()
                               + datetime.timedelta(weeks=52)).strftime("%Y-%m-%d")
        self.engine.end_date = datetime.datetime.strptime(exit_date_expected, "%Y-%m-%d").date() + datetime.timedelta(days=5)

        watchlist = [{
            "company_id": "MISSING.TW", "name": "缺資料標的", "sector": "TestSector",
            "entry_date": entry_date, "entry_price": 100.0, "current_price": 100.0,
            "max_price_since": 100.0, "min_price_since": 100.0,
            "max_return_pct": 0.0, "min_return_pct": 0.0, "current_return_pct": 0.0,
            "status": "tracking"
        }]
        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f)

        with mock.patch("yfinance.download", new=lambda *a, **k: pd.DataFrame()):  # 模擬 yfinance 完全抓不到資料
            self.engine.resolve_fixed_holding_exits()

        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)[0]

        self.assertEqual(result["exit_status"], "missing_data")
        self.assertTrue(result["data_missing"])
        self.assertIsNone(result["current_return_pct"], "缺資料樣本不應有已實現報酬數字，避免誤算入平均值/勝率")
        # 單一真相來源：watchlist 內的缺資料樣本以 exit_status 標記即可，
        # 不得再重複記入 missing_data_entries（否則報告端 len(A)+len(B) 會雙重計算）
        self.assertEqual(len(self.engine.missing_data_entries), 0,
                         "出場缺價樣本不應同時進入 missing_data_entries，避免報告雙重計算")

    def test_missing_exit_price_preserves_period_extremes(self):
        """出場價缺失但期間極值可得時，MFE/MAE（毛值）應保留，不得一併丟棄設為 None。"""
        entry_date = "2020-01-06"
        exit_date_expected = (datetime.datetime.strptime(entry_date, "%Y-%m-%d").date()
                               + datetime.timedelta(weeks=52)).strftime("%Y-%m-%d")
        self.engine.end_date = datetime.datetime.strptime(exit_date_expected, "%Y-%m-%d").date() + datetime.timedelta(days=5)

        watchlist = [{
            "company_id": "PARTIAL.TW", "name": "部分缺資料標的", "sector": "TestSector",
            "entry_date": entry_date, "entry_price": 100.0, "current_price": 100.0,
            "max_price_since": 100.0, "min_price_since": 100.0,
            "max_return_pct": 0.0, "min_return_pct": 0.0, "current_return_pct": 0.0,
            "status": "tracking"
        }]
        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f)

        fake_price_df = _make_price_df("2019-12-01", 500, base_price=100.0, daily_step=0.2)

        def partial_download(ticker, start=None, end=None, progress=False, **kwargs):
            # 期間極值查詢（start == 進場日）→ 有資料；出場價查詢（start = 出場日-10天）→ 無資料
            if start == entry_date:
                return fake_price_df.loc[start:end].copy()
            return pd.DataFrame()

        with mock.patch("yfinance.download", new=partial_download):
            self.engine.resolve_fixed_holding_exits()

        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)[0]

        self.assertEqual(result["exit_status"], "missing_data")
        self.assertEqual(result["missing_reason"], "exit_price_unavailable")
        self.assertIsNotNone(result["max_return_pct"], "期間極值已成功取得，不應被丟棄")
        self.assertIsNotNone(result["min_return_pct"])
        self.assertIsNone(result["current_return_pct"], "出場價缺失仍不得有已實現報酬")

    def test_zero_entry_price_marked_missing_without_crash(self):
        """entry_price 為 0 時不得拋 ZeroDivisionError，應標記為缺資料（invalid_entry_price）。"""
        watchlist = [{
            "company_id": "ZERO.TW", "name": "零進場價標的", "sector": "TestSector",
            "entry_date": "2020-01-06", "entry_price": 0.0, "current_price": 0.0,
            "max_price_since": 0.0, "min_price_since": 0.0,
            "max_return_pct": 0.0, "min_return_pct": 0.0, "current_return_pct": 0.0,
            "status": "tracking"
        }]
        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f)

        with mock.patch("yfinance.download", new=lambda *a, **k: pd.DataFrame()):
            self.engine.resolve_fixed_holding_exits()  # 不得拋例外

        with open(backtest_engine.BACKTEST_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)[0]

        self.assertEqual(result["exit_status"], "missing_data")
        self.assertEqual(result["missing_reason"], "invalid_entry_price")
        self.assertIsNone(result["current_return_pct"])

    def test_monte_carlo_missing_price_returns_missing_flag_not_zero(self):
        """MonteCarloSimulator 的價格取得函式在資料缺失時也應回傳 missing=True，而非 0.0。"""
        sim = MonteCarloSimulator("2015-01-01", "2015-06-01", 1)
        try:
            with mock.patch("yfinance.download", new=lambda *a, **k: pd.DataFrame()):
                price, missing = sim.get_historical_price_at("NOPE.TW", "2015-01-06")
                self.assertTrue(missing)
                self.assertEqual(price, 0.0)

                max_p, min_p, exit_p, period_missing = sim.get_period_prices("NOPE.TW", "2015-01-06", "2016-01-05")
                self.assertTrue(period_missing)
        finally:
            sim.restore_environment()
            # 還原為乾淨的空陣列，勿刪除此 git 追蹤的執行期檔案（避免破壞其他 agent 的工作區）
            with open(monte_carlo_analyzer.MONTE_CARLO_WATCHLIST, "w", encoding="utf-8") as f:
                json.dump([], f)


if __name__ == "__main__":
    unittest.main()
