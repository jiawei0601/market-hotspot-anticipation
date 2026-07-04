"""Stage 2 真實資料 ingestion 層（網路）。

把 FinMind（主）／TWSE（備）的真實資料抓進來、正規化、組裝成 Point-in-Time
月快照，再交給純儲存層 `pit_store` 以 append-only 方式落地。

設計原則（見 ADR 0003/0004/0006、CONTEXT.md）：
- 網路與儲存分離：本檔負責抓取/正規化；寫入一律走 `pit_store.write_monthly_snapshot`。
- PIT 正確：
  - 營收可見日＝FinMind `create_time`（公布日），無則套「次月 10 日」規則；
  - 外資持股以資料日期為可見日；
  - 股價以月底最後交易日為可見日（close_date = 該月最後一個日曆日）。
- FinMind 免費有限流 → 逐檔抓取之間 sleep。
- 股價使用 yfinance 月 K（interval="1mo"），Close = 該月最後交易日收盤價。
"""
import os
import json
import time
import datetime
import urllib.request
import urllib.parse

import pit_store
import sector_membership

# ==================== legacy 的 yfinance ticker 對照表 ====================
# key = 純數字股票代碼（與 data/snapshots/ 一致），value = yfinance ticker
# 保留供既有呼叫相容；新代碼優先透過 resolve_yfinance_ticker()，查無 legacy 對照時
# 改用 sector_membership.get_universe_type_map 動態解析（登記簿驅動，見 ADR 0008）。
YFINANCE_TICKERS: dict[str, str] = {
    "3131": "3131.TWO",
    "3680": "3680.TWO",
    "6683": "6683.TWO",
    "6187": "6187.TWO",
    "6223": "6223.TWO",
    "3013": "3013.TW",
    "3017": "3017.TW",
    "3583": "3583.TW",
    "3324": "3324.TWO",
    "2486": "2486.TW",
    "3450": "3450.TW",
    "8027": "8027.TWO",
}

_TYPE_TO_SUFFIX = {"twse": ".TW", "tpex": ".TWO"}

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _finmind_token() -> str:
    """FinMind API token：環境變數 FINMIND_TOKEN 優先，否則從專案 .env 讀取；皆無則回空字串（匿名層）。
    邏輯與 universe.py 的 _finmind_token() 一致（本檔不得改 universe.py，故自建同邏輯函式）。"""
    token = os.environ.get("FINMIND_TOKEN", "").strip()
    if token:
        return token
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("FINMIND_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def resolve_yfinance_ticker(company_id: str, as_of: str | None = None) -> str:
    """把純數字股票代碼解析為 yfinance ticker，三層 fallback：

    1. YFINANCE_TICKERS legacy 對照表（保留相容既有呼叫）。
    2. 查無 legacy 對照 → 用 sector_membership.get_universe_type_map(as_of) 查
       universe 快照的 type（twse -> '{id}.TW'，tpex -> '{id}.TWO'）。
       as_of 未提供時預設今天所在月份。
    3. 兩層皆查無 → raise ValueError 附明確訊息（不可靜默臆測）。
    """
    legacy = YFINANCE_TICKERS.get(company_id)
    if legacy is not None:
        return legacy

    if as_of is None:
        as_of = datetime.date.today().strftime("%Y-%m")

    try:
        type_map = sector_membership.get_universe_type_map(as_of)
    except FileNotFoundError as e:
        raise ValueError(
            f"無 yfinance ticker 對照：{company_id}"
            f"（legacy 表查無，universe 快照亦查無：{e}）"
        ) from e

    stock_type = type_map.get(company_id)
    suffix = _TYPE_TO_SUFFIX.get(stock_type)
    if suffix is None:
        raise ValueError(
            f"無 yfinance ticker 對照：{company_id}"
            f"（legacy 表查無，universe type map 中 type={stock_type!r} 無法判斷 .TW/.TWO 尾碼；"
            "請確認 universe 快照涵蓋此股或補充 YFINANCE_TICKERS）"
        )
    return f"{company_id}{suffix}"


# ==================== FinMind 抓取與正規化 ====================

def _finmind(dataset: str, data_id: str, start_date: str,
             end_date: str | None = None, token: str | None = None,
             timeout: int = 25) -> list:
    params = {"dataset": dataset, "data_id": data_id, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    if token:
        params["token"] = token
    url = f"{FINMIND_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8"))
    if j.get("status") != 200:
        raise RuntimeError(f"FinMind {dataset} {data_id} 失敗：{j.get('msg')}")
    return j.get("data") or []


