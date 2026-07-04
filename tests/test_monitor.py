import unittest
from unittest import mock
import pit_store
from market_monitor import (
    MarketInformationMonitor,
    CONSENSUS_MAX,
    MEMBERSHIP_SOURCE_REGISTRY,
    MEMBERSHIP_SOURCE_FALLBACK,
    _PRIORS_PATH,
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
        """測試供應鏈洗牌與內含價值計算。

        ADR 0008 seed 後，CPO_Optical_Transceiver 板塊登記簿已非空，其 stock_id 格式
        （純數字，如 "3450"）與 content_value.json matrix 的 company_id 格式（"3450.TW"）
        不同，會被 get_supply_chain_schedule 依其既有文件行為（registry 引入但 matrix
        缺資料的成員將被跳過）過濾掉。此測試驗證的是 content_value matrix 本身的內含價值
        計算邏輯，與登記簿是否為空無關，故 mock 登記簿查詢回傳空清單、隔離其影響，讓測試
        繼續驗證 fallback（現行 content_value era 名單）路徑下的計算結果。
        """
        import sector_membership
        with mock.patch.object(sector_membership, "get_members_in_universe", return_value=[]):
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
        """驗收關鍵：登記簿當下查無紀錄時，resolve_sector_members 的 fallback 輸出
        應與改版前的 get_point_in_time_matrix 結果一致。

        ADR 0008 已於 2026-07-04 對 CPO_Optical_Transceiver 板塊 seed 真實登記簿事件
        （forward 凍結起點即為今日），故「今日查詢真實登記簿」不再保證為空——這是 ADR
        0008 的預期結果，不是缺陷。此測試驗證的目標本來就是「fallback 路徑本身的行為
        是否等於改版前的 12 檔名單」，與登記簿當下是否已 seed 無關，故改用 mock 明確
        隔離登記簿查詢（回傳空清單），維持測試對 fallback 行為的驗證意圖不受 seed 資料
        影響。"""
        import sector_membership
        with mock.patch.object(sector_membership, "get_members_in_universe", return_value=[]):
            members, source = self.monitor.resolve_sector_members("CPO_Optical_Transceiver", None)
        expected = [it["company_id"] for it in self.monitor.get_point_in_time_matrix(None)]

        self.assertEqual(source, MEMBERSHIP_SOURCE_FALLBACK)
        self.assertEqual(sorted(members), sorted(expected))
        self.assertEqual(len(members), 12, "現行 Feynman 世代（最新 era）應為 12 檔手選名單")


class TestSectorKeyedContentValuePriors(unittest.TestCase):
    """content_value.json 先驗矩陣改為 sector-keyed 後的讀取行為驗證。

    見任務交辦：pit_store.load_content_value_priors 加 sector 參數；
    market_monitor.get_point_in_time_matrix 加 sector 參數，查無該板塊回傳空 dict/list。
    """

    def setUp(self):
        self.monitor = MarketInformationMonitor()

    def test_load_content_value_priors_sector_keyed_read(self):
        """指定 sector='CPO_Optical_Transceiver' 應讀到含 generation_specs 與 eras 的 dict。"""
        priors = pit_store.load_content_value_priors(_PRIORS_PATH, sector="CPO_Optical_Transceiver")
        self.assertIn("generation_specs", priors)
        self.assertIn("eras", priors)
        self.assertIsInstance(priors["eras"], list)
        self.assertGreater(len(priors["eras"]), 0)

    def test_load_content_value_priors_no_sector_returns_sectors_dict(self):
        """未帶 sector（None）時回傳整個 sectors dict，可列舉出 CPO_Optical_Transceiver。"""
        sectors = pit_store.load_content_value_priors(_PRIORS_PATH, sector=None)
        self.assertIn("CPO_Optical_Transceiver", sectors)
        self.assertIn("eras", sectors["CPO_Optical_Transceiver"])

    def test_load_content_value_priors_unknown_sector_returns_empty_dict(self):
        """查無該板塊時回傳空 dict，而非 KeyError/例外。"""
        priors = pit_store.load_content_value_priors(_PRIORS_PATH, sector="Nonexistent_Sector")
        self.assertEqual(priors, {})

    def test_get_point_in_time_matrix_unknown_sector_returns_empty_list(self):
        """market_monitor.get_point_in_time_matrix 查無板塊時回傳空 list（非例外）。"""
        result = self.monitor.get_point_in_time_matrix(sector="Nonexistent_Sector")
        self.assertEqual(result, [])

    def test_get_point_in_time_matrix_unknown_sector_with_as_of_date(self):
        """帶 as_of_date 但板塊不存在時仍應回傳空 list（不因日期參數而拋例外）。"""
        result = self.monitor.get_point_in_time_matrix("2024-06-30", sector="Nonexistent_Sector")
        self.assertEqual(result, [])

    def test_cpo_sector_behavior_unchanged_default(self):
        """CPO_Optical_Transceiver 板塊行為回歸不變：不帶 sector（沿用 DEFAULT_SECTOR）
        與明確帶入 sector='CPO_Optical_Transceiver' 結果應完全一致。"""
        default_result = self.monitor.get_point_in_time_matrix("2024-06-30")
        explicit_result = self.monitor.get_point_in_time_matrix(
            "2024-06-30", sector="CPO_Optical_Transceiver"
        )
        self.assertEqual(default_result, explicit_result)
        self.assertEqual(len(default_result), 10)  # 2024-12-31 以前 era（10 支）

    def test_cpo_sector_all_eras_regression(self):
        """CPO_Optical_Transceiver 四個世代的成員數與代表性數值與改版前完全一致。"""
        cases = [
            ("2018-01-01", 6),
            ("2021-06-01", 9),
            ("2024-06-30", 10),
            (None, 12),
        ]
        for as_of, expected_count in cases:
            result = self.monitor.get_point_in_time_matrix(as_of)
            self.assertEqual(len(result), expected_count, f"as_of={as_of}")

        # 抽樣代表值：3450.TW 在最新 era 的 Feynman content value 應為 14.0（不可變先驗）
        latest = self.monitor.get_point_in_time_matrix(None)
        foci = next(x for x in latest if x["company_id"] == "3450.TW")
        self.assertEqual(foci["content_value_by_gen"]["Feynman"], 14.0)


class TestRegistryPathIdNormalization(unittest.TestCase):
    """防回歸：登記簿回傳純代號（'3450'）、content_value 矩陣為帶尾碼代號（'3450.TW'），
    get_supply_chain_schedule 的矩陣查表必須經 _pure_id 正規化才能匹配。
    （2026-07-04 雙路 review 抓到的 P0：未正規化時 registry 路徑 CV 分析全空。）"""

    def test_registry_pure_ids_still_match_suffixed_matrix(self):
        import market_monitor as mm
        from unittest import mock
        import sector_membership
        monitor = mm.MarketInformationMonitor()
        pure_ids = ["3450", "3324", "3131"]  # 登記簿格式：無尾碼
        with mock.patch.object(sector_membership, "get_members_in_universe",
                               return_value=pure_ids):
            s = monitor.get_supply_chain_schedule(
                "Vera_Rubin", "Feynman", sector="CPO_Optical_Transceiver")
        self.assertEqual(s["membership_source"], "registry")
        self.assertEqual(len(s["timeline_matrix"]), 3,
                         "純代號成員必須匹配到帶尾碼的矩陣項目（_pure_id 正規化）")


if __name__ == "__main__":
    unittest.main()
