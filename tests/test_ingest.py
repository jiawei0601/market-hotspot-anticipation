"""ingest.py 純本地 fixture 測試（無網路依賴）。

涵蓋：
- resolve_yfinance_ticker 三層 fallback（legacy 對照表 / universe type map / raise ValueError）。
- backfill_sector 的成員解析（登記簿全集，不與 universe 交集）與跳過語意
  （已存在快照月由底層 pit_store append-only 鐵律擋下，backfill()/backfill_prices()
  內部 catch SnapshotExistsError 歸入 'skipped'，backfill_sector 沿用不需額外處理）。

網路呼叫（FinMind／yfinance／sector_membership 對 universe 快照的檔案讀取）一律 mock。
"""
import unittest
from unittest.mock import patch

import ingest
import sector_membership


class TestResolveYfinanceTickerLegacy(unittest.TestCase):
    def test_legacy_table_hit(self):
        self.assertEqual(ingest.resolve_yfinance_ticker("3131"), "3131.TWO")
        self.assertEqual(ingest.resolve_yfinance_ticker("3013"), "3013.TW")

    def test_legacy_table_takes_priority_over_type_map(self):
        # 3131 在 legacy 表為 .TWO；即使 type map 說是 twse 也應優先採 legacy。
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.return_value = {"3131": "twse"}
            self.assertEqual(ingest.resolve_yfinance_ticker("3131"), "3131.TWO")
            m.assert_not_called()  # legacy 命中不應打 type map


class TestResolveYfinanceTickerTypeMapFallback(unittest.TestCase):
    def test_twse_maps_to_dot_tw(self):
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.return_value = {"9999": "twse"}
            self.assertEqual(ingest.resolve_yfinance_ticker("9999", as_of="2026-06"), "9999.TW")
            m.assert_called_once_with("2026-06")

    def test_tpex_maps_to_dot_two(self):
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.return_value = {"8888": "tpex"}
            self.assertEqual(ingest.resolve_yfinance_ticker("8888", as_of="2026-06"), "8888.TWO")

    def test_as_of_none_defaults_to_today_month(self):
        import datetime
        expected_ym = datetime.date.today().strftime("%Y-%m")
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.return_value = {"9999": "twse"}
            ingest.resolve_yfinance_ticker("9999")
            m.assert_called_once_with(expected_ym)


class TestResolveYfinanceTickerRaises(unittest.TestCase):
    def test_raises_when_universe_snapshot_not_found(self):
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.side_effect = FileNotFoundError("找不到 universe 快照：2026-06")
            with self.assertRaises(ValueError) as ctx:
                ingest.resolve_yfinance_ticker("9999", as_of="2026-06")
            self.assertIn("9999", str(ctx.exception))

    def test_raises_when_type_map_has_no_entry(self):
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.return_value = {}  # 查無此股
            with self.assertRaises(ValueError) as ctx:
                ingest.resolve_yfinance_ticker("9999", as_of="2026-06")
            self.assertIn("9999", str(ctx.exception))

    def test_raises_when_type_unrecognized(self):
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.return_value = {"9999": "emerging"}  # 非 twse/tpex，無法判斷尾碼
            with self.assertRaises(ValueError):
                ingest.resolve_yfinance_ticker("9999", as_of="2026-06")


class TestFetchMonthPricesUsesResolver(unittest.TestCase):
    def test_fetch_month_prices_raises_via_resolver_when_unresolvable(self):
        with patch.object(sector_membership, "get_universe_type_map") as m:
            m.return_value = {}
            with self.assertRaises(ValueError):
                ingest.fetch_month_prices("9999", as_of="2026-06")


