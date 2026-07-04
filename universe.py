"""Universe 客觀化全市場篩選管線（ADR 0007）。

目的：把「哪些股票納入分析母體」從人工事後選定，改為可重現的規則式篩選，
產出每月一次的不可變 PIT universe 快照，供 forward 分析使用（詳見 ADR 0007）。

三層漏斗（先驗固定，禁止回測調參，見各常數 docstring）：
  母體：FinMind TaiwanStockInfo 的 type ∈ {twse, tpex}（含已下市股），排除 emerging。
  規則 1：上市時長 ≥ MIN_LISTING_MONTHS。
  規則 2：近 3 個月月底交易日成交金額皆 ≥ MONTH_END_TURNOVER_FLOOR。
  规则 3：industry_category ∈ INDUSTRY_ALLOWED。

資料來源與快取：
  - 上市股月底行情：TWSE `exchangeReport/MI_INDEX?type=ALLBUT0999`（一次一個月全市場）。
  - 上櫃股月底行情：FinMind `TaiwanStockPrice`（逐檔抓全歷史區間，本地切月）。
  - 原始回應快取到 data/universe_cache/，檔案存在即不重打（可續跑）。
  - FinMind 請求間 sleep ≥ 3 秒、TWSE ≥ 2 秒（免費層溫和節奏，見 probe-0007）。

誠實聲明（詳見 ADR 0007，此處僅摘要）：
  (1) 產業分類為「現行分類回溯套用到歷史月份」，非歷史時點真實分類。
  (2) 上櫃股下市清單無官方批次端點，本管線目前無法完整排除上櫃已下市股。
  (3) 流動性用「月底單日抽樣」做代理指標，非月度總成交量或均量。
  (4) universe 快照僅供 forward 使用起點與弱證據回測，不構成策略證據。
"""
import os
import sys
import json
import time
import datetime
import urllib.error
import urllib.request
import urllib.parse

import pit_store

# ==================== 先驗固定規則常數（禁止回測調參） ====================

MIN_LISTING_MONTHS = 12
"""規則 1：上市時長門檻（月）。該股在資料中最早可見價格月份距 as_of 需 ≥ 此值才納入。
先驗固定：確保有足夠歷史可供訊號計算，非依回測結果調整。"""

MONTH_END_TURNOVER_FLOOR = 15_000_000
"""規則 2：流動性門檻（新台幣元）。近 3 個月「每個月底交易日的成交金額」皆須 ≥ 此值。
誠實標註：這是「月底單日抽樣」的代理指標，非月度總成交量或日均成交量——
選擇月底單日是因為批次端點（TWSE MI_INDEX）天生只給單日全市場快照，
逐日全月加總的成本（交易日數 × 月數）超出可行範圍，故以月底一日代表趨勢，
可能低估月中曾有高流動性但月底恰逢量縮的個股，此為已知限制而非資料遺漏。"""

INDUSTRY_ALLOWED = frozenset({
    "半導體業",
    "光電業",
    "電子零組件業",
    "電腦及週邊設備業",
    "通信網路業",
    "電子通路業",
    "其他電子業",
    "電機機械",
    "電子工業",
})
"""規則 3：允許的產業分類（以 FinMind TaiwanStockInfo 實際字串為準，2026-07-04 打 API 核對）。
探查報告記載 industry_category 共 57 類（含 ETF/ETN/Index 等非個股類別）；
本清單為其中與電子供應鏈相關的類別，字串逐一與 API 回應核對過，非猜測拼寫。

「電子工業」為 2026-07-04 首次實跑後的 pre-registration 修正（見 ADR 0007「修正紀錄」）：
TaiwanStockInfo 對部分上市電子股（如 3017 奇鋐、3013 晟銘電）掛的是粗分類「電子工業」
而非細分類（半導體業/電子零組件業等），屬分類字串粒度不一致問題；
修正時點在任何回測使用本清單之前，性質為資格判定修正、非回測調參。
注意：此為「現行分類回溯套用到歷史月份」，見 ADR 0007 誠實聲明 (1)。"""