def _announce_date(revenue_year: int, revenue_month: int, create_time: str) -> str:
    """營收可見日：有公布日 (create_time) 用之，否則套『次月 10 日』規則。"""
    if create_time:
        return create_time  # 'YYYY-MM-DD'
    y, m = revenue_year, revenue_month
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{ny:04d}-{nm:02d}-10"


def fetch_month_revenue(company_id: str, start_date: str = "2015-01-01",
                        token: str | None = None) -> list:
    """回傳正規化月營收（含 YoY 與可見日）：
    [{stock_id, period 'YYYY-MM', revenue_billion, yoy_pct, announce_date}, ...]
    """
    rows = _finmind("TaiwanStockMonthRevenue", company_id, start_date, token=token)
    # 先建 period -> 億元，供 YoY 計算
    rev_by_period = {}
    norm = []
    for r in rows:
        ry, rm = int(r["revenue_year"]), int(r["revenue_month"])
        period = f"{ry:04d}-{rm:02d}"
        rev_b = round(r["revenue"] / 1e8, 4)  # FinMind 單位＝元 → 億元
        rev_by_period[period] = rev_b
        norm.append({
            "stock_id": company_id,
            "period": period,
            "_y": ry, "_m": rm,
            "revenue_billion": rev_b,
            "announce_date": _announce_date(ry, rm, r.get("create_time") or ""),
        })
    out = []
    for rec in norm:
        prev = f"{rec['_y'] - 1:04d}-{rec['_m']:02d}"
        base = rev_by_period.get(prev)
        rec["yoy_pct"] = (round((rec["revenue_billion"] - base) / base * 100, 2)
                          if base and base > 0 else None)
        del rec["_y"], rec["_m"]
        out.append(rec)
    return out


def fetch_foreign_holding(company_id: str, start_date: str = "2015-01-01",
                          token: str | None = None) -> list:
    """回傳正規化外資持股：[{stock_id, date 'YYYY-MM-DD', foreign_ratio}, ...]"""
    rows = _finmind("TaiwanStockShareholding", company_id, start_date, token=token)
    return [{
        "stock_id": company_id,
        "date": r["date"],
        "foreign_ratio": r.get("ForeignInvestmentSharesRatio"),
    } for r in rows if r.get("ForeignInvestmentSharesRatio") is not None]


# ==================== 組裝 Point-in-Time 月快照 ====================

