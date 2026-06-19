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

    kind∈{'revenue','holdings','prices'}；
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


def load_content_value_priors(path: str = PRIORS_PATH) -> dict:
    """讀取並回傳 content_value.json（含 generation_specs 與 eras）。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