class TestBackfillSectorMemberResolution(unittest.TestCase):
    def test_uses_get_members_full_set_not_universe_intersection(self):
        """backfill_sector 應用 get_members()（登記簿全集），不得用
        get_members_in_universe()（與 universe 交集）——資料層寧多勿少。"""
        with patch.object(sector_membership, "get_members") as m_members, \
             patch.object(sector_membership, "get_members_in_universe") as m_intersect, \
             patch.object(ingest, "backfill") as m_backfill, \
             patch.object(ingest, "backfill_prices") as m_prices, \
             patch.object(ingest, "_finmind_token", return_value=""):
            m_members.return_value = ["1101", "2330"]
            m_backfill.return_value = {"added": [], "skipped_existing": [], "errors": []}
            m_prices.return_value = {"added": [], "skipped_existing": [], "errors": []}

            result = ingest.backfill_sector("CPO", start_month="2024-01", end_month="2024-02")

            m_members.assert_called_once_with("CPO", "2024-02")
            m_intersect.assert_not_called()
            self.assertEqual(result["members"], ["1101", "2330"])
            self.assertEqual(result["sector"], "CPO")
            self.assertEqual(result["as_of"], "2024-02")

    def test_end_month_defaults_to_today(self):
        import datetime
        expected_ym = datetime.date.today().strftime("%Y-%m")
        with patch.object(sector_membership, "get_members") as m_members, \
             patch.object(ingest, "backfill") as m_backfill, \
             patch.object(ingest, "backfill_prices") as m_prices, \
             patch.object(ingest, "_finmind_token", return_value=""):
            m_members.return_value = []
            m_backfill.return_value = {"added": [], "skipped_existing": [], "errors": []}
            m_prices.return_value = {"added": [], "skipped_existing": [], "errors": []}

            result = ingest.backfill_sector("CPO", start_month="2015-01")

            m_members.assert_called_once_with("CPO", expected_ym)
            self.assertEqual(result["as_of"], expected_ym)

    def test_calls_backfill_and_backfill_prices_per_member(self):
        with patch.object(sector_membership, "get_members") as m_members, \
             patch.object(ingest, "backfill") as m_backfill, \
             patch.object(ingest, "backfill_prices") as m_prices, \
             patch.object(ingest, "_finmind_token", return_value="tok123"):
            m_members.return_value = ["1101", "2330"]
            m_backfill.return_value = {"added": ["w1"], "skipped_existing": [], "errors": []}
            m_prices.return_value = {"added": ["p1"], "skipped_existing": [], "errors": []}

            result = ingest.backfill_sector("CPO", start_month="2024-01", end_month="2024-02")

            self.assertEqual(m_backfill.call_count, 2)
            self.assertEqual(m_prices.call_count, 2)
            # 逐檔呼叫：company_ids 應為單一成員的清單
            called_ids = [call.args[0] for call in m_backfill.call_args_list]
            self.assertEqual(called_ids, [["1101"], ["2330"]])
            # token 應傳入 backfill()
            for call in m_backfill.call_args_list:
                self.assertEqual(call.kwargs.get("token"), "tok123")
            self.assertEqual(result["revenue_holdings"]["added"], ["w1", "w1"])
            self.assertEqual(result["prices"]["added"], ["p1", "p1"])