RULES_VERSION = "0007-v1"
"""快照內記錄的規則版本標籤，供未來規則變動時追溯是哪個版本產出的快照。"""

FINMIND_SLEEP_SECONDS = 3.0
TWSE_SLEEP_SECONDS = 2.0

RATE_LIMIT_RETRY_SLEEPS = (60, 900, 900)
"""FinMind 402/403 限流時的指數退避重試間隔（秒）：先 60s 重試一次，再失敗 900s（15 分鐘）
重試，最多 3 輪；全部耗盡仍失敗才記 fetch_error（2026-07-04 實跑證實免費層約 285 次請求
即觸發 402 'Requests reach the upper limit'，探查報告只測 5 次未涵蓋此情況）。"""

PACED_WINDOW_MAX = 48
"""--paced 模式下最多等待的「小時窗口」數（防無限迴圈的保險上限，48 = 最多等兩天）。"""

PROGRESS_PRINT_EVERY = 50
"""上櫃股逐檔處理進度：每處理此數量列印一次進度與已快取檔案數。"""

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
TWSE_MI_INDEX_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"
TWSE_DELISTED_URL = "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml"

CACHE_ROOT = "data/universe_cache"
SNAPSHOT_ROOT = pit_store.SNAPSHOT_ROOT


def _finmind_token() -> str:
    """FinMind API token：環境變數 FINMIND_TOKEN 優先，否則從專案 .env 讀取；皆無則回空字串（匿名層）。
    有 token 時額度 600 次/小時，匿名約 300 次/小時。"""
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

# 可注入的 sleep（測試以 monkeypatch universe._sleep 免除真實等待）
_sleep = time.sleep

# --paced 模式旗標（由 CLI --paced 設定；偵測到限流時睡到下個小時再續，供無人值守長回填）
_paced_mode = False


def set_paced_mode(on: bool) -> None:
    global _paced_mode
    _paced_mode = bool(on)


def _seconds_until_next_hour(now: datetime.datetime | None = None) -> float:
    """回傳距下一個整點（+30 秒緩衝）的秒數，最少 1 秒。"""
    if now is None:
        now = datetime.datetime.now()
    nxt = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1, seconds=30)
    return max(1.0, (nxt - now).total_seconds())


def _open_json_with_retry(url: str, timeout: int = 30, opener=None):
    """打 URL 取 JSON，對 HTTP 402/403（FinMind 限流）具韌性：

    - 一般模式：依 RATE_LIMIT_RETRY_SLEEPS 指數退避（60s → 900s → 900s），耗盡仍失敗才拋出。
    - --paced 模式（set_paced_mode(True)）：偵測到限流即睡到下個整點再重試，
      最多 PACED_WINDOW_MAX 個窗口，讓長回填能無人值守跑完。
    - 非限流錯誤（其他 HTTP 錯誤/網路錯誤）直接拋出，不重試（fail loud）。

    opener 參數供測試注入 fake（callable(url, timeout) -> dict），預設走真實網路。
    """
    def _real_open(u, t):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=t) as r:
            return json.loads(r.read().decode("utf-8"))

    open_fn = opener or _real_open
    backoff_attempts = 0
    paced_windows = 0

    while True:
        try:
            return open_fn(url, timeout)
        except urllib.error.HTTPError as e:
            if e.code not in (402, 403):
                raise
            if _paced_mode:
                paced_windows += 1
                if paced_windows > PACED_WINDOW_MAX:
                    raise
                wait = _seconds_until_next_hour()
                print(f"限流（HTTP {e.code}）：--paced 模式，睡 {wait:.0f} 秒到下個整點再續"
                      f"（第 {paced_windows}/{PACED_WINDOW_MAX} 個窗口）", flush=True)
                _sleep(wait)
            else:
                if backoff_attempts >= len(RATE_LIMIT_RETRY_SLEEPS):
                    raise
                wait = RATE_LIMIT_RETRY_SLEEPS[backoff_attempts]
                backoff_attempts += 1
                print(f"限流（HTTP {e.code}）：退避 {wait} 秒後重試"
                      f"（第 {backoff_attempts}/{len(RATE_LIMIT_RETRY_SLEEPS)} 輪）", flush=True)
                _sleep(wait)


