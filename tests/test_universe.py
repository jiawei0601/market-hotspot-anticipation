"""universe.py 純本地 fixture 測試（無網路依賴）。

涵蓋：三規則（上市時長／流動性／產業分類）各自的通過與剔除案例、
快照 append-only 不可變鐵律、build_snapshot 用 fake fetcher 組裝全流程。
"""
import os
import tempfile
import unittest

import pit_store
import universe


class TestPassesListingLength(unittest.TestCase):
    def test_pass_exactly_min_months(self):
        # 2025-06 到 2026-06 剛好 12 個月差
        self.assertTrue(universe.passes_listing_length("2025-06", "2026-06"))

    def test_pass_more_than_min_months(self):
        self.assertTrue(universe.passes_listing_length("2015-01", "2026-06"))

    def test_fail_fewer_than_min_months(self):
        # 只差 6 個月，不足 12
        self.assertFalse(universe.passes_listing_length("2026-01", "2026-06"))

    def test_fail_none_first_price_month(self):
        self.assertFalse(universe.passes_listing_length(None, "2026-06"))


class TestPassesListingLengthByProbe(unittest.TestCase):
    def test_pass_when_existed_at_probe(self):
        self.assertTrue(universe.passes_listing_length_by_probe(True))

    def test_fail_when_absent_at_probe(self):
        self.assertFalse(universe.passes_listing_length_by_probe(False))

    def test_fail_when_probe_data_missing(self):
        self.assertFalse(universe.passes_listing_length_by_probe(None))


class TestPassesLiquidity(unittest.TestCase):
    def test_pass_all_three_months_above_floor(self):
        turnovers = [20_000_000, 16_000_000, 15_000_000]
        self.assertTrue(universe.passes_liquidity(turnovers))

    def test_fail_one_month_below_floor(self):
        turnovers = [20_000_000, 10_000_000, 15_000_000]
        self.assertFalse(universe.passes_liquidity(turnovers))

    def test_fail_one_month_missing(self):
        turnovers = [20_000_000, None, 15_000_000]
        self.assertFalse(universe.passes_liquidity(turnovers))

    def test_fail_fewer_than_three_months(self):
        turnovers = [20_000_000, 16_000_000]
        self.assertFalse(universe.passes_liquidity(turnovers))

    def test_boundary_exactly_at_floor_passes(self):
        turnovers = [universe.MONTH_END_TURNOVER_FLOOR] * 3
        self.assertTrue(universe.passes_liquidity(turnovers))


class TestPassesIndustry(unittest.TestCase):
    def test_pass_allowed_category(self):
        self.assertTrue(universe.passes_industry("半導體業"))
        self.assertTrue(universe.passes_industry("電子零組件業"))

    def test_fail_disallowed_category(self):
        self.assertFalse(universe.passes_industry("金融保險"))
        self.assertFalse(universe.passes_industry("食品工業"))

    def test_pass_coarse_category_electronics(self):
        # 粗分類「電子工業」為 2026-07-04 pre-registration 修正後納入
        # （TaiwanStockInfo 對部分上市電子股掛粗分類而非細分類，見 ADR 0007 修正紀錄）
        self.assertTrue(universe.passes_industry("電子工業"))

    def test_pass_tpex_lei_suffix_variant(self):
        # TPEx 上櫃側「類」字尾變體：「其他電子類」對應上市側「其他電子業」，
        # 為 2026-07-04 第二筆 pre-registration 修正（弘塑/萬潤/雙鴻誤剔除的根因）
        self.assertTrue(universe.passes_industry("其他電子類"))

    def test_fail_electronics_adjacent_but_excluded(self):
        # 刻意不納入的電子相關字串（軟體/雲服務/電商/傳統電工，非電子供應鏈硬體）
        self.assertFalse(universe.passes_industry("資訊服務業"))
        self.assertFalse(universe.passes_industry("數位雲端類"))
        self.assertFalse(universe.passes_industry("電子商務業"))
        self.assertFalse(universe.passes_industry("電器電纜"))

    def test_pass_v3_data_driven_expansion_categories(self):
        # 0007-v3：枚舉 data/sector_membership/ 全部板塊成員的 industry_category 後
        # 資料驅動擴充納入的 7 類（見 ADR 0007 修正紀錄三、universe.py INDUSTRY_ALLOWED docstring）。
        # 觸發股：其他(6803崑鼎/8390金益鼎/9955佳龍)、創新板股票(7610聯友金屬-創)、
        # 綠能環保類(6894衛司特)——皆屬 Semiconductor_Materials_Recycling；
        # 塑膠工業(1301/1303/1312/1326)、水泥工業(1101/1102/1103/1104/1108)、
        # 油電燃氣業(6505台塑化)、化學工業(1714和桐)——皆屬 Traditional_Recovery。
        self.assertTrue(universe.passes_industry("其他"))
        self.assertTrue(universe.passes_industry("創新板股票"))
        self.assertTrue(universe.passes_industry("綠能環保類"))
        self.assertTrue(universe.passes_industry("塑膠工業"))
        self.assertTrue(universe.passes_industry("水泥工業"))
        self.assertTrue(universe.passes_industry("油電燃氣業"))
        self.assertTrue(universe.passes_industry("化學工業"))

    def test_fail_none_category(self):
        self.assertFalse(universe.passes_industry(None))

    def test_rules_version_is_v3(self):
        # 0007-v3：資料驅動擴充允許清單以涵蓋登記簿板塊成員，同步升版供快照追溯與重建政策判定
        self.assertEqual(universe.RULES_VERSION, "0007-v3")


