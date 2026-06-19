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

# ==================== 全 universe 的 yfinance ticker 對照表 ====================
# key = 純數字股票代碼（與 data/snapshots/ 一致），value = yfinance ticker
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

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


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
    """抓取 company_ids 的營收＋外資持股，為 months 各組裝並寫入不可變月快照。
    回傳 {'written': [...paths], 'skipped': [...已存在月份]}。對 FinMind 溫和（每檔間 sleep）。
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

    written, skipped = [], []
    for ym in months:
        for kind, snap in (("revenue", build_revenue_snapshot(rev_by_sid, ym)),
                           ("holdings", build_holding_snapshot(hold_by_sid, ym))):
            if not snap:
                continue
            try:
                written.append(pit_store.write_monthly_snapshot(kind, snap, year_month=ym, root=root))
            except pit_store.SnapshotExistsError:
                skipped.append(f"{ym}/{kind}")
    return {"written": written, "skipped": skipped, "errors": errors}


# ==================== 股價（yfinance）抓取與快照 ====================

def _month_last_day(year_month: str) -> str:
    """回傳 'YYYY-MM' 對應的最後一個日曆日 'YYYY-MM-DD'。"""
    y, m = int(year_month[:4]), int(year_month[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (datetime.date(ny, nm, 1) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def fetch_month_prices(company_id: str, start_date: str = "2015-01-01") -> list:
    """以 yfinance 抓取月 K 收盤價（interval='1mo'），回傳正規化列表：
    [{stock_id, year_month 'YYYY-MM', close float, close_date 'YYYY-MM-DD'}]

    close_date = 該月最後一個日曆日（作為 PIT 可見日截斷點）。
    company_id 格式：純 4 位代碼（如 '3131'），透過 YFINANCE_TICKERS 對照。
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("需要安裝 yfinance：pip install yfinance") from e

    ticker_sym = YFINANCE_TICKERS.get(company_id)
    if ticker_sym is None:
        raise ValueError(f"無 yfinance ticker 對照：{company_id}；請更新 YFINANCE_TICKERS")

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
    """抓取 company_ids（純數字代碼）的月 K，為 months 各組裝並寫入不可變月快照。
    回傳 {'written': [...paths], 'skipped': [...已存在月份], 'errors': [...失敗]}.
    yfinance 呼叫量小（每檔一次），不需強限流；sleep 為防禦性間隔。
    """
    price_by_sid: dict = {}
    errors: list = []
    for cid in company_ids:
        try:
            price_by_sid[cid] = fetch_month_prices(cid, start_date)
        except Exception as e:
            errors.append(f"prices {cid}: {e}")
        time.sleep(sleep)

    written, skipped = [], []
    for ym in months:
        snap = build_price_snapshot(price_by_sid, ym)
        if not snap:
            continue
        try:
            written.append(
                pit_store.write_monthly_snapshot("prices", snap, year_month=ym, root=root)
            )
        except pit_store.SnapshotExistsError:
            skipped.append(f"{ym}/prices")

    return {"written": written, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    # 溫和樣本測試：2 檔 × 2 月，寫入 temp（不污染 data/），少量 FinMind 呼叫。
    import tempfile

    companies = ["3131", "2330"]      # 弘塑、台積電（必有資料）
    months = ["2024-01", "2024-02"]
    with tempfile.TemporaryDirectory() as tmp:
        res = backfill(companies, months, root=tmp, start_date="2022-06-01")
        print("written:", len(res["written"]), "skipped:", res["skipped"])

        # 不可變性：重跑同月應全部 skipped
        res2 = backfill(companies, months, root=tmp, start_date="2022-06-01")
        assert res2["written"] == [], f"重寫應全 skipped，但 written={res2['written']}"
        print("immutability OK (re-run skipped:", len(res2["skipped"]), ")")

        # PIT 讀回
        rev = pit_store.read_snapshot("revenue", "2024-02-28", root=tmp)
        hold = pit_store.read_snapshot("holdings", "2024-02-28", root=tmp)
        assert rev and "3131" in rev, "應讀到 3131 營收"
        assert hold and "3131" in hold, "應讀到 3131 外資持股"
        print("revenue 3131 @2024-02:", rev["3131"])
        print("holding 3131 @2024-02:", {k: hold["3131"][k] for k in ("date", "foreign_ratio")})
    print("OK")