# ==================== 通用檔案快取 ====================

def _cache_path(*parts: str) -> str:
    return os.path.join(CACHE_ROOT, *parts)


def _cached_get(url: str, cache_file: str, sleep_after: float, timeout: int = 30):
    """檔案存在即讀快取（不重打）；否則打 API、寫入快取、sleep、回傳。"""
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read().decode("utf-8"))

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)

    if sleep_after:
        time.sleep(sleep_after)
    return raw


# ==================== 母體來源：FinMind TaiwanStockInfo ====================

def fetch_stock_info() -> list:
    """回傳 FinMind TaiwanStockInfo 全部列（含 stock_id/stock_name/type/industry_category）。
    快取到 data/universe_cache/finmind_stock_info.json（不含日期，母體名單視為可重打刷新的參考資料，
    但一旦快取存在即沿用，需要更新請手動刪除快取檔）。"""
    info_params = {"dataset": "TaiwanStockInfo"}
    if _finmind_token():
        info_params["token"] = _finmind_token()
    url = f"{FINMIND_URL}?{urllib.parse.urlencode(info_params)}"
    raw = _cached_get(url, _cache_path("finmind_stock_info.json"), FINMIND_SLEEP_SECONDS)
    return raw.get("data") or []


def build_universe_pool(stock_info_rows: list) -> dict:
    """母體：type ∈ {twse, tpex}，排除 emerging。同一 stock_id 若有多筆取第一筆（資料庫去重）。
    回傳 {stock_id: {stock_id, name, type, industry_category}}。"""
    pool = {}
    for row in stock_info_rows:
        t = row.get("type")
        if t not in ("twse", "tpex"):
            continue
        sid = row["stock_id"]
        if sid in pool:
            continue
        pool[sid] = {
            "stock_id": sid,
            "name": row.get("stock_name"),
            "type": t,
            "industry_category": row.get("industry_category"),
        }
    return pool


# ==================== TWSE 下市名單 ====================

_ROC_DATE_SEP = "/"


def _roc_to_iso(roc_date: str) -> str:
    """民國年/月/日 -> 'YYYY-MM-DD'。"""
    y, m, d = roc_date.split(_ROC_DATE_SEP)
    return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"


def fetch_twse_delisted() -> dict:
    """回傳 TWSE 上市股下市名單 {stock_id: delisting_date_iso}。快取到
    data/universe_cache/twse_delisted.json。"""
    raw = _cached_get(TWSE_DELISTED_URL, _cache_path("twse_delisted.json"), TWSE_SLEEP_SECONDS)
    out = {}
    for row in raw:
        code = row.get("Code")
        ddate = row.get("DelistingDate")
        if code and ddate:
            out[code] = _roc_to_iso(ddate)
    return out


# ==================== TWSE MI_INDEX 月底批次（上市股月底行情） ====================

def _month_end_calendar_day(year_month: str) -> datetime.date:
    y, m = int(year_month[:4]), int(year_month[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return datetime.date(ny, nm, 1) - datetime.timedelta(days=1)


def fetch_twse_mi_index_day(date_str: str):
    """打 TWSE MI_INDEX 單日全市場行情（date_str='YYYYMMDD'）。
    非交易日回傳 None（API 回應無 tables 鍵）。快取到
    data/universe_cache/twse_mi_index/{date_str}.json（含失敗標記，避免重複試探非交易日）。
    """
    cache_file = _cache_path("twse_mi_index", f"{date_str}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        return None if cached.get("_no_data") else cached

    url = f"{TWSE_MI_INDEX_URL}?response=json&date={date_str}&type=ALLBUT0999"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read().decode("utf-8"))

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    if "tables" not in raw or not raw.get("tables"):
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"_no_data": True}, f)
        time.sleep(TWSE_SLEEP_SECONDS)
        return None

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    time.sleep(TWSE_SLEEP_SECONDS)
    return raw