class TestHelperDateMath(unittest.TestCase):
    def test_months_before(self):
        self.assertEqual(universe.months_before("2026-06", 12), "2025-06")
        self.assertEqual(universe.months_before("2026-01", 1), "2025-12")

    def test_prev_year_months(self):
        self.assertEqual(
            universe._prev_year_months("2026-06", 3),
            ["2026-04", "2026-05", "2026-06"],
        )

    def test_latest_closed_month(self):
        import datetime
        self.assertEqual(
            universe._latest_closed_month(datetime.date(2026, 7, 4)),
            "2026-06",
        )
        self.assertEqual(
            universe._latest_closed_month(datetime.date(2026, 1, 15)),
            "2025-12",
        )

    def test_month_range(self):
        self.assertEqual(
            universe._month_range("2026-01", "2026-03"),
            ["2026-01", "2026-02", "2026-03"],
        )


class TestBuildUniversePool(unittest.TestCase):
    def test_excludes_emerging_and_dedupes(self):
        rows = [
            {"stock_id": "1101", "stock_name": "台泥", "type": "twse", "industry_category": "水泥工業"},
            {"stock_id": "1101", "stock_name": "台泥dup", "type": "twse", "industry_category": "水泥工業"},
            {"stock_id": "9999", "stock_name": "興櫃股", "type": "emerging", "industry_category": "半導體業"},
            {"stock_id": "3131", "stock_name": "弘塑", "type": "tpex", "industry_category": "其他電子類"},
        ]
        pool = universe.build_universe_pool(rows)
        self.assertEqual(set(pool.keys()), {"1101", "3131"})
        self.assertEqual(pool["1101"]["name"], "台泥")  # 取第一筆


