"""板塊歸屬證據定日登記簿（ADR 0008）。

目的：把「哪些股票屬於哪個板塊／segment」從人工事後認定，改為可追溯證據、
append-only、point-in-time（PIT）可重現的登記簿，避免用「現在的認知」回填
過去分析，同時保留每筆歸屬判斷背後的證據等級與來源（詳見 ADR 0008）。

儲存：data/sector_membership/{sector}.json，每個檔案是純陣列（append-only 事件列表）。
每筆事件：
    {
      "stock_id": str,
      "sector": str,
      "action": "add" | "remove",
      "segment": "equipment" | "component" | "downstream" | None,
      "evidence_grade": "E1" | "E2" | "E3",
      "evidence_desc": str,
      "evidence_url": str,
      "evidence_date": "YYYY-MM-DD",
      "effective_from": "YYYY-MM-DD",
      "recorded_at": "YYYY-MM-DD",
    }

鐵律（見 data/sector_membership/README.md）：
    1. 只能 append，不得改寫或刪除既有事件（違反即 raise）。
    2. effective_from >= evidence_date（生效日不得早於證據日——不可用未來才出現的
       證據，回頭聲稱更早就已生效）。

PIT 讀取規則：
    as_of 可傳 "YYYY-MM"（視為該月最後一天）或 "YYYY-MM-DD"。
    某股於 as_of 是否為板塊成員，取決於「effective_from <= as_of」的事件中，
    最新一筆 action 是 add 還是 remove（同一天有多筆時，以檔案內出現順序為準，
    最後一筆決定當下狀態——append-only 保證順序即時間序）。
"""
import argparse
import datetime
import json
import os

SECTOR_MEMBERSHIP_ROOT = "data/sector_membership"
SNAPSHOT_ROOT = "data/snapshots"  # 與 universe.py / pit_store.py 對齊

VALID_ACTIONS = frozenset({"add", "remove"})
VALID_SEGMENTS = frozenset({"equipment", "component", "downstream"})
VALID_EVIDENCE_GRADES = frozenset({"E1", "E2", "E3"})

MAX_SNAPSHOT_LOOKBACK_MONTHS = 3
"""get_members_in_universe 找不到 as_of 當月 universe 快照時，最多往前回溯的月數。"""


class MembershipIntegrityError(Exception):
    """違反 append-only 或日期鐵律（見 README.md「鐵律」章節）。"""


# ==================== 檔案存取 ====================

def _sector_path(sector: str, root: str = SECTOR_MEMBERSHIP_ROOT) -> str:
    return os.path.join(root, f"{sector}.json")