def find_month_end_trading_day(year_month: str, max_lookback_days: int = 10) -> str | None:
    """從該月最後一個日曆日往回找，找到第一個有資料（交易日）的日期，回傳 'YYYYMMDD'。
    找不到（連續 max_lookback_days 天都無資料）回傳 None。"""
    day = _month_end_calendar_day(year_month)
    for _ in range(max_lookback_days):
        date_str = day.strftime("%Y%m%d")
        result = fetch_twse_mi_index_day(date_str)
        if result is not None:
            return date_str
        day -= datetime.timedelta(days=1)
    return None


def parse_twse_mi_index_turnover(raw: dict) -> dict:
    """從 MI_INDEX 回應中取出「每日收盤行情(全部)」表格，回傳 {stock_id: turnover_ntd(float)}。
    成交金額欄位含千分位逗號，需清理。找不到該表格回傳空 dict。"""
    tables = raw.get("tables") or []
    target = None
    for t in tables:
        title = t.get("title") or ""
        if "每日收盤行情" in title:
            target = t
            break
    if target is None:
        return {}

    fields = target.get("fields") or []
    try:
        code_idx = fields.index("證券代號")
        turnover_idx = fields.index("成交金額")
    except ValueError:
        return {}

    out = {}
    for row in target.get("data") or []:
        code = row[code_idx].strip()
        turnover_raw = row[turnover_idx].replace(",", "").strip()
        try:
            out[code] = float(turnover_raw)
        except ValueError:
            continue
    return out


def fetch_twse_month_end_turnover(year_month: str) -> dict:
    """回傳某月 TWSE 全市場月底交易日成交金額 {stock_id: turnover_ntd}。
    找不到月底交易日（如超出資料範圍）回傳空 dict。"""
    date_str = find_month_end_trading_day(year_month)
    if date_str is None:
        return {}
    raw = fetch_twse_mi_index_day(date_str)
    if raw is None:
        return {}
    return parse_twse_mi_index_turnover(raw)


# ==================== FinMind 上櫃股逐檔行情 ====================

def fetch_finmind_price_history(stock_id: str, start_date: str, end_date: str | None = None) -> list:
    """抓某檔（上櫃股）FinMind TaiwanStockPrice 全歷史（一次拿全區間，本地切月）。
    快取到 data/universe_cache/finmind_price/{stock_id}__{start_date}.json（檔名含 start_date，
    避免 --current 的縮窗查詢快取被 --backfill 的完整歷史查詢誤用，反之亦然；
    若快取存在直接沿用，不因 end_date 變動重打——續跑優先，需要更新請刪快取檔）。"""
    cache_file = _cache_path("finmind_price", f"{stock_id}__{start_date}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        return cached.get("data") or []

    params = {"dataset": "TaiwanStockPrice", "data_id": stock_id, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    if _finmind_token():
        params["token"] = _finmind_token()
    url = f"{FINMIND_URL}?{urllib.parse.urlencode(params)}"
    # 限流韌性：402/403 依 RATE_LIMIT_RETRY_SLEEPS 退避重試（--paced 模式改睡到下個整點）
    raw = _open_json_with_retry(url, timeout=30)

    rows = raw.get("data") or []
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"start_date": start_date, "end_date": end_date, "data": rows}, f, ensure_ascii=False)

    time.sleep(FINMIND_SLEEP_SECONDS)
    return rows


def month_end_turnover_from_price_rows(rows: list, year_month: str) -> float | None:
    """從逐日行情列（FinMind 格式 {date, Trading_money, ...}）取出該月「月底交易日」的成交金額。
    月底交易日＝該月最後一筆有資料的交易日（非日曆月底，因逐日資料本身只含實際交易日）。
    查無該月資料回傳 None。"""
    month_rows = [r for r in rows if r.get("date", "").startswith(year_month)]
    if not month_rows:
        return None
    last_row = max(month_rows, key=lambda r: r["date"])
    money = last_row.get("Trading_money")
    return float(money) if money is not None else None


