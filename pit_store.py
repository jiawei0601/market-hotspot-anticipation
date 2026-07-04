import os
import json
import datetime

SNAPSHOT_ROOT = "data/snapshots"          # data/snapshots/YYYY-MM/{kind}.json
PRIORS_PATH   = "data/priors/content_value.json"


class SnapshotExistsError(Exception):
    """違反 append-only 不可變鐵律：嘗試覆寫已存在的月快照。"""


def write_monthly_snapshot(
    kind: str,
    payload: dict,
    year_month: str | None = None,
    root: str = SNAPSHOT_ROOT,
) -> str:
    """寫入不可變月快照。

    kind 為任意快照種類字串（如 'revenue'、'holdings'、'prices'、'universe' 等）；
    year_month 預設當月 'YYYY-MM'。
    目標檔已存在 → raise SnapshotExistsError（永不覆寫）。
    回傳寫入路徑。
    """
    if year_month is None:
        year_month = datetime.date.today().strftime("%Y-%m")

    dir_path = os.path.join(root, year_month)
    path = os.path.join(dir_path, f"{kind}.json")

    if os.path.exists(path):
        raise SnapshotExistsError(
            f"快照已存在，拒絕覆寫（append-only 鐵律）：{path}"
        )

    os.makedirs(dir_path, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return path


def append_companies_to_snapshot(
    month: str,
    kind: str,
    new_entries: dict,
    root: str = SNAPSHOT_ROOT,
) -> dict:
    """以「(月, 公司) 級」不可變粒度追加公司條目到既有月快照。

    背景（2026-07-04 新板塊擴容時發現的結構衝突）：append-only 鐵律原本以
    「整個月檔」為不可變單位（write_monthly_snapshot 只要目標檔存在就整檔拒寫），
    導致新板塊成員（如台達電 2308）的歷史資料無法補進已存在的月份——
    ingest.py --backfill-sector 對舊月份全部被 SnapshotExistsError 跳過。

    鐵律精確化為：**既有 (月, 公司) 條目一律不可變；不存在的公司條目允許追加**。
    追加動作不觸碰既有 key 的任何 byte，PIT 安全性不受影響（過去已發布的資料
    永遠不變，只是同一月檔裡可以再長出「當時就存在、只是我們現在才抓到」的
    其他公司條目）。

    行為：
    - 月檔（root/month/{kind}.json）不存在 → 等同 write_monthly_snapshot，整檔新建。
    - 月檔存在 → 僅加入檔中尚無該公司 key 的條目；已存在的 key 完全不動
      （即使 new_entries 內容不同也不覆蓋，該 key 列入回傳的 skipped_existing）。
      只有真的有新增時才寫回檔案。

    回傳 {"added": [...新增的公司 key...], "skipped_existing": [...已存在而跳過的公司 key...]}。
    """
    dir_path = os.path.join(root, month)
    path = os.path.join(dir_path, f"{kind}.json")

    if not os.path.exists(path):
        write_monthly_snapshot(kind, dict(new_entries), year_month=month, root=root)
        return {"added": sorted(new_entries.keys()), "skipped_existing": []}

    with open(path, "r", encoding="utf-8") as f:
        existing = json.load(f)

    added = []
    skipped_existing = []
    for company_id, entry in new_entries.items():
        if company_id in existing:
            skipped_existing.append(company_id)
        else:
            existing[company_id] = entry
            added.append(company_id)

    if added:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    return {"added": sorted(added), "skipped_existing": sorted(skipped_existing)}


def read_snapshot(
    kind: str,
    as_of_date: str,
    root: str = SNAPSHOT_ROOT,
):
    """回傳 ≤ as_of_date 的最近一份月快照 (Point-in-Time)；找不到回傳 None。

    as_of_date 格式 'YYYY-MM-DD'。
    比較時取其 'YYYY-MM'，選出所有 <= 該月且含 {kind}.json 的月份中最大者。
    """
    cutoff_ym = as_of_date[:7]  # 取 'YYYY-MM'

    if not os.path.isdir(root):
        return None

    candidates = []
    for entry in os.listdir(root):
        month_dir = os.path.join(root, entry)
        if not os.path.isdir(month_dir):
            continue
        # entry 格式應為 'YYYY-MM'
        if entry <= cutoff_ym:
            snapshot_path = os.path.join(month_dir, f"{kind}.json")
            if os.path.exists(snapshot_path):
                candidates.append(entry)

    if not candidates:
        return None

    best_ym = max(candidates)
    best_path = os.path.join(root, best_ym, f"{kind}.json")

    with open(best_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_content_value_priors(path: str = PRIORS_PATH, sector: str | None = None) -> dict:
    """讀取 content_value.json（sector-keyed 先驗矩陣，見 ADR 板塊化改版）。

    檔案頂層結構為 {"sectors": {<sector_name>: {"generation_specs": ..., "eras": ...}, ...}}。

    - sector 指定時：回傳該板塊的 {"generation_specs":..., "eras":...} dict；
      查無該板塊 → 回傳空 dict {}（不可變先驗矩陣沒有此板塊時的顯式空值，
      供呼叫端如 market_monitor.get_point_in_time_matrix 靜默跳過）。
    - sector 為 None（預設）：回傳整個 sectors dict（{sector_name: {...}, ...}），
      供需要列舉全部板塊或做進一步查詢的呼叫端使用。

    向下相容：舊呼叫點若沿用 pre-ADR 檔案格式（頂層直接是
      {"generation_specs":..., "eras":...}，無 "sectors" 包裝）時，
      sector 為 None 會直接回傳整份頂層 dict；sector 有指定時視為查無該板塊，
      回傳空 dict {}。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "sectors" not in data:
        # 舊格式（無 sectors 包裝）向下相容
        return data if sector is None else {}

    sectors = data["sectors"]
    if sector is None:
        return sectors
    return sectors.get(sector, {})


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_root:
        kind = "revenue"
        ym = "2026-06"
        payload = {"test": True, "value": 42}

        # 1. 寫入快照
        written_path = write_monthly_snapshot(kind, payload, year_month=ym, root=tmp_root)
        assert os.path.exists(written_path), "快照檔案應存在"

        # 2. 第二次寫入同一月份應 raise SnapshotExistsError
        raised = False
        try:
            write_monthly_snapshot(kind, payload, year_month=ym, root=tmp_root)
        except SnapshotExistsError:
            raised = True
        assert raised, "第二次寫入應 raise SnapshotExistsError"

        # 3. 讀回快照 (as_of_date 在同月或之後均可讀到)
        result = read_snapshot(kind, as_of_date="2026-06-30", root=tmp_root)
        assert result == payload, f"讀回資料應等於寫入資料，但得到：{result}"

        # 4. 早於快照月份的 as_of_date 應得 None
        result_none = read_snapshot(kind, as_of_date="2026-05-31", root=tmp_root)
        assert result_none is None, "早於快照月份應回傳 None"

    print("OK")