class TestBackfillSectorSkipSemantics(unittest.TestCase):
    def test_existing_company_entry_is_absorbed_as_skipped_existing_by_lower_layer(self):
        """驗證現有行為：backfill()/backfill_prices() 底層改走
        pit_store.append_companies_to_snapshot()，既有 (月, 公司) 條目歸入
        'skipped_existing'、不會向上 raise。backfill_sector 因此不需要自己再包
        一層 try/except。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            # 第一次寫入 revenue/holdings 快照（announce_date/date 皆 <= 2024-01-31 cutoff，
            # 確保 build_revenue_snapshot/build_holding_snapshot 判定為可見）
            with patch.object(ingest, "fetch_month_revenue", return_value=[
                {"stock_id": "1101", "period": "2023-12",
                 "revenue_billion": 1.0, "yoy_pct": None, "announce_date": "2024-01-10"},
            ]), patch.object(ingest, "fetch_foreign_holding", return_value=[
                {"stock_id": "1101", "date": "2024-01-15", "foreign_ratio": 10.0},
            ]), patch("time.sleep", return_value=None):
                res1 = ingest.backfill(["1101"], ["2024-01"], root=tmp)
            self.assertEqual(len(res1["added"]), 2)  # revenue + holdings
            self.assertEqual(res1["skipped_existing"], [])

            # 第二次針對同月同公司重跑：應全部 skipped_existing，不 raise
            with patch.object(ingest, "fetch_month_revenue", return_value=[
                {"stock_id": "1101", "period": "2023-12",
                 "revenue_billion": 1.0, "yoy_pct": None, "announce_date": "2024-01-10"},
            ]), patch.object(ingest, "fetch_foreign_holding", return_value=[
                {"stock_id": "1101", "date": "2024-01-15", "foreign_ratio": 10.0},
            ]), patch("time.sleep", return_value=None):
                res2 = ingest.backfill(["1101"], ["2024-01"], root=tmp)
            self.assertEqual(res2["added"], [])
            self.assertEqual(
                sorted(res2["skipped_existing"]),
                ["2024-01/holdings:1101", "2024-01/revenue:1101"],
            )

    def test_backfill_sector_surfaces_skipped_existing_from_members(self):
        with patch.object(sector_membership, "get_members") as m_members, \
             patch.object(ingest, "backfill") as m_backfill, \
             patch.object(ingest, "backfill_prices") as m_prices, \
             patch.object(ingest, "_finmind_token", return_value=""):
            m_members.return_value = ["1101"]
            m_backfill.return_value = {
                "added": [], "skipped_existing": ["2024-01/revenue:1101"], "errors": [],
            }
            m_prices.return_value = {
                "added": [], "skipped_existing": ["2024-01/prices:1101"], "errors": [],
            }

            result = ingest.backfill_sector("CPO", start_month="2024-01", end_month="2024-01")

            self.assertEqual(
                result["revenue_holdings"]["skipped_existing"], ["2024-01/revenue:1101"]
            )
            self.assertEqual(result["prices"]["skipped_existing"], ["2024-01/prices:1101"])

    def test_new_company_backfilled_into_existing_month_does_not_touch_existing_entry(self):
        """核心場景：既有月檔已有公司 A 的資料，backfill 加入公司 B（新板塊成員）
        時應成功追加，且公司 A 的既有條目完全不變（byte-for-byte）。"""
        import tempfile
        import pit_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ingest, "fetch_month_revenue", return_value=[
                {"stock_id": "1101", "period": "2023-12",
                 "revenue_billion": 1.0, "yoy_pct": None, "announce_date": "2024-01-10"},
            ]), patch.object(ingest, "fetch_foreign_holding", return_value=[
                {"stock_id": "1101", "date": "2024-01-15", "foreign_ratio": 10.0},
            ]), patch("time.sleep", return_value=None):
                ingest.backfill(["1101"], ["2024-01"], root=tmp)

            existing_before = pit_store.read_snapshot("revenue", "2024-01-31", root=tmp)["1101"]

            # 新板塊成員 2308（台達電）補進同一個已存在的月份
            with patch.object(ingest, "fetch_month_revenue", return_value=[
                {"stock_id": "2308", "period": "2023-12",
                 "revenue_billion": 5.0, "yoy_pct": None, "announce_date": "2024-01-10"},
            ]), patch.object(ingest, "fetch_foreign_holding", return_value=[
                {"stock_id": "2308", "date": "2024-01-15", "foreign_ratio": 50.0},
            ]), patch("time.sleep", return_value=None):
                res = ingest.backfill(["2308"], ["2024-01"], root=tmp)

            self.assertEqual(
                sorted(res["added"]), ["2024-01/holdings:2308", "2024-01/revenue:2308"]
            )
            self.assertEqual(res["skipped_existing"], [])

            rev_after = pit_store.read_snapshot("revenue", "2024-01-31", root=tmp)
            hold_after = pit_store.read_snapshot("holdings", "2024-01-31", root=tmp)
            self.assertEqual(rev_after["1101"], existing_before)  # 既有條目 byte 不變
            self.assertIn("2308", rev_after)
            self.assertIn("2308", hold_after)


class TestMonthRangeInclusive(unittest.TestCase):
    def test_single_month(self):
        self.assertEqual(ingest._month_range_inclusive("2024-01", "2024-01"), ["2024-01"])

    def test_spans_year_boundary(self):
        self.assertEqual(
            ingest._month_range_inclusive("2023-11", "2024-02"),
            ["2023-11", "2023-12", "2024-01", "2024-02"],
        )


class TestAppendCompaniesToSnapshot(unittest.TestCase):
    """pit_store.append_companies_to_snapshot：「(月, 公司) 級」不可變粒度鐵律。"""

    def test_month_file_absent_creates_full_file(self):
        import tempfile
        import pit_store

        with tempfile.TemporaryDirectory() as tmp:
            result = pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"1101": {"revenue_billion": 1.0}}, root=tmp
            )
            self.assertEqual(result, {"added": ["1101"], "skipped_existing": []})
            snap = pit_store.read_snapshot("revenue", "2024-01-31", root=tmp)
            self.assertEqual(snap, {"1101": {"revenue_billion": 1.0}})

    def test_append_new_company_to_existing_month_leaves_existing_entry_untouched(self):
        import tempfile
        import pit_store

        with tempfile.TemporaryDirectory() as tmp:
            pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"1101": {"revenue_billion": 1.0}}, root=tmp
            )
            result = pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"2308": {"revenue_billion": 5.0}}, root=tmp
            )
            self.assertEqual(result, {"added": ["2308"], "skipped_existing": []})
            snap = pit_store.read_snapshot("revenue", "2024-01-31", root=tmp)
            self.assertEqual(snap["1101"], {"revenue_billion": 1.0})  # 既有條目 byte 不變
            self.assertEqual(snap["2308"], {"revenue_billion": 5.0})

    def test_rerun_is_idempotent(self):
        import tempfile
        import pit_store

        with tempfile.TemporaryDirectory() as tmp:
            pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"1101": {"revenue_billion": 1.0}}, root=tmp
            )
            result = pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"1101": {"revenue_billion": 1.0}}, root=tmp
            )
            self.assertEqual(result, {"added": [], "skipped_existing": ["1101"]})
            snap = pit_store.read_snapshot("revenue", "2024-01-31", root=tmp)
            self.assertEqual(snap, {"1101": {"revenue_billion": 1.0}})  # 未改變

    def test_attempt_to_overwrite_existing_key_is_rejected(self):
        """企圖用不同內容覆蓋既有 key：拒絕覆寫，列入 skipped_existing，既有值不變。"""
        import tempfile
        import pit_store

        with tempfile.TemporaryDirectory() as tmp:
            pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"1101": {"revenue_billion": 1.0}}, root=tmp
            )
            result = pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"1101": {"revenue_billion": 999.0}}, root=tmp
            )
            self.assertEqual(result, {"added": [], "skipped_existing": ["1101"]})
            snap = pit_store.read_snapshot("revenue", "2024-01-31", root=tmp)
            self.assertEqual(snap["1101"], {"revenue_billion": 1.0})  # 原值不被覆蓋

    def test_mixed_added_and_skipped_existing_in_one_call(self):
        import tempfile
        import pit_store

        with tempfile.TemporaryDirectory() as tmp:
            pit_store.append_companies_to_snapshot(
                "2024-01", "revenue", {"1101": {"revenue_billion": 1.0}}, root=tmp
            )
            result = pit_store.append_companies_to_snapshot(
                "2024-01", "revenue",
                {"1101": {"revenue_billion": 999.0}, "2308": {"revenue_billion": 5.0}},
                root=tmp,
            )
            self.assertEqual(result, {"added": ["2308"], "skipped_existing": ["1101"]})
            snap = pit_store.read_snapshot("revenue", "2024-01-31", root=tmp)
            self.assertEqual(snap["1101"], {"revenue_billion": 1.0})
            self.assertEqual(snap["2308"], {"revenue_billion": 5.0})


if __name__ == "__main__":
    unittest.main()