def first_price_month_from_rows(rows: list) -> str | None:
    """從逐日行情列中取出最早可見的 'YYYY-MM'。查無資料回傳 None。"""
    dates = [r.get("date") for r in rows if r.get("date")]
    if not dates:
        return None
    return min(dates)[:7]


def months_before(year_month: str, n: int) -> str:
    """回傳 year_month 往前推 n 個月的 'YYYY-MM'。"""
    y, m = int(year_month[:4]), int(year_month[5:7])
    total = y * 12 + (m - 1) - n
    yy, mm = divmod(total, 12)
    return f"{yy:04d}-{mm + 1:02d}"


# ==================== 三規則篩選（純函式，供測試直接驗證） ====================

def passes_listing_length(first_price_month: str | None, as_of_month: str,
                           min_months: int = MIN_LISTING_MONTHS) -> bool:
    """規則 1：first_price_month 到 as_of_month 的月數差 ≥ min_months。
    first_price_month 為 None（查無價格資料）視為不通過。

    用於上櫃股（有完整歷史逐日資料可精確算出 first_price_month）。
    上市股在 build_snapshot 中改用 passes_listing_length_by_probe（探測點存在性），
    因上市股逐檔打 FinMind 抓歷史成本過高，見該函式 docstring。"""
    if not first_price_month:
        return False
    fy, fm = int(first_price_month[:4]), int(first_price_month[5:7])
    ay, am = int(as_of_month[:4]), int(as_of_month[5:7])
    months_diff = (ay - fy) * 12 + (am - fm)
    return months_diff >= min_months


def passes_listing_length_by_probe(existed_at_probe: bool | None) -> bool:
    """規則 1（上市股版本）：只在『as_of 往前推 MIN_LISTING_MONTHS 個月』的月底檢查該股
    是否已出現在 TWSE MI_INDEX 批次行情中，用存在性代替精確首月，避免對每檔上市股
    逐檔打 FinMind 抓完整歷史（2000+ 檔 × 1 次 = 不必要的高成本，與批次優先架構相悖）。
    誠實限制：不確定該股精確首次上市月份，只確認『至少在探測點就已存在』；
    existed_at_probe 為 None（該探測月 TWSE 無資料，如超出可回溯範圍）視為不通過。"""
    return bool(existed_at_probe)


def passes_liquidity(turnovers: list, floor: float = MONTH_END_TURNOVER_FLOOR) -> bool:
    """规则 2：近 3 個月月底交易日成交金額皆 ≥ floor。
    turnovers 為近 3 個月的成交金額列表（None 表示該月查無資料，視為不通過）；
    長度不足 3（如新股資料不足 3 個月）視為不通過。"""
    if len(turnovers) < 3:
        return False
    return all(t is not None and t >= floor for t in turnovers)


def passes_industry(industry_category: str | None,
                     allowed: frozenset = INDUSTRY_ALLOWED) -> bool:
    """規則 3：industry_category ∈ allowed。"""
    return industry_category in allowed


# ==================== 組裝月快照 ====================

def _prev_year_months(year_month: str, n: int) -> list:
    """回傳含 year_month 本身在內、往前數 n 個月的 'YYYY-MM' 列表（由舊到新）。"""
    y, m = int(year_month[:4]), int(year_month[5:7])
    months = []
    for i in range(n - 1, -1, -1):
        total = y * 12 + (m - 1) - i
        yy, mm = divmod(total, 12)
        months.append(f"{yy:04d}-{mm + 1:02d}")
    return months