def _month_end(year_month: str) -> str:
    y, m = (int(x) for x in year_month.split("-"))
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (datetime.date(ny, nm, 1) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def build_revenue_snapshot(records_by_sid: dict, year_month: str) -> dict:
    """某月的 PIT 營收快照：每檔取『可見日 <= 該月月底』中 period 最新的一筆。"""
    cutoff = _month_end(year_month)
    snap = {}
    for sid, recs in records_by_sid.items():
        visible = [r for r in recs if r["announce_date"] <= cutoff]
        if visible:
            snap[sid] = max(visible, key=lambda r: r["period"])
    return snap


def build_holding_snapshot(records_by_sid: dict, year_month: str) -> dict:
    """某月的 PIT 外資持股快照：每檔取『日期 <= 該月月底』中最新一筆。"""
    cutoff = _month_end(year_month)
    snap = {}
    for sid, recs in records_by_sid.items():
        visible = [r for r in recs if r["date"] <= cutoff]
        if visible:
            snap[sid] = max(visible, key=lambda r: r["date"])
    return snap


def backfill(company_ids: list, months: list, root: str = pit_store.SNAPSHOT_ROOT,
             start_date: str = "2015-01-01", token: str | None = None,
             sleep: float = 0.6) -> dict:
    """抓取 company_ids 的營收＋外資持股，為 months 各組裝並以「(月, 公司) 級」
    不可變粒度追加進月快照（見 pit_store.append_companies_to_snapshot）。

    回傳 {'added': [...'YYYY-MM/kind:company_id'...], 'skipped_existing': [...同格式...],
    'errors': [...]}。對 FinMind 溫和（每檔間 sleep）。同一 (月, 公司) 重跑必為
    skipped_existing，故整體冪等。
    """
    rev_by_sid, hold_by_sid = {}, {}
    errors = []
    for cid in company_ids:
        try:
            rev_by_sid[cid] = fetch_month_revenue(cid, start_date, token=token)
        except Exception as e:  # 單檔失敗不中止整批（FinMind 限流/缺資料）
            errors.append(f"revenue {cid}: {e}")
        time.sleep(sleep)
        try:
            hold_by_sid[cid] = fetch_foreign_holding(cid, start_date, token=token)
        except Exception as e:
            errors.append(f"holdings {cid}: {e}")
        time.sleep(sleep)

    added, skipped_existing = [], []
    for ym in months:
        for kind, snap in (("revenue", build_revenue_snapshot(rev_by_sid, ym)),
                           ("holdings", build_holding_snapshot(hold_by_sid, ym))):
            if not snap:
                continue
            result = pit_store.append_companies_to_snapshot(ym, kind, snap, root=root)
            added.extend(f"{ym}/{kind}:{cid}" for cid in result["added"])
            skipped_existing.extend(f"{ym}/{kind}:{cid}" for cid in result["skipped_existing"])
    return {"added": added, "skipped_existing": skipped_existing, "errors": errors}


# ==================== 股價（yfinance）抓取與快照 ====================

def _month_last_day(year_month: str) -> str:
    """回傳 'YYYY-MM' 對應的最後一個日曆日 'YYYY-MM-DD'。"""
    y, m = int(year_month[:4]), int(year_month[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (datetime.date(ny, nm, 1) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def fetch_month_prices(company_id: str, start_date: str = "2015-01-01",
                       as_of: str | None = None) -> list:
    """以 yfinance 抓取月 K 收盤價（interval='1mo'），回傳正規化列表：
    [{stock_id, year_month 'YYYY-MM', close float, close_date 'YYYY-MM-DD'}]

    close_date = 該月最後一個日曆日（作為 PIT 可見日截斷點）。
    company_id 格式：純 4 位代碼（如 '3131'），透過 resolve_yfinance_ticker() 對照
    （legacy 表優先，查無則以 sector_membership 登記簿的 universe type map 動態解析）。
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("需要安裝 yfinance：pip install yfinance") from e

    ticker_sym = resolve_yfinance_ticker(company_id, as_of=as_of)

    end = (datetime.date.today() + datetime.timedelta(days=45)).strftime("%Y-%m-%d")
    hist = yf.Ticker(ticker_sym).history(start=start_date, end=end, interval="1mo")

    if hist.empty:
        raise RuntimeError(f"yfinance {ticker_sym} 無資料（start={start_date}）")

    out = []
    for idx, row in hist.iterrows():
        ym = idx.strftime("%Y-%m")
        close_date = _month_last_day(ym)
        out.append({
            "stock_id": company_id,
            "year_month": ym,
            "close": round(float(row["Close"]), 2),
            "close_date": close_date,
        })
    return out


def build_price_snapshot(price_by_sid: dict, year_month: str) -> dict:
    """某月的 PIT 股價快照：每檔取 year_month 相符的月 K 收盤。
    PIT 可見日 = close_date（月底），呼叫端以 close_date <= as_of_date 篩選。
    """
    snap = {}
    for sid, recs in price_by_sid.items():
        match = [r for r in recs if r["year_month"] == year_month]
        if match:
            r = match[-1]
            snap[sid] = {"close": r["close"], "close_date": r["close_date"]}
    return snap


def backfill_prices(
    company_ids: list,
    months: list,
    root: str = pit_store.SNAPSHOT_ROOT,
    start_date: str = "2015-01-01",
    sleep: float = 0.3,
) -> dict:
    """抓取 company_ids（純數字代碼）的月 K，為 months 各組裝並以「(月, 公司) 級」
    不可變粒度追加進月快照（見 pit_store.append_companies_to_snapshot）。

    回傳 {'added': [...'YYYY-MM/prices:company_id'...], 'skipped_existing': [...同格式...],
    'errors': [...失敗]}。yfinance 呼叫量小（每檔一次），不需強限流；sleep 為防禦性間隔。
    同一 (月, 公司) 重跑必為 skipped_existing，故整體冪等。
    """
    price_by_sid: dict = {}
    errors: list = []
    for cid in company_ids:
        try:
            price_by_sid[cid] = fetch_month_prices(cid, start_date)
        except Exception as e:
            errors.append(f"prices {cid}: {e}")
        time.sleep(sleep)

    added, skipped_existing = [], []
    for ym in months:
        snap = build_price_snapshot(price_by_sid, ym)
        if not snap:
            continue
        result = pit_store.append_companies_to_snapshot(ym, "prices", snap, root=root)
        added.extend(f"{ym}/prices:{cid}" for cid in result["added"])
        skipped_existing.extend(f"{ym}/prices:{cid}" for cid in result["skipped_existing"])

    return {"added": added, "skipped_existing": skipped_existing, "errors": errors}


# ==================== 登記簿驅動的板塊回填（sector_membership 全集） ====================

def _month_range_inclusive(start: str, end: str) -> list:
    """回傳 start ~ end（皆 'YYYY-MM'，含頭尾）逐月列表。"""
    sy, sm_ = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    total_start = sy * 12 + (sm_ - 1)
    total_end = ey * 12 + (em - 1)
    months = []
    for total in range(total_start, total_end + 1):
        yy, mm = divmod(total, 12)
        months.append(f"{yy:04d}-{mm + 1:02d}")
    return months


def backfill_sector(sector: str, start_month: str = "2015-01",
                     end_month: str | None = None,
                     token: str | None = None) -> dict:
    """以 sector_membership 登記簿驅動的板塊回填：成員清單不再寫死，改由登記簿決定。

    成員解析：用 sector_membership.get_members(sector, <end_month 或今月>) 取得該板塊
    「登記簿全集」（不與 universe 快照交集——資料層寧多勿少，交集判斷留給下游分析層）。

    對每個成員逐檔跑：
    - backfill()：營收 + 外資持股快照。
    - backfill_prices()：股價快照（resolve_yfinance_ticker 三層 fallback 解析 ticker）。

    不可變粒度為「(月, 公司) 級」（見 pit_store.append_companies_to_snapshot）：
    已存在的 (月, 公司) 條目由底層擋下並歸入 'skipped_existing'；不存在的公司條目
    （即使該月檔案已存在）允許追加為 'added'。backfill()/backfill_prices() 內部
    已組好此語意，故本函式沿用其回傳、不需額外處理。

    進度：每處理 10 檔成員列印一次。

    回傳：{'sector', 'as_of', 'members', 'revenue_holdings': {...}, 'prices': {...}}
    """
    as_of = end_month or datetime.date.today().strftime("%Y-%m")
    members = sector_membership.get_members(sector, as_of)

    if token is None:
        token = _finmind_token()

    months = _month_range_inclusive(start_month, as_of)

    print(f"板塊 {sector} @ {as_of}：登記簿全集共 {len(members)} 檔成員，"
          f"回填月份 {start_month} ~ {as_of}（共 {len(months)} 個月）", flush=True)

    total = len(members)
    rev_hold_results = {"added": [], "skipped_existing": [], "errors": []}
    price_results = {"added": [], "skipped_existing": [], "errors": []}

    for i, cid in enumerate(members, 1):
        r1 = backfill([cid], months, start_date=f"{start_month}-01", token=token)
        r2 = backfill_prices([cid], months, start_date=f"{start_month}-01")
        for key in ("added", "skipped_existing", "errors"):
            rev_hold_results[key].extend(r1[key])
            price_results[key].extend(r2[key])

        if i % 10 == 0 or i == total:
            print(f"[{i}/{total}] 已處理板塊 {sector} 成員（累計 revenue/holdings "
                  f"added={len(rev_hold_results['added'])} "
                  f"skipped_existing={len(rev_hold_results['skipped_existing'])} "
                  f"errors={len(rev_hold_results['errors'])}；"
                  f"prices added={len(price_results['added'])} "
                  f"skipped_existing={len(price_results['skipped_existing'])} "
                  f"errors={len(price_results['errors'])}）", flush=True)

    return {
        "sector": sector,
        "as_of": as_of,
        "members": members,
        "revenue_holdings": rev_hold_results,
        "prices": price_results,
    }


def _run_sample_test():
    """溫和樣本測試：2 檔 × 2 月，寫入 temp（不污染 data/），少量 FinMind 呼叫。"""
    import tempfile

    companies = ["3131", "2330"]      # 弘塑、台積電（必有資料）
    months = ["2024-01", "2024-02"]
    with tempfile.TemporaryDirectory() as tmp:
        res = backfill(companies, months, root=tmp, start_date="2022-06-01")
        print("added:", len(res["added"]), "skipped_existing:", res["skipped_existing"])

        # 不可變性：重跑同月同公司應全部 skipped_existing
        res2 = backfill(companies, months, root=tmp, start_date="2022-06-01")
        assert res2["added"] == [], f"重寫應全 skipped_existing，但 added={res2['added']}"
        print("immutability OK (re-run skipped_existing:", len(res2["skipped_existing"]), ")")

        # PIT 讀回
        rev = pit_store.read_snapshot("revenue", "2024-02-28", root=tmp)
        hold = pit_store.read_snapshot("holdings", "2024-02-28", root=tmp)
        assert rev and "3131" in rev, "應讀到 3131 營收"
        assert hold and "3131" in hold, "應讀到 3131 外資持股"
        print("revenue 3131 @2024-02:", rev["3131"])
        print("holding 3131 @2024-02:", {k: hold["3131"][k] for k in ("date", "foreign_ratio")})
    print("OK")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PIT 資料 ingestion（登記簿驅動）")
    parser.add_argument("--backfill-sector", metavar="SECTOR",
                         help="以 sector_membership 登記簿全集回填某板塊（營收/持股/股價）")
    parser.add_argument("--start", default="2015-01", metavar="YYYY-MM",
                         help="回填起始月，預設 2015-01（配合 --backfill-sector）")
    parser.add_argument("--end", default=None, metavar="YYYY-MM",
                         help="回填結束月與成員解析 as_of，預設今月（配合 --backfill-sector）")
    args = parser.parse_args()

    if args.backfill_sector:
        result = backfill_sector(args.backfill_sector, start_month=args.start, end_month=args.end)
        print(f"完成：{result['sector']} 共 {len(result['members'])} 檔成員；"
              f"revenue/holdings added={len(result['revenue_holdings']['added'])}；"
              f"prices added={len(result['prices']['added'])}")
    else:
        _run_sample_test()
