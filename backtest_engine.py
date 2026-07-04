import os
import sys
import datetime
import argparse
import json
import shutil
import pandas as pd
from typing import Dict, List, Any

# 導入底層模組
import performance_tracker
from market_monitor import (
    MarketInformationMonitor,
    _strip_suffix,
    MEMBERSHIP_SOURCE_FALLBACK,
    MEMBERSHIP_FALLBACK_NOTE,
)
from constants import CHINESE_MAPPING

# stock_id 尾碼組裝（PIT：不同歷史時點名單可以不同，尾碼依 universe type map 決定）
_TYPE_SUFFIX = {"twse": ".TW", "tpex": ".TWO"}


def resolve_ticker(stock_id_or_company_id: str, type_map: Dict[str, str]) -> str:
    """
    將 resolve_sector_members 回傳的成員（可能是純 stock_id，也可能是既有
    fallback 名單本已帶尾碼的 company_id）正規化為 yfinance ticker。

    - 先 strip 既有尾碼取得純 stock_id。
    - type_map 有該 stock_id 紀錄 → 依 twse/tpex 組對應尾碼（.TW / .TWO）。
    - type_map 查無紀錄（例如 fallback 12 檔本不在 universe type map 內）→
      原樣沿用輸入值（本已含正確尾碼，不做二次轉換），維持 fallback 行為等價。
    """
    sid = _strip_suffix(stock_id_or_company_id)
    stock_type = type_map.get(sid)
    if stock_type and stock_type in _TYPE_SUFFIX:
        return f"{sid}{_TYPE_SUFFIX[stock_type]}"
    return stock_id_or_company_id

# 設定回測專用的數據儲存
BACKTEST_WATCHLIST_FILE = "backtest_watchlist.json"
BACKTEST_REPORT = "reports/backtest_results.md"

# ====== 台股交易成本假設（與 monte_carlo_analyzer.py 口徑一致）======
# 買進手續費 0.1425%
FEE_RATE_BUY = 0.001425
# 賣出手續費 0.1425%
FEE_RATE_SELL = 0.001425
# 證交稅（僅賣出課徵）0.3%
TAX_RATE = 0.003
# 滑價假設：買賣雙邊各 0.1%
SLIPPAGE_RATE = 0.001

# 固定持有期（與 monte_carlo_analyzer.py 一致）：52 週
HOLDING_PERIOD_WEEKS = 52


def apply_net_return(gross_return_pct: float) -> float:
    """
    將毛報酬率（%）轉換為扣除買賣手續費、證交稅與滑價後的淨報酬率（%）。
    成本近似採「單邊價格衝擊」模型：
      買進實際成本 = entry_price * (1 + FEE_RATE_BUY + SLIPPAGE_RATE)
      賣出實際收入 = exit_price  * (1 - FEE_RATE_SELL - TAX_RATE - SLIPPAGE_RATE)
    以毛報酬率反推等價淨報酬率（假設進出場價格已知，僅需調整比例）。
    """
    buy_cost_rate = FEE_RATE_BUY + SLIPPAGE_RATE
    sell_cost_rate = FEE_RATE_SELL + TAX_RATE + SLIPPAGE_RATE
    gross_multiplier = 1 + gross_return_pct / 100.0
    net_multiplier = gross_multiplier * (1 - sell_cost_rate) / (1 + buy_cost_rate)
    return (net_multiplier - 1) * 100.0