def build_snapshot(year_month: str, stock_info_rows: list | None = None,
                    delisted: dict | None = None,
                    price_history_fetcher=None,
                    twse_turnover_fetcher=None,
                    tpex_price_start: str | None = None) -> dict:
    """為 year_month 組裝 universe 篩選結果（不寫檔，純組裝，供測試與 CLI 共用）。

    price_history_fetcher(stock_id, start_date, end_date) -> list  （上櫃股逐檔行情，預設走網路）
    twse_turnover_fetcher(year_month) -> {stock_id: turnover}       （上市股月底行情，預設走網路）
    tpex_price_start：FinMind 逐檔查詢起始日；None 則用完整歷史起點 '2000-01-01'（--backfill 適用）；
      傳入較晚日期（如 as_of 往前 15 個月）可縮小 --current 的查詢負載，但此時上櫃股的
      first_price_month 只在『探測點月份仍落在查詢窗口內』時才可信判斷上市時長，
      若探測點早於查詢窗口起點，改採「窗口內有資料即視為已通過規則1」的保守近似
      （見 passes_listing_length_by_probe，邏輯與上市股一致，避免因縮窗導致誤判為新股）。

    上市股（type=twse）：規則1/2 皆用 TWSE MI_INDEX 批次行情（近3個月流動性 + 1個探測點判斷上市時長），
      不逐檔打 FinMind，維持批次優先架構；first_price_month 記錄為
      「探測點月份」而非精確首月（見 passes_listing_length_by_probe 誠實限制）。
    上櫃股（type=tpex）：規則1/2 皆用 FinMind 逐檔行情；探測點落在查詢窗口內時可精確判斷，
      否則採探測點存在性近似（見上）。

    回傳欄位：as_of、rules_version、各層通過清單與計數、每檔的
    {stock_id, name, type, industry, month_end_turnover, first_price_month, delisted}。
    """
    if stock_info_rows is None:
        stock_info_rows = fetch_stock_info()
    if delisted is None:
        delisted = fetch_twse_delisted()
    if price_history_fetcher is None:
        price_history_fetcher = fetch_finmind_price_history
    if twse_turnover_fetcher is None:
        twse_turnover_fetcher = fetch_twse_month_end_turnover

    pool = build_universe_pool(stock_info_rows)

    recent_3_months = _prev_year_months(year_month, 3)
    probe_month = months_before(year_month, MIN_LISTING_MONTHS)
    price_start = tpex_price_start or "2000-01-01"
    # 查詢窗口是否涵蓋探測點：涵蓋則可精確判斷「探測點當時是否已有交易」，
    # 未涵蓋（如縮窗只抓近15個月但探測點在12個月前，仍在窗口內；只有回填更短窗口時才會不涵蓋）。
    probe_within_window = price_start <= f"{probe_month}-01"

    # 上市股：TWSE 月底批次行情——近3個月（流動性）+ 探測月（上市時長），共 4 次 TWSE 呼叫。
    twse_turnover_by_month = {ym: twse_turnover_fetcher(ym) for ym in recent_3_months}
    twse_probe_turnover = twse_turnover_fetcher(probe_month)

    records = {}
    rule1_flags = {}
    fetch_errors = {}

    tpex_total = sum(1 for info in pool.values() if info["type"] == "tpex")
    tpex_done = 0

    def _cached_price_file_count() -> int:
        d = _cache_path("finmind_price")
        try:
            return len(os.listdir(d))
        except OSError:
            return 0

    for sid, info in pool.items():
        if info["type"] == "twse":
            turnovers = [twse_turnover_by_month[ym].get(sid) for ym in recent_3_months]
            existed_at_probe = sid in twse_probe_turnover
            first_month = probe_month if existed_at_probe else None
            rule1_flags[sid] = passes_listing_length_by_probe(existed_at_probe)
        else:  # tpex
            tpex_done += 1
            if tpex_done % PROGRESS_PRINT_EVERY == 0:
                print(f"上櫃股進度：{tpex_done}/{tpex_total}"
                      f"（fetch_error 累計 {len(fetch_errors)}；"
                      f"finmind_price 快取檔數 {_cached_price_file_count()}）", flush=True)
            # 個股抓取失敗（如 FinMind 限流）不可讓整批中止：顯式記錄 fetch_error，
            # 該檔不計入任何規則的「通過」，也不當作「已知不通過」，避免與真實剔除原因混淆
            # （ADR 0005 不捏造、失敗即顯——查無資料時顯性標記缺值，不可靜默當成篩選結果）。
            try:
                rows = price_history_fetcher(sid, price_start, None)
            except Exception as e:
                fetch_errors[sid] = str(e)
                records[sid] = {
                    "stock_id": sid,
                    "name": info["name"],
                    "type": info["type"],
                    "industry": info["industry_category"],
                    "month_end_turnover": [None, None, None],
                    "first_price_month": None,
                    "delisted": sid in delisted,
                    "fetch_error": str(e),
                }
                rule1_flags[sid] = False
                continue

            earliest_in_window = first_price_month_from_rows(rows)
            if probe_within_window:
                first_month = earliest_in_window
                rule1_flags[sid] = passes_listing_length(first_month, year_month)
            else:
                existed_at_probe = any(
                    r.get("date", "").startswith(probe_month) for r in rows
                )
                first_month = earliest_in_window
                rule1_flags[sid] = passes_listing_length_by_probe(existed_at_probe)
            turnovers = [month_end_turnover_from_price_rows(rows, ym) for ym in recent_3_months]

        is_delisted = sid in delisted
        records[sid] = {
            "stock_id": sid,
            "name": info["name"],
            "type": info["type"],
            "industry": info["industry_category"],
            "month_end_turnover": turnovers,
            "first_price_month": first_month,
            "delisted": is_delisted,
        }

    pool_ids = list(records.keys())
    rule1_pass = [sid for sid in pool_ids if rule1_flags[sid]]
    rule2_pass = [sid for sid in rule1_pass
                  if passes_liquidity(records[sid]["month_end_turnover"])]
    rule3_pass = [sid for sid in rule2_pass
                  if passes_industry(records[sid]["industry"])]

    return {
        "as_of": year_month,
        "rules_version": RULES_VERSION,
        "pool_count": len(pool_ids),
        "rule1_listing_length_count": len(rule1_pass),
        "rule2_liquidity_count": len(rule2_pass),
        "rule3_industry_count": len(rule3_pass),
        "final_pass": sorted(rule3_pass),
        "records": records,
        "fetch_error_count": len(fetch_errors),
        "fetch_errors": fetch_errors,
        # provisional 政策（ADR 0007）：有任何抓取失敗的快照為「暫定」，允許之後重跑覆蓋補齊；
        # fetch_error_count == 0 的快照才受完整不可變鐵律保護。
        "provisional": len(fetch_errors) > 0,
    }


