import os
import datetime
from typing import Dict, List, Any, Optional
import numpy as np
import pit_store

# 非共識黃金建倉標的的 pre-registered 先驗門檻（見 CONTEXT.md / ADR 0003）——禁止用回測 tune
CONSENSUS_MAX = 60.0       # 共識度上限：< 此值才算「逆勢/未擁擠」
BACKLOG_LEAD_MIN = 50.0    # 設備 Backlog 領先門檻：> 此值才算「領先已動」
DOWNSTREAM_YOY_MAX = 15.0  # 下游當月營收 YoY 上限：< 此值才算「基本面未現/拐點前」

_PRIORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "priors", "content_value.json")


def _strip_suffix(company_id: str) -> str:
    """去除 .TW / .TWO 後綴，取得 PIT 快照使用的純數字代碼。"""
    for sfx in (".TWO", ".TW"):
        if company_id.endswith(sfx):
            return company_id[: -len(sfx)]
    return company_id


class MarketInformationMonitor:
    """
    12-18 個月至 18-24 個月超前中期投資核心資訊監控與量化資料引擎。

    Stage 2（當前）: 三個自有訊號均以真實 PIT 月快照（data/snapshots/）驅動：
    - Backlog Lead = segment=equipment 公司真實月營收 YoY 中位數
    - Consensus    = 外資持股% 歷史百分位 + 橫斷面同儕排名等權混合
    - 個股 YoY 曲線 = 真實 PIT 月營收 yoy_pct，未來 3 個月為投影
    """

    def __init__(self):
        _priors = pit_store.load_content_value_priors(_PRIORS_PATH)
        self.generation_specs = _priors["generation_specs"]
        self._eras = _priors["eras"]
        self.real_revenue_cache = None

    # ==================== 供應鏈矩陣 ====================

    def get_point_in_time_matrix(self, as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        依 as_of_date 回傳當時的供應鏈標的選股池（PIT，杜絕 look-ahead bias）。
        - 2015-2019：早期世代（6 支）
        - 2020-2022：Hopper 世代（9 支）
        - 2023-2024：Blackwell 世代（10 支）
        - 2025-2026：Feynman 世代（12 支）
        """
        if as_of_date:
            today = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()
        else:
            today = datetime.date.today()

        for era in self._eras:
            until = era.get("until")
            if until is None or today <= datetime.datetime.strptime(until, "%Y-%m-%d").date():
                return era["companies"]
        return self._eras[-1]["companies"]

    # ==================== 高頻報價（仍為合成模擬，非真實資料）====================

    def get_high_frequency_pricing(self, sector: str, as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """合成高頻報價趨勢；支援 as_of_date 截斷。"""
        if as_of_date:
            today = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()
        else:
            today = datetime.date.today()

        dates = [today - datetime.timedelta(weeks=i) for i in range(12)][::-1]
        base_price = 150.0
        prices = []
        for idx in range(12):
            if idx < 5:
                price = base_price - idx * 0.8
            elif idx < 9:
                price = base_price - 4.0 + (idx - 5) * 1.2
            else:
                price = base_price + 0.8 + (idx - 9) * 3.5
            prices.append(round(price, 2))

        weekly_data = [{"date": d.strftime("%Y-%m-%d"), "price": p} for d, p in zip(dates, prices)]
        recent_change = (prices[-1] - prices[-4]) / prices[-4] * 100
        trend = "rising" if recent_change > 1.5 else ("declining" if recent_change < -1.5 else "stable")

        return {
            "sector": sector,
            "metric_name": "Next-Gen Package Equipment Material Index",
            "trend": trend,
            "weekly_change_pct": round(recent_change, 2),
            "data_points": weekly_data,
            "catalyst_triggered": trend == "rising",
        }

    # ==================== 供應鏈洗牌時程 ====================

    def get_supply_chain_schedule(self, current_gen: str, next_gen: str,
                                  as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """推演世代更迭下的供應鏈洗牌，含 Feynman_Next 替代風險。"""
        analysis = []
        bottlenecks = []

        matrix = self.get_point_in_time_matrix(as_of_date)
        for item in matrix:
            val_current = item["content_value_by_gen"].get(current_gen, 0.0)
            val_next    = item["content_value_by_gen"].get(next_gen, 0.0)
            val_future  = item["content_value_by_gen"].get("Feynman_Next", 0.0)

            change_pct        = (val_next - val_current) / val_current * 100 if val_current > 0 else 999.0
            future_change_pct = (val_future - val_next)  / val_next    * 100 if val_next    > 0 else 999.0

            substitution_risk = "LOW"
            if val_future < val_next * 0.7:
                substitution_risk = "HIGH (Content Value Erosion / Substitution)"
            elif val_future > val_next * 1.4:
                substitution_risk = "NONE (Content Value Expanding)"

            # 動態共識度（有資料用真實，否則 fallback 靜態先驗）
            consensus = self._compute_consensus(item["company_id"], as_of_date)
            if consensus is None:
                consensus = item["consensus_score"]

            analysis.append({
                "company_id": item["company_id"],
                "name": item["name"],
                "segment": item["segment"],
                "content_value_current": val_current,
                "content_value_next": val_next,
                "content_value_future": val_future,
                "change_pct": round(change_pct, 2),
                "future_change_pct": round(future_change_pct, 2),
                "consensus_score": consensus,
                "status": item["status"],
                "timeline": item["timeline"],
                "substitution_risk_future": substitution_risk,
            })

            if item["segment"] in ["equipment", "package"]:
                bottlenecks.append(f"{item['name']} ({item['segment']})")

        return {
            "current_generation": current_gen,
            "next_generation": next_gen,
            "future_generation": "Feynman_Next",
            "bottlenecks": bottlenecks,
            "timeline_matrix": analysis,
        }

    # ==================== TWSE 最新月營收（保留供測試 / fallback）====================

    def fetch_real_monthly_revenue(self) -> Dict[str, Dict[str, Any]]:
        """從 TWSE 開放 API 下載最新月份上市/上櫃公司營收匯總（僅當月快照）。"""
        if self.real_revenue_cache is not None:
            return self.real_revenue_cache

        import urllib.request
        import json

        urls = [
            "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
            "https://openapi.twse.com.tw/v1/opendata/t187ap05_P",
        ]
        revenue_map = {}
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
                for row in data:
                    company_code = row.get("公司代號", "").strip()
                    if not company_code:
                        continue
                    try:
                        revenue_yoy = float(row.get("營業收入-去年同月增減(%)", "0.0"))
                    except ValueError:
                        revenue_yoy = 0.0
                    try:
                        rev_val = float(row.get("營業收入-當月營收", "0")) / 100000.0
                    except ValueError:
                        rev_val = 0.0
                    revenue_map[company_code] = {
                        "revenue_billion": round(rev_val, 2),
                        "yoy_pct": round(revenue_yoy, 2),
                        "date_ym": row.get("資料年月", "").strip(),
                        "company_name": row.get("公司名稱", "").strip(),
                    }
            except Exception as e:
                print(f"[WARN] Cannot fetch real revenue from {url}: {e}")

        self.real_revenue_cache = revenue_map
        return revenue_map

    # ==================== PIT 快照輔助函式 ====================

    def _read_company_revenue_history(self, company_id: str,
                                      as_of_date_str: Optional[str],
                                      n_snapshots: int = 14) -> list:
        """
        從 data/snapshots/ 讀取最近 n_snapshots 個月快照，回傳按 period 排序的唯一營收記錄。
        日粒度 PIT：只納入 announce_date <= as_of_date_str 的記錄。
        每筆: {'period': 'YYYY-MM', 'revenue_billion': float, 'yoy_pct': float|None}
        """
        sid = _strip_suffix(company_id)
        as_of_cutoff = as_of_date_str or datetime.date.today().strftime("%Y-%m-%d")
        as_of_ym = as_of_cutoff[:7]

        periods: Dict[str, dict] = {}
        year, month = int(as_of_ym[:4]), int(as_of_ym[5:7])
        for _ in range(n_snapshots):
            ym = f"{year:04d}-{month:02d}"
            snap = pit_store.read_snapshot("revenue", f"{ym}-28")
            if snap and sid in snap:
                rec = snap[sid]
                period = rec.get("period", "")
                announce_date = rec.get("announce_date", "")
                if (period and period not in periods
                        and announce_date and announce_date <= as_of_cutoff):
                    periods[period] = {
                        "period": period,
                        "revenue_billion": rec.get("revenue_billion", 0.0),
                        "yoy_pct": rec.get("yoy_pct"),
                    }
            month -= 1
            if month == 0:
                month = 12
                year -= 1

        return sorted(periods.values(), key=lambda r: r["period"])

    def get_backlog_lead(self, as_of_date: Optional[str] = None) -> float:
        """
        板塊 segment=equipment 公司真實月營收 YoY 中位數（日粒度 PIT 正確）。
        此為 ADR 0006 定義的 Equipment Backlog Lead 訊號（誠實限制：是「動能代理」而非真訂單）。
        資料不足時回傳 0.0。
        """
        matrix = self.get_point_in_time_matrix(as_of_date)
        equipment_cids = [it["company_id"] for it in matrix if it["segment"] == "equipment"]

        yoy_values = []
        for cid in equipment_cids:
            # 用 _read_company_revenue_history 保證日粒度 PIT 正確（announce_date 過濾）
            hist = self._read_company_revenue_history(cid, as_of_date, n_snapshots=3)
            if hist and hist[-1].get("yoy_pct") is not None:
                yoy_values.append(hist[-1]["yoy_pct"])

        if not yoy_values:
            return 0.0
        return round(float(np.median(yoy_values)), 2)

    def _read_price_history(self, company_id: str, as_of_date_str: Optional[str],
                            n_months: int = 13) -> list:
        """
        從 PIT 股價快照讀取最近 n_months 個月收盤價。
        PIT 規則：close_date（月底）<= as_of_date_str 才可見。
        回傳 [(year_month 'YYYY-MM', close float), ...] 由新到舊。
        """
        sid = _strip_suffix(company_id)
        as_of_cutoff = as_of_date_str or datetime.date.today().strftime("%Y-%m-%d")
        as_of_ym = as_of_cutoff[:7]

        result: dict = {}
        year, month = int(as_of_ym[:4]), int(as_of_ym[5:7])
        for _ in range(n_months + 1):
            ym = f"{year:04d}-{month:02d}"
            snap = pit_store.read_snapshot("prices", f"{ym}-28")
            if snap and sid in snap:
                rec = snap[sid]
                close_date = rec.get("close_date", "")
                if close_date and close_date <= as_of_cutoff and ym not in result:
                    result[ym] = rec["close"]
            month -= 1
            if month == 0:
                month = 12
                year -= 1

        return sorted(result.items(), key=lambda x: x[0], reverse=True)

    def _compute_price_consensus(self, company_id: str,
                                 as_of_date: Optional[str] = None) -> Optional[float]:
        """
        股價 Consensus 部分（0-100）：
        (a) 自身 12M 歷史百分位（當前收盤在近 12M 的位置；高=接近年高=擁擠）
        (b) 橫斷面同儕排名：各同儕計算各自 own 12M percentile，再對本公司排名
            （比較「相對年高位置」，避免跨股直接比較絕對股價無意義）
        資料不足（< 6 個月）時回傳 None。
        """
        own_history = self._read_price_history(company_id, as_of_date, n_months=13)
        if len(own_history) < 6:
            return None

        closes = [c for _, c in own_history]
        current_close = closes[0]
        own_pct = sum(1 for c in closes if c <= current_close) / len(closes) * 100

        peer_own_pcts = [own_pct]
        for it in self.get_point_in_time_matrix(as_of_date):
            p_cid = it["company_id"]
            if _strip_suffix(p_cid) == _strip_suffix(company_id):
                continue
            p_hist = self._read_price_history(p_cid, as_of_date, n_months=13)
            if len(p_hist) < 3:
                continue
            p_closes = [c for _, c in p_hist]
            p_cur = p_closes[0]
            p_pct = sum(1 for c in p_closes if c <= p_cur) / len(p_closes) * 100
            peer_own_pcts.append(p_pct)

        peer_rank = sum(1 for p in peer_own_pcts if p <= own_pct) / len(peer_own_pcts) * 100
        return round((own_pct + peer_rank) / 2, 1)

    def _compute_consensus(self, company_id: str,
                           as_of_date: Optional[str] = None) -> Optional[float]:
        """
        完整 Consensus Score（0-100）：持股% + 股價兩個子訊號等權混合。
        各子訊號 = (自身 12M 歷史百分位 + 橫斷面同儕排名) / 2（ADR 0006）。
        若股價快照不可得，退化為僅持股%；若兩者皆不足，回傳 None（呼叫端 fallback 靜態先驗）。
        """
        sid = _strip_suffix(company_id)
        as_of_str = as_of_date or datetime.date.today().strftime("%Y-%m-%d")
        as_of_ym = as_of_str[:7]

        # ---- 持股% 部分 ----
        history_ratios: list = []
        year, month = int(as_of_ym[:4]), int(as_of_ym[5:7])
        for _ in range(12):
            ym = f"{year:04d}-{month:02d}"
            snap = pit_store.read_snapshot("holdings", f"{ym}-28")
            if snap and sid in snap:
                ratio = snap[sid].get("foreign_ratio")
                if ratio is not None:
                    history_ratios.append(ratio)
            month -= 1
            if month == 0:
                month = 12
                year -= 1

        if len(history_ratios) < 6:
            return None

        current_ratio = history_ratios[0]
        own_hold_pct = sum(1 for v in history_ratios if v <= current_ratio) / len(history_ratios) * 100

        latest_snap = pit_store.read_snapshot("holdings", f"{as_of_ym}-28")
        peer_ratios: list = []
        if latest_snap:
            for it in self.get_point_in_time_matrix(as_of_date):
                p_sid = _strip_suffix(it["company_id"])
                rec = latest_snap.get(p_sid)
                if rec and rec.get("foreign_ratio") is not None:
                    peer_ratios.append(rec["foreign_ratio"])

        hold_peer_rank = (sum(1 for r in peer_ratios if r <= current_ratio) / len(peer_ratios) * 100
                          if peer_ratios else own_hold_pct)

        holdings_consensus = (own_hold_pct + hold_peer_rank) / 2

        # ---- 股價部分（有快照就加入；無則僅用持股%）----
        price_consensus = self._compute_price_consensus(company_id, as_of_date)

        if price_consensus is not None:
            return round((holdings_consensus + price_consensus) / 2, 1)
        return round(holdings_consensus, 1)

    # ==================== 核心訊號：真實 PIT 營收拐點 ====================

    def simulate_revenue_inflection(self, company_ids: List[str],
                                    as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """
        個股月營收 YoY 拐點與設備 Backlog 領先訊號。

        Stage 2 改動：
        - 歷史 YoY 曲線（索引 0-8）= 真實 PIT 快照 yoy_pct（非 sin 合成）
        - 未來 3 個月（索引 9-11）= 投影（以末尾 YoY × 加速係數）
        - Backlog Lead = 板塊 equipment 公司真實 YoY 中位數（非隨機合成）
        - Consensus = 外資持股% 歷史百分位 + 同儕排名（fallback 至靜態先驗）
        真實資料不足（< 3 筆）時 fallback 合成，並標記 has_real_data=False。
        """
        results = {}
        today = (datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()
                 if as_of_date else datetime.date.today())

        # 板塊 equipment 真實 Backlog Lead（一次算好，所有個股共用）
        sector_backlog_yoy = self.get_backlog_lead(as_of_date)
        equipment_lead_active_global = sector_backlog_yoy > BACKLOG_LEAD_MIN

        matrix = self.get_point_in_time_matrix(as_of_date)

        for cid in company_ids:
            item = next((x for x in matrix if x["company_id"] == cid), None)
            if not item:
                continue
            name, segment = item["name"], item["segment"]

            rev_hist = self._read_company_revenue_history(cid, as_of_date, n_snapshots=14)
            has_real = len(rev_hist) >= 3

            if has_real:
                yoy_recs = [r for r in rev_hist if r["yoy_pct"] is not None]
                real_yoy_9 = [r["yoy_pct"] for r in yoy_recs[-9:]]
                while len(real_yoy_9) < 9:
                    real_yoy_9.insert(0, 0.0)

                last_actual_rev   = rev_hist[-1]["revenue_billion"]
                latest_real_period = rev_hist[-1]["period"]
                latest_real_yoy   = yoy_recs[-1]["yoy_pct"] if yoy_recs else 0.0

                current_year_revs = [r["revenue_billion"] for r in rev_hist[-9:]]
                while len(current_year_revs) < 9:
                    current_year_revs.insert(0, 0.0)
            else:
                import hashlib
                _seed = int(hashlib.md5(f"{cid}_{as_of_date or 'live'}".encode()).hexdigest(), 16) % (2**32)
                _rng = np.random.default_rng(_seed)
                base = 600.0 if segment != "equipment" else 250.0
                ly = [round(base * (1 + np.sin(i / 3) * 0.1 - 0.20), 1) for i in range(12)]
                cy = [round(base * (1 + np.sin(i / 3) * 0.08 - 0.15), 1) for i in range(9)]
                real_yoy_9 = [round((c - l) / l * 100, 2) if l > 0 else 0.0
                              for c, l in zip(cy, ly[:9])]
                last_actual_rev    = cy[-1]
                latest_real_period = ""
                latest_real_yoy    = real_yoy_9[-1] if real_yoy_9 else 0.0
                current_year_revs  = cy

            # 未來 3 個月投影
            scales = [1.05, 1.15, 1.35] if segment != "equipment" else [1.10, 1.25, 1.50]
            future_rev = [round(last_actual_rev * s, 1) for s in scales]
            all_current_year = list(current_year_revs) + future_rev  # 12 values

            last_yoy = real_yoy_9[-1]
            future_yoy_proj = [round(last_yoy * s, 2) for s in scales]
            yoy_curve = real_yoy_9 + future_yoy_proj  # 12 values

            # 歷史基期（逆推）
            historical_base = []
            for i in range(9):
                rev = all_current_year[i]
                y   = real_yoy_9[i]
                denom = 1 + y / 100
                historical_base.append(round(rev / denom, 1) if denom > 0.01 else round(rev * 0.8, 1))
            historical_base += [round(all_current_year[i] * 0.75, 1) for i in range(9, 12)]

            future_yoy = yoy_curve[-3:]
            inflection_expected = future_yoy[-1] > future_yoy[0] and future_yoy[-1] > 20.0

            max_yoy_idx = int(np.argmax(yoy_curve[-3:])) + 9
            peak_yoy_val = yoy_curve[max_yoy_idx]
            peak_month = (today + datetime.timedelta(days=30 * (max_yoy_idx - 8))).strftime("%Y-%m")

            consensus = self._compute_consensus(cid, as_of_date)
            if consensus is None:
                consensus = item["consensus_score"]

            results[cid] = {
                "name": name,
                "segment": segment,
                "inflection_expected": inflection_expected,
                "peak_month": peak_month,
                "projected_peak_yoy_pct": peak_yoy_val,
                "last_month_yoy": yoy_curve[8],
                "future_3m_yoy": future_yoy,
                "consensus_score": consensus,
                "has_real_data": has_real,
                "real_date_ym": latest_real_period,
                "real_revenue_billion": last_actual_rev if has_real else None,
                "real_yoy_pct": latest_real_yoy if has_real else None,
                "equipment_lead_active": equipment_lead_active_global,
                "current_backlog_yoy_pct": sector_backlog_yoy,
                "backlog_yoy_curve_3m": [sector_backlog_yoy] * 3,
                "is_golden_accumulation_target": (
                    consensus < CONSENSUS_MAX
                    and equipment_lead_active_global
                    and yoy_curve[8] < DOWNSTREAM_YOY_MAX
                ),
                "historical_base": historical_base,
                "current_projected": all_current_year,
            }

        return results


if __name__ == "__main__":
    monitor = MarketInformationMonitor()
    print("=== 供應鏈洗牌（Vera_Rubin → Feynman）===")
    sched = monitor.get_supply_chain_schedule("Vera_Rubin", "Feynman")
    for item in sched["timeline_matrix"][:3]:
        print(f"  {item['name']}: CV {item['content_value_current']}→{item['content_value_next']}, "
              f"Consensus={item['consensus_score']}")

    print("\n=== Backlog Lead ===")
    print(f"  Equipment YoY 中位數: {monitor.get_backlog_lead()}")

    print("\n=== 營收拐點（前 3 支）===")
    matrix = monitor.get_point_in_time_matrix()
    cids = [it["company_id"] for it in matrix[:3]]
    res = monitor.simulate_revenue_inflection(cids)
    for cid, data in res.items():
        print(f"  {data['name']}({cid}): has_real={data['has_real_data']}, "
              f"last_yoy={data['last_month_yoy']}, backlog={data['current_backlog_yoy_pct']}, "
              f"consensus={data['consensus_score']}, golden={data['is_golden_accumulation_target']}")