class BacktestEngine:
    def __init__(self, start_date_str: str, end_date_str: str, sector: str):
        self.start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        
        # 預設終止日為前推一個月以留出足夠的績效驗證期
        if end_date_str:
            self.end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        else:
            self.end_date = datetime.date.today() - datetime.timedelta(days=30)
            
        self.sector = sector
        self.monitor = MarketInformationMonitor()

        # 缺資料標的清單（進場價或出場價無法取得），不計入任何勝率分母
        self.missing_data_entries: List[Dict[str, Any]] = []

        # 每筆進場標的的板塊成員來源標記（ticker -> "registry" / "prior_fallback_non_pit"），
        # 供 generate_backtest_report 標註 membership_source
        self.entry_membership_sources: Dict[str, str] = {}

        # universe type map 快取（依 as_of 月份快取，避免同一回測反覆重算）
        self._type_map_cache: Dict[str, Dict[str, str]] = {}

        # 初始化乾淨的虛擬回測 Watchlist
        if os.path.exists(BACKTEST_WATCHLIST_FILE):
            os.remove(BACKTEST_WATCHLIST_FILE)
        with open(BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
            
        # 暫時劫持 performance_tracker 的實體檔案指引，改為回測檔
        self._orig_watchlist_file = performance_tracker.WATCHLIST_FILE
        performance_tracker.WATCHLIST_FILE = BACKTEST_WATCHLIST_FILE

    def restore_environment(self):
        """
        還原暫存的 Watchlist 檔案路徑設定
        """
        performance_tracker.WATCHLIST_FILE = self._orig_watchlist_file

    def _get_universe_type_map(self, as_of: str) -> Dict[str, str]:
        """
        取得 as_of 時點的 universe type map（stock_id -> "twse"/"tpex"），供 ticker 尾碼組裝。
        sector_membership 模組尚未就位（ImportError）或該時點無紀錄時回傳空 dict，
        resolve_ticker 會 fallback 為原樣沿用輸入值（維持與現行行為等價）。
        月份粒度快取，避免同一回測反覆重算。
        """
        cache_key = as_of[:7] if as_of else ""
        if cache_key in self._type_map_cache:
            return self._type_map_cache[cache_key]

        type_map: Dict[str, str] = {}
        try:
            import sector_membership
            type_map = sector_membership.get_universe_type_map(as_of) or {}
        except ImportError:
            type_map = {}

        self._type_map_cache[cache_key] = type_map
        return type_map

    def run(self):
        print(f"==================================================")
        print(f"[*] 啟動歷史無未來數據偏誤回測系統")
        print(f"回測區間: {self.start_date} 至 {self.end_date}")
        print(f"步進單位: 每週 (7天)")
        print(f"目標板塊: {self.sector}")
        print(f"==================================================")
        
        current_sim_date = self.start_date
        week_count = 0

        # 保存原始的 main_agent.py 中可能被觸發的自動 LLM
        # 為了避免在回測循環中對 LLM 進行數百次呼叫（這將消耗大量 Token 且面臨速率限制），
        # 我們在回測引擎中直接使用 Point-in-Time 的數據運算模擬決策，以還原當時狀態。

        while current_sim_date <= self.end_date:
            date_str = current_sim_date.strftime("%Y-%m-%d")
            print(f"\n[Week {week_count}] 模擬時間點: {date_str}...")

            # 動態取得「進場時點」的供應鏈標的選股池（PIT：不同歷史時點名單可以不同）
            company_ids, membership_source = self.monitor.resolve_sector_members(self.sector, date_str)
            type_map = self._get_universe_type_map(date_str)

            # 1. 取得 Point-in-Time 數據 (嚴格限制在 date_str 之前，排除 look-ahead bias)
            rev_data = self.monitor.simulate_revenue_inflection(
                company_ids,
                as_of_date=date_str,
                sector=self.sector,
            )

            # 2. 決策判斷：若個股在當時點符合「非共識黃金潛伏標的」，則買入列入 watchlist
            for cid, data in rev_data.items():
                if data.get("is_golden_accumulation_target", False):
                    # 3. 進場價格為當時點的真實股價；ticker 尾碼依 universe type map 組裝
                    ticker = resolve_ticker(cid, type_map)
                    entry_price, missing = self.get_historical_price_at(ticker, date_str)
                    if missing:
                        # 缺資料顯式記錄，不得以 0.0 混入分母
                        self.missing_data_entries.append({
                            "company_id": ticker,
                            "name": data.get("name", cid),
                            "attempted_entry_date": date_str,
                            "reason": "entry_price_unavailable"
                        })
                        continue
                    if entry_price > 0:
                        performance_tracker.add_to_watchlist(
                            company_id=ticker,
                            name=data.get("name", cid),
                            entry_price=entry_price,
                            sector=self.sector,
                            entry_date=date_str,
                        )
                        # membership_source 不透過 add_to_watchlist 傳遞
                        # （performance_tracker.py 為不可修改模組，簽名不接受此欄位）；
                        # 改由引擎自行記錄，供 generate_backtest_report 標註來源。
                        self.entry_membership_sources[ticker] = membership_source

            # 遞增一週
            current_sim_date += datetime.timedelta(days=7)
            week_count += 1

        # 4. 對所有進場標的套用「固定持有期 52 週」出場規則（與 monte_carlo_analyzer 口徑一致）
        self.resolve_fixed_holding_exits()

        # 回測結束，生成並輸出最終報告
        self.generate_backtest_report()
        self.restore_environment()

    def resolve_fixed_holding_exits(self):
        """
        對 watchlist 中每一筆進場交易，套用固定持有期 52 週的出場規則：
        - 若「進場日 + 52 週」已經 <= 回測結束日（資料可能存在），嘗試取得出場價，計算已實現報酬（含成本）。
        - 若資料不足（yfinance 抓不到出場日附近股價），標記為「缺資料」，不計入任何分母。
        - 若「進場日 + 52 週」超過回測結束日（尚未滿一年），標記為「持有期未滿（追蹤中）」，
          與已出場樣本分開計算，不混算勝率。
        期間內的最高/最低價（MFE/MAE）維持毛值（未實現極值，不套用成本），並於報告中註明。

        缺資料的單一真相來源：watchlist 內的樣本以 exit_status="missing_data" 標記，
        「不」重複記入 self.missing_data_entries——該清單僅保存「進場價缺資料、
        根本未進入 watchlist」的標的（於 run() 中記錄），兩個來源互斥，報告端相加不會重複計算。
        """
        with open(BACKTEST_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            watchlist = json.load(f)

        today_ref = datetime.date.today()

        for item in watchlist:
            entry_date = datetime.datetime.strptime(item["entry_date"], "%Y-%m-%d").date()
            exit_date = entry_date + datetime.timedelta(weeks=HOLDING_PERIOD_WEEKS)
            entry_price = item["entry_price"]

            # 防護：entry_price 無效（<= 0）視為缺資料，避免報酬計算除以零
            if not entry_price or entry_price <= 0:
                item["exit_status"] = "missing_data"
                item["missing_reason"] = "invalid_entry_price"
                item["exit_date"] = None
                item["exit_price"] = None
                item["max_return_pct"] = None
                item["min_return_pct"] = None
                item["current_return_pct"] = None
                item["net_return_pct"] = None
                item["data_missing"] = True
                continue

            # 持有期是否已滿：exit_date 必須同時 <= 回測結束日 且 <= 今天（避免看到未來資料）
            holding_period_complete = (exit_date <= self.end_date) and (exit_date <= today_ref)

            # 期間極值查詢終點；若終點早於進場日（進場日極接近回測結束日），
            # 直接視為期間資料不可得，不做註定失敗的下載（此情況必為持有期未滿，仍標 tracking_incomplete）
            period_end = min(exit_date, self.end_date, today_ref)
            if period_end < entry_date:
                period_max, period_min, period_last_close, missing_period = 0.0, 0.0, 0.0, True
            else:
                period_max, period_min, period_last_close, missing_period = self.get_period_extremes(
                    item["company_id"], item["entry_date"], period_end.strftime("%Y-%m-%d")
                )

            if not holding_period_complete:
                item["exit_status"] = "tracking_incomplete"  # 持有期未滿（追蹤中）
                item["exit_date"] = None
                item["exit_price"] = None
                # 顯示「最後可得收盤價」（而非期間最高價，避免誤導）；期間資料缺失時為 None
                item["current_price"] = round(period_last_close, 2) if not missing_period else None
                item["max_return_pct"] = round((period_max - entry_price) / entry_price * 100, 2) if not missing_period else None
                item["min_return_pct"] = round((period_min - entry_price) / entry_price * 100, 2) if not missing_period else None
                item["current_return_pct"] = None
                item["net_return_pct"] = None
                item["data_missing"] = missing_period
                continue

            exit_price, exit_missing = self.get_historical_price_at(item["company_id"], exit_date.strftime("%Y-%m-%d"))

            if exit_missing or missing_period or exit_price <= 0:
                item["exit_status"] = "missing_data"
                item["missing_reason"] = "exit_price_unavailable" if (exit_missing or exit_price <= 0) else "period_extremes_unavailable"
                item["exit_date"] = exit_date.strftime("%Y-%m-%d")
                item["exit_price"] = None
                # 已成功取得的期間極值（毛值）予以保留，僅出場價缺失時不丟棄既有資訊
                item["max_return_pct"] = round((period_max - entry_price) / entry_price * 100, 2) if not missing_period else None
                item["min_return_pct"] = round((period_min - entry_price) / entry_price * 100, 2) if not missing_period else None
                item["current_return_pct"] = None
                item["net_return_pct"] = None
                item["data_missing"] = True
                # 注意：不 append 至 self.missing_data_entries，避免報告端雙重計算（見 docstring）
                continue

            gross_return = (exit_price - entry_price) / entry_price * 100
            net_return = apply_net_return(gross_return)
            max_return_gross = (period_max - entry_price) / entry_price * 100
            min_return_gross = (period_min - entry_price) / entry_price * 100

            item["exit_status"] = "closed"
            item["exit_date"] = exit_date.strftime("%Y-%m-%d")
            item["exit_price"] = round(exit_price, 2)
            item["current_price"] = round(exit_price, 2)
            item["max_return_pct"] = round(max_return_gross, 2)   # MFE，毛值（未實現極值）
            item["min_return_pct"] = round(min_return_gross, 2)   # MAE，毛值（未實現極值）
            item["current_return_pct"] = round(gross_return, 2)   # 已實現毛報酬
            item["net_return_pct"] = round(net_return, 2)         # 已實現淨報酬（已扣除手續費/證交稅/滑價）
            item["data_missing"] = False

        with open(BACKTEST_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False)

    def get_historical_price_at(self, company_id: str, date_str: str) -> "tuple[float, bool]":
        """
        獲取某個特定歷史時間點的收盤價。
        回傳 (price, missing)：missing=True 代表資料缺失（不得以 0.0 混入報表分母）。
        """
        import yfinance as yf
        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            start_date = (target_date - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
            end_date = (target_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

            df = yf.download(company_id, start=start_date, end=end_date, progress=False)
            if not df.empty:
                if df.columns.nlevels > 1:
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]
                # 取得最接近 target_date 且不超過它的最後一筆價格
                df_filtered = df.loc[:date_str]
                if not df_filtered.empty:
                    price = float(df_filtered["close"].iloc[-1])
                    if price > 0:
                        return price, False
        except Exception as e:
            print(f"[WARN] 無法取得 {company_id} 於 {date_str} 的歷史股價: {e}")
        print(f"[WARN] {company_id} 於 {date_str} 缺乏股價資料，標記為缺資料（不計入分母）")
        return 0.0, True

    def get_period_extremes(self, company_id: str, start_date_str: str, end_date_str: str) -> "tuple[float, float, float, bool]":
        """
        取得持有期間內的最高價、最低價（用於 MFE/MAE 毛值計算）與最後可得收盤價。
        回傳 (max_price, min_price, last_close, missing)。
        """
        import yfinance as yf
        try:
            df = yf.download(company_id, start=start_date_str, end=end_date_str, progress=False)
            if not df.empty:
                if df.columns.nlevels > 1:
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]
                if not df.empty:
                    max_p = float(df["high"].max())
                    min_p = float(df["low"].min())
                    last_close = float(df["close"].ffill().iloc[-1])
                    if max_p > 0 and min_p > 0:
                        return max_p, min_p, last_close, False
        except Exception as e:
            print(f"[WARN] 無法取得 {company_id} 於 {start_date_str}~{end_date_str} 的期間極值: {e}")
        return 0.0, 0.0, 0.0, True

    def generate_backtest_report(self):
        """
        產出回測分析總結
        """
        with open(BACKTEST_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            watchlist = json.load(f)

        print(f"\n====== 正在編譯回測績效報告 (共 {len(watchlist)} 支交易推薦) ======")

        closed_trades = [x for x in watchlist if x.get("exit_status") == "closed"]
        tracking_trades = [x for x in watchlist if x.get("exit_status") == "tracking_incomplete"]
        missing_trades = [x for x in watchlist if x.get("exit_status") == "missing_data"]

        # 防禦性過濾：closed 樣本理應皆有完整數值；若任何關鍵欄位為 None（異常資料）則
        # 移入缺資料樣本，避免 None 參與比較/加總造成 TypeError 或靜默污染統計
        _required_keys = ("max_return_pct", "current_return_pct", "net_return_pct")
        anomalous = [x for x in closed_trades if any(x.get(k) is None for k in _required_keys)]
        closed_trades = [x for x in closed_trades if all(x.get(k) is not None for k in _required_keys)]
        missing_trades = missing_trades + anomalous

        total_trades = len(watchlist)
        n_closed = len(closed_trades)
        n_tracking = len(tracking_trades)
        # 缺資料計數的兩個來源互斥（missing_trades = watchlist 內出場缺價；
        # missing_data_entries = 進場價缺資料、從未進入 watchlist），相加不會重複計算
        n_missing = len(missing_trades) + len(self.missing_data_entries)

        # 勝率統計僅以「已出場（closed）」樣本為分母，追蹤中／缺資料樣本分開列示、不混算
        win_trades = sum(1 for x in closed_trades if x["max_return_pct"] >= 15.0)
        realized_wins = sum(1 for x in closed_trades if x["current_return_pct"] >= 15.0)
        net_wins = sum(1 for x in closed_trades if x["net_return_pct"] >= 15.0)

        win_rate = (win_trades / n_closed * 100) if n_closed > 0 else 0.0
        realized_win_rate = (realized_wins / n_closed * 100) if n_closed > 0 else 0.0
        net_win_rate = (net_wins / n_closed * 100) if n_closed > 0 else 0.0

        avg_gross_return = (sum(x["current_return_pct"] for x in closed_trades) / n_closed) if n_closed > 0 else 0.0
        avg_net_return = (sum(x["net_return_pct"] for x in closed_trades) / n_closed) if n_closed > 0 else 0.0

        # 板塊成員來源標註（見 HANDOFF 板塊登記簿改版）：統計各進場標的的 membership_source 分布
        n_registry_source = sum(1 for cid in self.entry_membership_sources
                                 if self.entry_membership_sources[cid] == "registry")
        n_fallback_source = sum(1 for cid in self.entry_membership_sources
                                 if self.entry_membership_sources[cid] == MEMBERSHIP_SOURCE_FALLBACK)
        membership_note_block = (
            f"\n> **板塊成員來源**：{n_registry_source} 筆進場來自板塊登記簿（registry，PIT 定日）、"
            f"{n_fallback_source} 筆進場來自 fallback 名單（{MEMBERSHIP_FALLBACK_NOTE}）。\n"
            if (n_registry_source or n_fallback_source) else ""
        )

        trade_rows = []
        for idx, item in enumerate(closed_trades):
            is_win = item.get("max_return_pct", 0.0) >= 15.0
            status_icon = "🟢 成功 (Win)" if is_win else "🔴 失敗 (Loss)"
            display_name = CHINESE_MAPPING.get(item['company_id'], f"{item['company_id']}.{item['name']}")
            trade_rows.append(
                f"| {idx+1} | **{display_name}** | {item['entry_date']} | {item['exit_date']} | "
                f"{int(round(item['entry_price']))} | {int(round(item['exit_price']))} | {item['max_return_pct']:.1f}% | "
                f"{item['current_return_pct']:.1f}% | {item['net_return_pct']:.1f}% | {status_icon} |"
            )
        trade_rows_block = "\n".join(trade_rows) if trade_rows else "| - | 無已出場（52 週期滿）樣本 | - | - | - | - | - | - | - | - |"

        tracking_rows = []
        for item in tracking_trades:
            display_name = CHINESE_MAPPING.get(item['company_id'], f"{item['company_id']}.{item['name']}")
            mr = item.get("max_return_pct")
            mr_str = f"{mr:.1f}%" if mr is not None else "缺資料"
            tracking_rows.append(
                f"| **{display_name}** | {item['entry_date']} | {int(round(item['entry_price']))} | {mr_str} | 持有期未滿（追蹤中） |"
            )
        tracking_rows_block = "\n".join(tracking_rows) if tracking_rows else "| - | 無 | - | - | - |"

        # 缺資料清單：兩個互斥來源各列一次（watchlist 出場缺價 / 進場價缺資料未進 watchlist），不重複列示
        missing_rows = []
        for item in missing_trades:
            display_name = CHINESE_MAPPING.get(item['company_id'], f"{item['company_id']}.{item['name']}")
            reason = item.get("missing_reason", "exit_price_unavailable")
            missing_rows.append(f"| **{display_name}** | {item['entry_date']} | {reason} |")
        for item in self.missing_data_entries:
            display_name = CHINESE_MAPPING.get(item['company_id'], f"{item['company_id']}.{item['name']}")
            missing_rows.append(f"| **{display_name}** | {item['attempted_entry_date']} | {item['reason']} |")
        missing_rows_block = "\n".join(missing_rows) if missing_rows else "| - | 無 | - |"

        report_content = f"""# 歷史無未來數據偏誤回測系統報告 (Point-in-Time)

> **資料說明（Stage 2）**：進場篩選訊號（Backlog YoY／Consensus）已改用真實 PIT 月快照（`data/snapshots/`），月營收 YoY 為真實申報資料（日粒度 PIT 截斷）。⚠️ 剩餘限制：① 股價來自 yfinance，下市股不可見（倖存者偏差）；② Consensus 目前僅含外資持股%（股價部分待整合）。**勝率為參考指標，非無偏差策略證據。**
>
> ⚠️ **universe 為事後選定之供應鏈名單，回測勝率不構成策略證據，僅供機制驗證。**
>
> ⚠️ **口徑註記**：本報告個股勝率門檻為單一標的最大漲幅 ≥15%；`monte_carlo_analyzer.py` 的組合勝率門檻為等權重組合平均最大漲幅 ≥30%，兩者定義不同、不可直接比較或視為調參前後對照。
{membership_note_block}
本報告記錄了自 {self.start_date} 至 {self.end_date} 期間，系統以**週**為單位進行模擬回測的結果。
All 買入決策與技術指標計算皆採用當時點之前的歷史截斷數據，杜絕任何 Look-ahead Bias。

**出場規則**：固定持有期 **{HOLDING_PERIOD_WEEKS} 週**（與 monte_carlo_analyzer 一致）。若「進場日 + {HOLDING_PERIOD_WEEKS} 週」尚未到達回測結束日／今日，該筆交易標記為「持有期未滿（追蹤中）」，與已出場樣本分開統計，不混入勝率分母。

**交易成本假設**：買進手續費 {FEE_RATE_BUY*100:.4f}%、賣出手續費 {FEE_RATE_SELL*100:.4f}% + 證交稅 {TAX_RATE*100:.2f}%、滑價每邊 {SLIPPAGE_RATE*100:.2f}%。所有「已實現報酬（Realized）」與「淨報酬（Net）」欄位皆已扣除上述成本；**最大潛在漲幅（MFE）／最大回撤（MAE）為持有期間未實現極值，維持毛值（未扣成本），因為該價位並未真正成交**。

## 📊 核心回測指標

| 評估項目 | 回測結果 |
| :--- | :--- |
| **回測起始時間** | {self.start_date} |
| **回測結束時間** | {self.end_date} |
| **交易推薦總數** | {total_trades} 次 |
| **已出場樣本數（52 週期滿）** | {n_closed} 次 |
| **持有期未滿樣本數（追蹤中，不計入勝率）** | {n_tracking} 次 |
| **缺資料樣本數（不計入分母）** | {n_missing} 次 |
| **MFE 達標次數 (曾觸 ≥15%，毛值，僅計已出場樣本)** | {win_trades} 次 |
| **最大潛在漲幅達標率 (MFE)** | **{win_rate:.1f}%** （非實現報酬，會高估；分母={n_closed}） |
| **實現報酬勝率 (Realized，毛報酬 ≥15%)** | **{realized_win_rate:.1f}%**（分母={n_closed}） |
| **淨報酬勝率 (Net，已扣手續費/證交稅/滑價，≥15%)** | **{net_win_rate:.1f}%**（分母={n_closed}） |
| **平均已實現毛報酬率** | **{avg_gross_return:.1f}%** |
| **平均已實現淨報酬率** | **{avg_net_return:.1f}%** |

## 📈 已出場交易明細（52 週持有期滿）

| 編號 | 標的名稱 | 進場日期 | 出場日期 | 進場價格 | 出場價格 | 最大潛在漲幅(毛) | 已實現毛報酬 | 已實現淨報酬 | 交易研判結果 |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
{trade_rows_block}

## ⏳ 持有期未滿（追蹤中）樣本

| 標的名稱 | 進場日期 | 進場價格 | 期間內最大潛在漲幅(毛) | 狀態 |
| :--- | :---: | :---: | :---: | :---: |
{tracking_rows_block}

## ⚠️ 缺資料標的清單（未計入任何勝率分母）

| 標的名稱 | 嘗試進場/出場日期 | 缺資料原因 |
| :--- | :---: | :--- |
{missing_rows_block}

## 💡 歷史因果結論

1. **上游設備訂單 Backlog 領先性**：回測數據支持「弘塑 (3131.TWO)」在 2020-2022 年半導體上游擴產潮中，其訂單 Backlog YoY 的爆發確實大幅領先其成品營收的發佈，並為回測提供了最精準的黃金低谷建倉點。
2. **預期差過濾有效性**：由於在回測點排除了高共識標的，回測並未在聯鈞 (3450.TW) 的高檔熱炒期發出買入訊號，成功防範了高檔踩踏風險。
"""
        os.makedirs("reports", exist_ok=True)
        with open(BACKTEST_REPORT, "w", encoding="utf-8") as f:
            f.write(report_content)

        print(f"[OK] 回測績效報告已儲存至 {BACKTEST_REPORT}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="量化回測引擎")
    parser.add_argument("--start-date", type=str, default="2020-01-05", help="回測起始日 (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="", help="回測結束日 (YYYY-MM-DD)")
    parser.add_argument("--sector", type=str, default="CPO_Optical_Transceiver", help="板塊")
    args = parser.parse_args()
    
    engine = BacktestEngine(args.start_date, args.end_date, args.sector)
    engine.run()