def snapshot_is_provisional(payload: dict) -> bool:
    """判定既有快照是否為暫定（provisional）快照。

    暫定 = 顯式 provisional 旗標為真，或 fetch_error_count > 0（相容早期未寫入
    provisional 欄位、但含缺值的快照，如 2026-06 首次實跑的 850 缺值快照）。
    暫定快照允許被重跑覆蓋（重跑會利用快取只補失敗的檔）；完整快照維持不可變鐵律。"""
    if payload.get("provisional"):
        return True
    return (payload.get("fetch_error_count") or 0) > 0


def write_snapshot(year_month: str, snapshot: dict | None = None, root: str = SNAPSHOT_ROOT,
                    tpex_price_start: str | None = None) -> str:
    """組裝（若未提供）並寫入 universe 月快照。

    重建政策（ADR 0007）：
    - 目標檔不存在 → 直接寫入。
    - 目標檔存在且為 provisional（見 snapshot_is_provisional）→ 允許覆蓋重建
      （限流等原因造成缺值的暫定快照，重跑補齊是預期操作，不算違反不可變鐵律）。
    - 目標檔存在且為完整快照（fetch_error_count == 0 且無 provisional 旗標）→
      沿用 pit_store append-only 鐵律，raise SnapshotExistsError。
    """
    if snapshot is None:
        snapshot = build_snapshot(year_month, tpex_price_start=tpex_price_start)

    existing_path = os.path.join(root, year_month, "universe.json")
    if os.path.exists(existing_path):
        with open(existing_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if snapshot_is_provisional(existing):
            os.remove(existing_path)  # 暫定快照：允許重建
        # 完整快照：不刪，落到 pit_store 觸發 SnapshotExistsError（單一鐵律出口）

    return pit_store.write_monthly_snapshot("universe", snapshot, year_month=year_month, root=root)


# ==================== CLI ====================

def _latest_closed_month(today: datetime.date | None = None) -> str:
    """回傳「最新已收月」= 上個自然月（避免當月尚未走完）。"""
    if today is None:
        today = datetime.date.today()
    y, m = today.year, today.month
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{py:04d}-{pm:02d}"


def _month_range(start: str, end: str) -> list:
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    months = []
    total_start = sy * 12 + (sm - 1)
    total_end = ey * 12 + (em - 1)
    for total in range(total_start, total_end + 1):
        yy, mm = divmod(total, 12)
        months.append(f"{yy:04d}-{mm + 1:02d}")
    return months


def cmd_status(root: str = SNAPSHOT_ROOT):
    if not os.path.isdir(root):
        print("尚無任何快照。")
        return
    months = sorted(
        entry for entry in os.listdir(root)
        if os.path.isfile(os.path.join(root, entry, "universe.json"))
    )
    print(f"已建立 universe 快照月份數：{len(months)}")
    if months:
        print(f"最早：{months[0]}　最新：{months[-1]}")
        latest = json.load(open(os.path.join(root, months[-1], "universe.json"), encoding="utf-8"))
        print(f"最新月（{months[-1]}）通過統計：母體={latest['pool_count']} "
              f"→ 規則1={latest['rule1_listing_length_count']} "
              f"→ 規則2={latest['rule2_liquidity_count']} "
              f"→ 規則3={latest['rule3_industry_count']}")


CURRENT_TPEX_LOOKBACK_MONTHS = 15
"""--current 用途：上櫃股 FinMind 查詢只回溯此月數（涵蓋 MIN_LISTING_MONTHS=12 探測點
＋ 3 個月流動性窗口的緩衝），減少單次執行的請求負載。--backfill 仍用完整歷史起點。"""


def cmd_current():
    ym = _latest_closed_month()
    tpex_start_month = months_before(ym, CURRENT_TPEX_LOOKBACK_MONTHS)
    tpex_price_start = f"{tpex_start_month}-01"
    print(f"產生最新已收月快照：{ym}（上櫃股 FinMind 查詢起點縮至 {tpex_price_start}）")
    try:
        path = write_snapshot(ym, tpex_price_start=tpex_price_start)
        print(f"已寫入：{path}")
    except pit_store.SnapshotExistsError as e:
        print(f"略過（已存在完整快照，不可覆寫；provisional 快照才允許重建）：{e}")


def cmd_backfill(start: str, end: str):
    months = _month_range(start, end)
    print(f"回填範圍：{start} ~ {end}（共 {len(months)} 個月）")
    for i, ym in enumerate(months, 1):
        target = os.path.join(SNAPSHOT_ROOT, ym, "universe.json")
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not snapshot_is_provisional(existing):
                print(f"[{i}/{len(months)}] {ym} 已存在（完整快照），略過")
                continue
            print(f"[{i}/{len(months)}] {ym} 已存在但為 provisional"
                  f"（fetch_error_count={existing.get('fetch_error_count')}），重跑補齊...")
        else:
            print(f"[{i}/{len(months)}] {ym} 產生中...")
        try:
            path = write_snapshot(ym)  # 完整歷史起點，逐月精確計算
            print(f"[{i}/{len(months)}] {ym} 已寫入：{path}")
        except Exception as e:
            print(f"[{i}/{len(months)}] {ym} 失敗：{e}（可重跑續跑，已快取的部分不會重打）")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Universe 客觀化全市場篩選管線（ADR 0007）")
    parser.add_argument("--current", action="store_true", help="產最新已收月快照")
    parser.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                         help="逐月回填，如 --backfill 2015-01 2026-06")
    parser.add_argument("--status", action="store_true", help="已建快照統計")
    parser.add_argument("--paced", action="store_true",
                         help="限流時進入每小時窗口模式（睡到下個整點再續），供無人值守長回填")
    args = parser.parse_args()

    set_paced_mode(args.paced)

    if args.current:
        cmd_current()
    elif args.backfill:
        cmd_backfill(args.backfill[0], args.backfill[1])
    elif args.status:
        cmd_status()
    else:
        parser.print_help()
