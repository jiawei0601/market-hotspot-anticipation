"""sector_membership.py 純本地 fixture 測試（無網路依賴）。

涵蓋：add/remove 時序、"YYYY-MM" 月底語意、effective_from < evidence_date 拒絕、
append-only 防竄改、與 universe 快照的交集、快照回溯 3 個月、type map。
"""
import json
import os
import tempfile
import unittest

import sector_membership as sm


class TestNormalizeAsOf(unittest.TestCase):
    def test_year_month_becomes_last_day(self):
        self.assertEqual(sm._normalize_as_of("2026-02"), "2026-02-28")
        self.assertEqual(sm._normalize_as_of("2024-02"), "2024-02-29")  # 閏年
        self.assertEqual(sm._normalize_as_of("2026-01"), "2026-01-31")
        self.assertEqual(sm._normalize_as_of("2026-04"), "2026-04-30")

    def test_full_date_passthrough(self):
        self.assertEqual(sm._normalize_as_of("2026-02-15"), "2026-02-15")


class TestAddEventValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_then_read_back(self):
        sm.add_event(
            sector="CPO", stock_id="3450", action="add",
            evidence_grade="E1", evidence_desc="法說會揭露",
            evidence_url="https://example.com/1",
            evidence_date="2025-01-10", effective_from="2025-01-10",
            segment="equipment", root=self.root,
        )
        events = sm._load_events("CPO", root=self.root)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["stock_id"], "3450")
        self.assertEqual(events[0]["action"], "add")
        self.assertEqual(events[0]["segment"], "equipment")
        self.assertEqual(events[0]["recorded_at"], events[0]["recorded_at"])  # 有值即可

    def test_recorded_at_defaults_to_today(self):
        import datetime
        sm.add_event(
            sector="CPO", stock_id="3450", action="add",
            evidence_grade="E1", evidence_desc="d", evidence_url="u",
            evidence_date="2025-01-10", effective_from="2025-01-10",
            root=self.root,
        )
        events = sm._load_events("CPO", root=self.root)
        self.assertEqual(events[0]["recorded_at"], datetime.date.today().strftime("%Y-%m-%d"))

    def test_reject_effective_from_before_evidence_date(self):
        with self.assertRaises(sm.MembershipIntegrityError):
            sm.add_event(
                sector="CPO", stock_id="3450", action="add",
                evidence_grade="E1", evidence_desc="d", evidence_url="u",
                evidence_date="2025-06-01", effective_from="2025-01-01",
                root=self.root,
            )
        # 驗證失敗不寫入任何內容
        self.assertEqual(sm._load_events("CPO", root=self.root), [])

    def test_effective_from_equal_to_evidence_date_ok(self):
        sm.add_event(
            sector="CPO", stock_id="3450", action="add",
            evidence_grade="E2", evidence_desc="d", evidence_url="u",
            evidence_date="2025-06-01", effective_from="2025-06-01",
            root=self.root,
        )
        self.assertEqual(len(sm._load_events("CPO", root=self.root)), 1)

    def test_reject_invalid_action(self):
        with self.assertRaises(sm.MembershipIntegrityError):
            sm.add_event(
                sector="CPO", stock_id="3450", action="rename",
                evidence_grade="E1", evidence_desc="d", evidence_url="u",
                evidence_date="2025-01-01", effective_from="2025-01-01",
                root=self.root,
            )

    def test_reject_invalid_evidence_grade(self):
        with self.assertRaises(sm.MembershipIntegrityError):
            sm.add_event(
                sector="CPO", stock_id="3450", action="add",
                evidence_grade="E4", evidence_desc="d", evidence_url="u",
                evidence_date="2025-01-01", effective_from="2025-01-01",
                root=self.root,
            )

    def test_reject_invalid_segment(self):
        with self.assertRaises(sm.MembershipIntegrityError):
            sm.add_event(
                sector="CPO", stock_id="3450", action="add",
                evidence_grade="E1", evidence_desc="d", evidence_url="u",
                evidence_date="2025-01-01", effective_from="2025-01-01",
                segment="upstream", root=self.root,
            )

    def test_reject_malformed_date(self):
        with self.assertRaises(sm.MembershipIntegrityError):
            sm.add_event(
                sector="CPO", stock_id="3450", action="add",
                evidence_grade="E1", evidence_desc="d", evidence_url="u",
                evidence_date="2025/01/01", effective_from="2025-01-01",
                root=self.root,
            )


class TestAppendOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_add_appends_not_overwrites(self):
        sm.add_event(
            sector="CPO", stock_id="3450", action="add",
            evidence_grade="E1", evidence_desc="first", evidence_url="u",
            evidence_date="2025-01-01", effective_from="2025-01-01",
            root=self.root,
        )
        sm.add_event(
            sector="CPO", stock_id="6223", action="add",
            evidence_grade="E2", evidence_desc="second", evidence_url="u",
            evidence_date="2025-02-01", effective_from="2025-02-01",
            root=self.root,
        )
        events = sm._load_events("CPO", root=self.root)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["evidence_desc"], "first")
        self.assertEqual(events[1]["evidence_desc"], "second")

    def test_correcting_a_mistake_uses_new_remove_event_not_mutation(self):
        # 錯誤判斷後的「撤銷」應該是新增 remove 事件，不是回頭改掉原 add 事件
        sm.add_event(
            sector="CPO", stock_id="9999", action="add",
            evidence_grade="E3", evidence_desc="誤判", evidence_url="u",
            evidence_date="2025-01-01", effective_from="2025-01-01",
            root=self.root,
        )
        sm.add_event(
            sector="CPO", stock_id="9999", action="remove",
            evidence_grade="E1", evidence_desc="撤銷：證據不成立", evidence_url="u",
            evidence_date="2025-03-01", effective_from="2025-03-01",
            root=self.root,
        )
        events = sm._load_events("CPO", root=self.root)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["action"], "add")  # 原事件未被竄改
        self.assertEqual(events[0]["evidence_desc"], "誤判")
        self.assertEqual(events[1]["action"], "remove")
        # 誤判期間（2025-01 ~ 2025-02）仍應忠實反映當時判斷
        self.assertIn("9999", sm.get_members("CPO", "2025-02", root=self.root))
        self.assertNotIn("9999", sm.get_members("CPO", "2025-03", root=self.root))


class TestGetMembersTimeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        # 3450 於 2025-01 加入，2025-06 移出；6223 於 2025-03 加入，持續至今
        sm.add_event(sector="CPO", stock_id="3450", action="add",
                     evidence_grade="E1", evidence_desc="d1", evidence_url="u",
                     evidence_date="2025-01-01", effective_from="2025-01-01",
                     segment="equipment", root=self.root)
        sm.add_event(sector="CPO", stock_id="6223", action="add",
                     evidence_grade="E2", evidence_desc="d2", evidence_url="u",
                     evidence_date="2025-03-01", effective_from="2025-03-01",
                     segment="component", root=self.root)
        sm.add_event(sector="CPO", stock_id="3450", action="remove",
                     evidence_grade="E1", evidence_desc="d3", evidence_url="u",
                     evidence_date="2025-06-01", effective_from="2025-06-01",
                     root=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_before_any_event_empty(self):
        self.assertEqual(sm.get_members("CPO", "2024-12", root=self.root), [])

    def test_after_first_add_only_3450(self):
        self.assertEqual(sm.get_members("CPO", "2025-02", root=self.root), ["3450"])

    def test_after_second_add_both(self):
        self.assertEqual(sm.get_members("CPO", "2025-04", root=self.root), ["3450", "6223"])

    def test_after_remove_only_6223(self):
        self.assertEqual(sm.get_members("CPO", "2025-07", root=self.root), ["6223"])

    def test_exact_effective_from_day_included(self):
        # effective_from 當天即生效（<=，非 <）
        self.assertEqual(sm.get_members("CPO", "2025-06-01", root=self.root), ["6223"])

    def test_year_month_boundary_semantics(self):
        # "2025-05" 應視為 2025-05-31，此時尚未移出
        self.assertIn("3450", sm.get_members("CPO", "2025-05", root=self.root))
        # "2025-06" 視為 2025-06-30，已移出
        self.assertNotIn("3450", sm.get_members("CPO", "2025-06", root=self.root))

    def test_nonexistent_sector_returns_empty(self):
        self.assertEqual(sm.get_members("NoSuchSector", "2025-12", root=self.root), [])

    def test_get_member_segments(self):
        segs = sm.get_member_segments("CPO", "2025-04", root=self.root)
        self.assertEqual(segs, {"3450": "equipment", "6223": "component"})

    def test_get_member_segments_excludes_removed(self):
        segs = sm.get_member_segments("CPO", "2025-07", root=self.root)
        self.assertEqual(segs, {"6223": "component"})

    def test_get_member_segments_takes_latest_effective_from(self):
        sm.add_event(sector="CPO", stock_id="6223", action="add",
                     evidence_grade="E1", evidence_desc="segment 修正",
                     evidence_url="u", evidence_date="2025-05-01",
                     effective_from="2025-05-01", segment="downstream",
                     root=self.root)
        segs = sm.get_member_segments("CPO", "2025-07", root=self.root)
        self.assertEqual(segs["6223"], "downstream")


def _write_fake_universe_snapshot(root, year_month, final_pass, records=None):
    dir_path = os.path.join(root, year_month)
    os.makedirs(dir_path, exist_ok=True)
    payload = {
        "as_of": year_month,
        "final_pass": final_pass,
        "records": records or {sid: {"stock_id": sid, "type": "twse"} for sid in final_pass},
    }
    with open(os.path.join(dir_path, "universe.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


class TestGetMembersInUniverse(unittest.TestCase):
    def setUp(self):
        self.member_tmp = tempfile.TemporaryDirectory()
        self.snap_tmp = tempfile.TemporaryDirectory()
        self.member_root = self.member_tmp.name
        self.snap_root = self.snap_tmp.name

        sm.add_event(sector="CPO", stock_id="3450", action="add",
                     evidence_grade="E1", evidence_desc="d", evidence_url="u",
                     evidence_date="2025-01-01", effective_from="2025-01-01",
                     root=self.member_root)
        sm.add_event(sector="CPO", stock_id="9999", action="add",
                     evidence_grade="E1", evidence_desc="d", evidence_url="u",
                     evidence_date="2025-01-01", effective_from="2025-01-01",
                     root=self.member_root)

    def tearDown(self):
        self.member_tmp.cleanup()
        self.snap_tmp.cleanup()

    def test_intersection_excludes_non_universe_member(self):
        # universe 只收 3450，不含 9999（如 9999 已下市或流動性不足被剔除）
        _write_fake_universe_snapshot(self.snap_root, "2025-06", ["3450", "1234"])
        result = sm.get_members_in_universe(
            "CPO", "2025-06", sector_root=self.member_root, snapshot_root=self.snap_root
        )
        self.assertEqual(result, ["3450"])

    def test_lookback_up_to_3_months(self):
        # 2025-06 快照缺失，2025-04 有快照 -> 回溯 2 個月應找到
        _write_fake_universe_snapshot(self.snap_root, "2025-04", ["3450"])
        result = sm.get_members_in_universe(
            "CPO", "2025-06", sector_root=self.member_root, snapshot_root=self.snap_root
        )
        self.assertEqual(result, ["3450"])

    def test_lookback_exactly_3_months_boundary(self):
        # 2025-06 往前 3 個月 = 2025-03，應仍找得到（含本月起算最多回溯 3 個月）
        _write_fake_universe_snapshot(self.snap_root, "2025-03", ["3450"])
        result = sm.get_members_in_universe(
            "CPO", "2025-06", sector_root=self.member_root, snapshot_root=self.snap_root
        )
        self.assertEqual(result, ["3450"])

    def test_lookback_beyond_3_months_raises(self):
        # 2025-06 往前 4 個月 = 2025-02，超出回溯上限，應 raise
        _write_fake_universe_snapshot(self.snap_root, "2025-02", ["3450"])
        with self.assertRaises(FileNotFoundError):
            sm.get_members_in_universe(
                "CPO", "2025-06", sector_root=self.member_root, snapshot_root=self.snap_root
            )

    def test_no_snapshot_at_all_raises(self):
        with self.assertRaises(FileNotFoundError):
            sm.get_members_in_universe(
                "CPO", "2025-06", sector_root=self.member_root, snapshot_root=self.snap_root
            )

    def test_as_of_full_date_uses_its_year_month(self):
        _write_fake_universe_snapshot(self.snap_root, "2025-06", ["3450"])
        result = sm.get_members_in_universe(
            "CPO", "2025-06-15", sector_root=self.member_root, snapshot_root=self.snap_root
        )
        self.assertEqual(result, ["3450"])


class TestGetUniverseTypeMap(unittest.TestCase):
    def setUp(self):
        self.snap_tmp = tempfile.TemporaryDirectory()
        self.snap_root = self.snap_tmp.name

    def tearDown(self):
        self.snap_tmp.cleanup()

    def test_type_map_from_records(self):
        _write_fake_universe_snapshot(
            self.snap_root, "2025-06", ["3450", "6223"],
            records={
                "3450": {"stock_id": "3450", "type": "twse"},
                "6223": {"stock_id": "6223", "type": "tpex"},
            },
        )
        result = sm.get_universe_type_map("2025-06", snapshot_root=self.snap_root)
        self.assertEqual(result, {"3450": "twse", "6223": "tpex"})

    def test_type_map_lookback(self):
        _write_fake_universe_snapshot(
            self.snap_root, "2025-04", ["3450"],
            records={"3450": {"stock_id": "3450", "type": "twse"}},
        )
        result = sm.get_universe_type_map("2025-06", snapshot_root=self.snap_root)
        self.assertEqual(result, {"3450": "twse"})

    def test_type_map_no_snapshot_raises(self):
        with self.assertRaises(FileNotFoundError):
            sm.get_universe_type_map("2025-06", snapshot_root=self.snap_root)


if __name__ == "__main__":
    unittest.main()