class TestBuildSnapshotFakeFetchers(unittest.TestCase):
    """純本地 fixture，不打任何網路：用 fake fetcher 注入固定資料，驗證三層漏斗全流程。"""

    def setUp(self):
        self.as_of = "2026-06"
        self.stock_info_rows = [
            # 通過全部三規則：上市股，半導體業，近3月流動性皆達標，探測點存在
            {"stock_id": "1000", "stock_name": "全通過上市股", "type": "twse", "industry_category": "半導體業"},
            # 上市股但產業不在允許清單
            {"stock_id": "1001", "stock_name": "產業不符上市股", "type": "twse", "industry_category": "金融保險"},
            # 上市股但流動性不足（近3月其中一月過低）
            {"stock_id": "1002", "stock_name": "流動性不足上市股", "type": "twse", "industry_category": "半導體業"},
            # 上市股但上市時長不足（探測點不存在）
            {"stock_id": "1003", "stock_name": "新股上市股", "type": "twse", "industry_category": "半導體業"},
            # 上櫃股，全通過
            {"stock_id": "2000", "stock_name": "全通過上櫃股", "type": "tpex", "industry_category": "電子零組件業"},
            # 興櫃股，母體排除
            {"stock_id": "3000", "stock_name": "興櫃股", "type": "emerging", "industry_category": "半導體業"},
        ]
        self.delisted = {}

        recent_3 = universe._prev_year_months(self.as_of, 3)
        self.recent_3 = recent_3
        probe_month = universe.months_before(self.as_of, universe.MIN_LISTING_MONTHS)
        self.probe_month = probe_month

        floor = universe.MONTH_END_TURNOVER_FLOOR
        # TWSE 月底行情：{year_month: {stock_id: turnover}}
        self.twse_by_month = {
            recent_3[0]: {"1000": floor + 1, "1001": floor + 1, "1002": floor + 1, "1003": floor + 1},
            recent_3[1]: {"1000": floor + 1, "1001": floor + 1, "1002": floor - 1, "1003": floor + 1},
            recent_3[2]: {"1000": floor + 1, "1001": floor + 1, "1002": floor + 1, "1003": floor + 1},
            probe_month: {"1000": floor + 1, "1001": floor + 1, "1002": floor + 1},  # 1003 探測點不存在=新股
        }

        # FinMind 上櫃股逐檔行情（2000 全通過）
        self.tpex_rows = {
            "2000": [
                {"date": f"{probe_month}-15", "Trading_money": floor + 1},
                {"date": f"{recent_3[0]}-28", "Trading_money": floor + 1},
                {"date": f"{recent_3[1]}-27", "Trading_money": floor + 1},
                {"date": f"{recent_3[2]}-30", "Trading_money": floor + 1},
            ],
        }

    def _twse_turnover_fetcher(self, year_month):
        return self.twse_by_month.get(year_month, {})

    def _price_history_fetcher(self, stock_id, start_date, end_date):
        return self.tpex_rows.get(stock_id, [])

    def test_full_funnel_counts_and_membership(self):
        snap = universe.build_snapshot(
            self.as_of,
            stock_info_rows=self.stock_info_rows,
            delisted=self.delisted,
            price_history_fetcher=self._price_history_fetcher,
            twse_turnover_fetcher=self._twse_turnover_fetcher,
        )
        self.assertEqual(snap["as_of"], self.as_of)
        self.assertEqual(snap["rules_version"], universe.RULES_VERSION)
        self.assertEqual(snap["pool_count"], 5)  # 排除 emerging 的 3000

        # 規則1：1003（新股）被剔除 -> 4 檔通過
        self.assertEqual(snap["rule1_listing_length_count"], 4)

        # 規則2：1002（流動性不足）再被剔除 -> 3 檔通過
        self.assertEqual(snap["rule2_liquidity_count"], 3)

        # 規則3：1001（產業不符）再被剔除 -> 2 檔最終通過（1000, 2000）
        self.assertEqual(snap["rule3_industry_count"], 2)
        self.assertEqual(snap["final_pass"], ["1000", "2000"])

        # 每檔紀錄欄位完整
        rec = snap["records"]["1000"]
        for field in ("stock_id", "name", "type", "industry", "month_end_turnover",
                      "first_price_month", "delisted"):
            self.assertIn(field, rec)
        self.assertFalse(rec["delisted"])

    def test_delisted_flag_recorded(self):
        delisted = {"1000": "2020-01-01"}
        snap = universe.build_snapshot(
            self.as_of,
            stock_info_rows=self.stock_info_rows,
            delisted=delisted,
            price_history_fetcher=self._price_history_fetcher,
            twse_turnover_fetcher=self._twse_turnover_fetcher,
        )
        self.assertTrue(snap["records"]["1000"]["delisted"])
        self.assertFalse(snap["records"]["2000"]["delisted"])

    def test_tpex_fetch_error_does_not_abort_batch(self):
        """單檔（上櫃股）抓取失敗（如 FinMind 限流）不可讓整批 build_snapshot 中止，
        應顯式記錄 fetch_error，該檔不計入任何規則通過，其餘檔案正常組裝。"""
        def failing_fetcher(stock_id, start_date, end_date):
            if stock_id == "2000":
                raise RuntimeError("HTTP Error 402: Payment Required")
            return self._price_history_fetcher(stock_id, start_date, end_date)

        snap = universe.build_snapshot(
            self.as_of,
            stock_info_rows=self.stock_info_rows,
            delisted=self.delisted,
            price_history_fetcher=failing_fetcher,
            twse_turnover_fetcher=self._twse_turnover_fetcher,
        )
        # 整批仍正常組裝完成（不拋例外中止）
        self.assertEqual(snap["pool_count"], 5)
        # 2000 因抓取失敗被排除於 final_pass，且顯式記錄在 fetch_errors
        self.assertNotIn("2000", snap["final_pass"])
        self.assertEqual(snap["fetch_error_count"], 1)
        self.assertIn("2000", snap["fetch_errors"])
        self.assertIn("402", snap["fetch_errors"]["2000"])
        # 其餘檔案（如 1000 上市股）不受影響，正常判斷
        self.assertIn("1000", snap["final_pass"])
        # 2000 的紀錄仍存在，但欄位顯式標記為缺值而非捏造
        rec = snap["records"]["2000"]
        self.assertIn("fetch_error", rec)
        self.assertIsNone(rec["first_price_month"])