def _load_events(sector: str, root: str = SECTOR_MEMBERSHIP_ROOT) -> list:
    """讀回某板塊的全部事件（依檔案內順序，即記錄順序）。檔案不存在回傳空列表。"""
    path = _sector_path(sector, root=root)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_events(sector: str, events: list, root: str = SECTOR_MEMBERSHIP_ROOT) -> str:
    path = _sector_path(sector, root=root)
    os.makedirs(root, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    return path


# ==================== 日期輔助 ====================

def _normalize_as_of(as_of: str) -> str:
    """"YYYY-MM" -> 該月最後一天的 "YYYY-MM-DD"；"YYYY-MM-DD" 原樣回傳。"""
    if len(as_of) == 7:  # "YYYY-MM"
        y, m = int(as_of[:4]), int(as_of[5:7])
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last_day = datetime.date(ny, nm, 1) - datetime.timedelta(days=1)
        return last_day.strftime("%Y-%m-%d")
    return as_of


def _validate_date_str(date_str: str, field_name: str) -> None:
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise MembershipIntegrityError(
            f"{field_name} 必須是 'YYYY-MM-DD' 格式，得到：{date_str!r}"
        )


def _months_before(year_month: str, n: int) -> str:
    y, m = int(year_month[:4]), int(year_month[5:7])
    total = y * 12 + (m - 1) - n
    yy, mm = divmod(total, 12)
    return f"{yy:04d}-{mm + 1:02d}"


# ==================== 事件驗證與寫入（鐵律 2：日期） ====================

def _validate_event(action: str, evidence_grade: str, evidence_date: str,
                     effective_from: str) -> None:
    if action not in VALID_ACTIONS:
        raise MembershipIntegrityError(
            f"action 必須是 {sorted(VALID_ACTIONS)} 之一，得到：{action!r}"
        )
    if evidence_grade not in VALID_EVIDENCE_GRADES:
        raise MembershipIntegrityError(
            f"evidence_grade 必須是 {sorted(VALID_EVIDENCE_GRADES)} 之一，得到：{evidence_grade!r}"
        )
    _validate_date_str(evidence_date, "evidence_date")
    _validate_date_str(effective_from, "effective_from")
    if effective_from < evidence_date:
        raise MembershipIntegrityError(
            f"effective_from（{effective_from}）不得早於 evidence_date（{evidence_date}）"
            "——生效不得早於證據（見 README.md 鐵律）"
        )


def add_event(sector: str, stock_id: str, action: str, evidence_grade: str,
              evidence_desc: str, evidence_url: str, evidence_date: str,
              effective_from: str, segment: str | None = None,
              recorded_at: str | None = None,
              root: str = SECTOR_MEMBERSHIP_ROOT) -> None:
    """Append 一筆歸屬事件到 data/sector_membership/{sector}.json。

    只會 append，不會改寫或刪除既有事件（append-only 鐵律）。
    驗證失敗（action/evidence_grade 不合法、日期格式錯誤、effective_from < evidence_date）
    一律 raise MembershipIntegrityError，不寫入任何內容。
    """
    if segment is not None and segment not in VALID_SEGMENTS:
        raise MembershipIntegrityError(
            f"segment 必須是 {sorted(VALID_SEGMENTS)} 之一或 None，得到：{segment!r}"
        )
    _validate_event(action, evidence_grade, evidence_date, effective_from)

    if recorded_at is None:
        recorded_at = datetime.date.today().strftime("%Y-%m-%d")
    else:
        _validate_date_str(recorded_at, "recorded_at")

    event = {
        "stock_id": stock_id,
        "sector": sector,
        "action": action,
        "segment": segment,
        "evidence_grade": evidence_grade,
        "evidence_desc": evidence_desc,
        "evidence_url": evidence_url,
        "evidence_date": evidence_date,
        "effective_from": effective_from,
        "recorded_at": recorded_at,
    }

    events = _load_events(sector, root=root)
    events.append(event)
    _write_events(sector, events, root=root)


# ==================== PIT 讀取 ====================

def get_members(sector: str, as_of: str, root: str = SECTOR_MEMBERSHIP_ROOT) -> list:
    """回傳 as_of 當下該板塊的成員 stock_id 排序清單。

    as_of 接受 "YYYY-MM"（視為該月最後一天）或 "YYYY-MM-DD"。
    規則：只看 effective_from <= as_of 的事件，依檔案內順序（即時間序）逐筆套用
    add/remove，最終仍在集合內的 stock_id 即為成員。
    無檔案或無符合事件回傳 []。
    """
    cutoff = _normalize_as_of(as_of)
    events = _load_events(sector, root=root)

    members = set()
    for ev in events:
        if ev["effective_from"] > cutoff:
            continue
        if ev["action"] == "add":
            members.add(ev["stock_id"])
        elif ev["action"] == "remove":
            members.discard(ev["stock_id"])
    return sorted(members)


def get_member_segments(sector: str, as_of: str,
                         root: str = SECTOR_MEMBERSHIP_ROOT) -> dict:
    """回傳 as_of 當下該板塊「成員 -> segment」對照表。

    同一 stock_id 若有多筆 effective_from <= as_of 的事件，取 effective_from 最新
    一筆（同日則取檔案內較後出現者）的 segment。非成員（已被 remove 或從未 add）
    不出現在回傳字典中。
    """
    cutoff = _normalize_as_of(as_of)
    events = _load_events(sector, root=root)

    current_members = set(get_members(sector, as_of, root=root))

    latest_segment_event = {}  # stock_id -> (effective_from, order_index, segment)
    for idx, ev in enumerate(events):
        if ev["effective_from"] > cutoff:
            continue
        sid = ev["stock_id"]
        key = (ev["effective_from"], idx)
        prev = latest_segment_event.get(sid)
        if prev is None or key > prev[0]:
            latest_segment_event[sid] = (key, ev.get("segment"))

    return {
        sid: latest_segment_event[sid][1]
        for sid in current_members
        if sid in latest_segment_event
    }


# ==================== 與 universe 快照交集 ====================

def _find_universe_snapshot(year_month: str, root: str = SNAPSHOT_ROOT,
                             max_lookback: int = MAX_SNAPSHOT_LOOKBACK_MONTHS) -> tuple:
    """從 year_month 起往前找最近一個存在 universe.json 的月份（含本月，最多回溯
    max_lookback 個月）。回傳 (找到的月份, 該快照 dict)；找不到 raise FileNotFoundError。
    """
    for i in range(max_lookback + 1):
        ym = _months_before(year_month, i) if i > 0 else year_month
        path = os.path.join(root, ym, "universe.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return ym, json.load(f)
    raise FileNotFoundError(
        f"找不到 universe 快照：{year_month} 及往前回溯 {max_lookback} 個月皆無"
        f"（查找根目錄：{root}）。可能尚未跑 universe.py 產生該期間快照。"
    )


def get_members_in_universe(sector: str, as_of: str,
                             sector_root: str = SECTOR_MEMBERSHIP_ROOT,
                             snapshot_root: str = SNAPSHOT_ROOT) -> list:
    """回傳 get_members(sector, as_of) 與該月 universe 快照 final_pass 的交集。

    as_of 為日期時取其年月去找 universe 快照；當月快照不存在時往前找最近一個月
    （最多回溯 MAX_SNAPSHOT_LOOKBACK_MONTHS 個月），仍找不到則 raise FileNotFoundError。
    """
    cutoff = _normalize_as_of(as_of)
    year_month = cutoff[:7]

    _, snapshot = _find_universe_snapshot(year_month, root=snapshot_root)
    universe_ids = set(snapshot.get("final_pass") or [])

    members = get_members(sector, as_of, root=sector_root)
    return sorted(m for m in members if m in universe_ids)


def get_universe_type_map(as_of: str, snapshot_root: str = SNAPSHOT_ROOT) -> dict:
    """回傳 as_of 當月 universe 快照 records 中的 stock_id -> "twse"|"tpex" 對照表
    （供呼叫端組 yfinance ticker 尾碼 .TW/.TWO）。

    當月快照不存在時往前找最近一個月（最多回溯 MAX_SNAPSHOT_LOOKBACK_MONTHS 個月），
    仍找不到則 raise FileNotFoundError。
    """
    cutoff = _normalize_as_of(as_of)
    year_month = cutoff[:7]

    _, snapshot = _find_universe_snapshot(year_month, root=snapshot_root)
    records = snapshot.get("records") or {}
    return {sid: rec.get("type") for sid, rec in records.items()}


# ==================== CLI ====================

def cmd_list(sector: str, root: str = SECTOR_MEMBERSHIP_ROOT):
    events = _load_events(sector, root=root)
    if not events:
        print(f"板塊 {sector} 尚無任何事件。")
        return
    print(f"板塊 {sector} 共 {len(events)} 筆事件：")
    for ev in events:
        print(f"  {ev['effective_from']} {ev['action']:>6} {ev['stock_id']} "
              f"segment={ev['segment']} grade={ev['evidence_grade']} "
              f"({ev['evidence_desc']})")


def cmd_members(sector: str, as_of: str, root: str = SECTOR_MEMBERSHIP_ROOT):
    members = get_members(sector, as_of, root=root)
    print(f"板塊 {sector} 於 {as_of} 的成員（{len(members)} 檔）：{members}")


def cmd_add(args, root: str = SECTOR_MEMBERSHIP_ROOT):
    add_event(
        sector=args.sector,
        stock_id=args.stock_id,
        action=args.action,
        evidence_grade=args.evidence_grade,
        evidence_desc=args.evidence_desc,
        evidence_url=args.evidence_url,
        evidence_date=args.evidence_date,
        effective_from=args.effective_from,
        segment=args.segment,
        root=root,
    )
    print(f"已新增事件：{args.sector} {args.action} {args.stock_id} "
          f"(effective_from={args.effective_from})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="板塊歸屬證據定日登記簿（ADR 0008）")
    parser.add_argument("--list", metavar="SECTOR", help="列出該板塊全部事件")
    parser.add_argument("--members", metavar="SECTOR", help="列出該板塊 as_of 當下成員")
    parser.add_argument("--as-of", metavar="YYYY-MM[-DD]", help="配合 --members 使用")
    parser.add_argument("--add", action="store_true", help="新增一筆事件（需搭配下列欄位參數）")
    parser.add_argument("--sector", help="板塊名稱")
    parser.add_argument("--stock-id", help="股票代號")
    parser.add_argument("--action", choices=sorted(VALID_ACTIONS), help="add 或 remove")
    parser.add_argument("--segment", choices=sorted(VALID_SEGMENTS), default=None,
                         help="equipment/component/downstream，可省略")
    parser.add_argument("--evidence-grade", choices=sorted(VALID_EVIDENCE_GRADES),
                         help="E1/E2/E3")
    parser.add_argument("--evidence-desc", help="證據描述")
    parser.add_argument("--evidence-url", help="證據連結")
    parser.add_argument("--evidence-date", help="證據日期 YYYY-MM-DD")
    parser.add_argument("--effective-from", help="生效日 YYYY-MM-DD（須 >= evidence-date）")

    args = parser.parse_args()

    if args.list:
        cmd_list(args.list)
    elif args.members:
        if not args.as_of:
            parser.error("--members 需搭配 --as-of")
        cmd_members(args.members, args.as_of)
    elif args.add:
        missing = [
            name for name, val in [
                ("--sector", args.sector), ("--stock-id", args.stock_id),
                ("--action", args.action), ("--evidence-grade", args.evidence_grade),
                ("--evidence-desc", args.evidence_desc), ("--evidence-url", args.evidence_url),
                ("--evidence-date", args.evidence_date), ("--effective-from", args.effective_from),
            ] if not val
        ]
        if missing:
            parser.error(f"--add 需搭配以下欄位參數：{', '.join(missing)}")
        cmd_add(args)
    else:
        parser.print_help()