class TestSnapshotImmutability(unittest.TestCase):
    def test_write_snapshot_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp_root:
            payload = {"as_of": "2026-06", "rules_version": universe.RULES_VERSION, "final_pass": []}
            path = pit_store.write_monthly_snapshot("universe", payload, year_month="2026-06", root=tmp_root)
            self.assertTrue(os.path.exists(path))

            with self.assertRaises(pit_store.SnapshotExistsError):
                pit_store.write_monthly_snapshot("universe", payload, year_month="2026-06", root=tmp_root)

    def test_read_back_via_pit_store(self):
        with tempfile.TemporaryDirectory() as tmp_root:
            payload = {"as_of": "2026-06", "rules_version": universe.RULES_VERSION, "final_pass": ["1000"]}
            pit_store.write_monthly_snapshot("universe", payload, year_month="2026-06", root=tmp_root)
            result = pit_store.read_snapshot("universe", as_of_date="2026-06-30", root=tmp_root)
            self.assertEqual(result, payload)


class TestProvisionalPolicy(unittest.TestCase):
    """快照重建政策（ADR 0007）：provisional（含 fetch_error）快照允許重建，完整快照不可覆寫。"""

    def _payload(self, fetch_error_count=0, provisional=None):
        p = {
            "as_of": "2026-06",
            "rules_version": universe.RULES_VERSION,
            "final_pass": [],
            "fetch_error_count": fetch_error_count,
            "fetch_errors": {},
        }
        if provisional is not None:
            p["provisional"] = provisional
        return p

    def test_snapshot_is_provisional_by_flag(self):
        self.assertTrue(universe.snapshot_is_provisional(self._payload(provisional=True)))

    def test_snapshot_is_provisional_by_fetch_error_count(self):
        # 相容早期未寫 provisional 欄位、但含缺值的快照（如 2026-06 首次實跑 850 缺值）
        self.assertTrue(universe.snapshot_is_provisional(self._payload(fetch_error_count=850)))

    def test_snapshot_is_not_provisional_when_clean(self):
        self.assertFalse(universe.snapshot_is_provisional(self._payload(fetch_error_count=0)))

    def test_build_snapshot_sets_provisional_flag(self):
        """有 fetch_error → provisional=True；無 → provisional=False。"""
        base = TestBuildSnapshotFakeFetchers("test_full_funnel_counts_and_membership")
        base.setUp()

        clean = universe.build_snapshot(
            base.as_of,
            stock_info_rows=base.stock_info_rows,
            delisted=base.delisted,
            price_history_fetcher=base._price_history_fetcher,
            twse_turnover_fetcher=base._twse_turnover_fetcher,
        )
        self.assertFalse(clean["provisional"])

        def failing_fetcher(stock_id, start_date, end_date):
            raise RuntimeError("HTTP Error 402: Payment Required")

        dirty = universe.build_snapshot(
            base.as_of,
            stock_info_rows=base.stock_info_rows,
            delisted=base.delisted,
            price_history_fetcher=failing_fetcher,
            twse_turnover_fetcher=base._twse_turnover_fetcher,
        )
        self.assertTrue(dirty["provisional"])

    def test_write_snapshot_allows_rebuild_of_provisional(self):
        with tempfile.TemporaryDirectory() as tmp_root:
            prov = self._payload(fetch_error_count=3, provisional=True)
            universe.write_snapshot("2026-06", snapshot=prov, root=tmp_root)

            clean = self._payload(fetch_error_count=0, provisional=False)
            path = universe.write_snapshot("2026-06", snapshot=clean, root=tmp_root)

            import json
            with open(path, encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertFalse(on_disk["provisional"])
            self.assertEqual(on_disk["fetch_error_count"], 0)

    def test_write_snapshot_rejects_rebuild_of_complete(self):
        with tempfile.TemporaryDirectory() as tmp_root:
            clean = self._payload(fetch_error_count=0, provisional=False)
            universe.write_snapshot("2026-06", snapshot=clean, root=tmp_root)

            with self.assertRaises(pit_store.SnapshotExistsError):
                universe.write_snapshot("2026-06", snapshot=self._payload(), root=tmp_root)

    # ---- rules_version 重建政策（0007-v1 → 0007-v2 等 pre-registration 規則修訂） ----

    def test_rebuildable_when_rules_version_outdated(self):
        outdated = self._payload(fetch_error_count=0, provisional=False)
        outdated["rules_version"] = "0007-v1"
        self.assertTrue(universe.snapshot_is_rebuildable(outdated))

    def test_not_rebuildable_when_same_version_and_complete(self):
        current = self._payload(fetch_error_count=0, provisional=False)
        self.assertFalse(universe.snapshot_is_rebuildable(current))

    def test_rebuildable_when_provisional_even_if_same_version(self):
        prov = self._payload(fetch_error_count=5, provisional=True)
        self.assertTrue(universe.snapshot_is_rebuildable(prov))

    def test_write_snapshot_allows_rebuild_of_outdated_version(self):
        """版本過時（如 0007-v1）且完整的快照，允許重建為當前版本。"""
        with tempfile.TemporaryDirectory() as tmp_root:
            old = self._payload(fetch_error_count=0, provisional=False)
            old["rules_version"] = "0007-v1"
            universe.write_snapshot("2026-06", snapshot=old, root=tmp_root)

            new = self._payload(fetch_error_count=0, provisional=False)
            path = universe.write_snapshot("2026-06", snapshot=new, root=tmp_root)

            import json
            with open(path, encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk["rules_version"], universe.RULES_VERSION)


class TestRateLimitRetry(unittest.TestCase):
    """限流韌性：402/403 指數退避（60s→900s→900s）與 --paced 每小時窗口模式。
    用 fake opener + monkeypatch universe._sleep 免除真實等待與網路。"""

    def setUp(self):
        self._orig_sleep = universe._sleep
        self.sleep_calls = []
        universe._sleep = lambda s: self.sleep_calls.append(s)

    def tearDown(self):
        universe._sleep = self._orig_sleep
        universe.set_paced_mode(False)

    @staticmethod
    def _http_error(code):
        import urllib.error
        return urllib.error.HTTPError("http://fake", code, "msg", None, None)

    def test_backoff_retries_then_succeeds(self):
        attempts = {"n": 0}

        def opener(url, timeout):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise self._http_error(402)
            return {"data": [{"date": "2026-06-30"}]}

        result = universe._open_json_with_retry("http://fake", opener=opener)
        self.assertEqual(result["data"][0]["date"], "2026-06-30")
        # 前兩次失敗 → 退避 60s、900s
        self.assertEqual(self.sleep_calls, [60, 900])

    def test_backoff_exhausted_raises(self):
        def opener(url, timeout):
            raise self._http_error(402)

        import urllib.error
        with self.assertRaises(urllib.error.HTTPError):
            universe._open_json_with_retry("http://fake", opener=opener)
        # 3 輪退避（60, 900, 900）全部耗盡後才拋出
        self.assertEqual(self.sleep_calls, [60, 900, 900])

    def test_non_rate_limit_error_raises_immediately(self):
        def opener(url, timeout):
            raise self._http_error(500)

        import urllib.error
        with self.assertRaises(urllib.error.HTTPError):
            universe._open_json_with_retry("http://fake", opener=opener)
        self.assertEqual(self.sleep_calls, [])  # 不重試、不等待（fail loud）

    def test_403_also_triggers_backoff(self):
        attempts = {"n": 0}

        def opener(url, timeout):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise self._http_error(403)
            return {"data": []}

        universe._open_json_with_retry("http://fake", opener=opener)
        self.assertEqual(self.sleep_calls, [60])

    def test_paced_mode_sleeps_to_next_hour(self):
        universe.set_paced_mode(True)
        attempts = {"n": 0}

        def opener(url, timeout):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise self._http_error(402)
            return {"data": []}

        universe._open_json_with_retry("http://fake", opener=opener)
        # paced 模式：每次限流睡到下個整點（秒數 1~3630 之間），非固定退避值
        self.assertEqual(len(self.sleep_calls), 2)
        for s in self.sleep_calls:
            self.assertGreaterEqual(s, 1)
            self.assertLessEqual(s, 3660)

    def test_seconds_until_next_hour(self):
        import datetime
        now = datetime.datetime(2026, 7, 4, 10, 30, 0)
        secs = universe._seconds_until_next_hour(now)
        # 10:30:00 → 11:00:30 = 1830 秒
        self.assertEqual(secs, 1830.0)


if __name__ == "__main__":
    unittest.main()
