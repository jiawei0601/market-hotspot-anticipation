import pandas as pd
import numpy as np
import datetime
from typing import Dict, List, Any, Optional

class MarketInformationMonitor:
    """
    12-18 個月至 18-24 個月超前中期投資核心資訊監控與模擬引擎。
    優化三大痛點：
    1. 能見度拉長至 18-24 個月 (Feynman -> Feynman_Next) 以防追高已反映標的。
    2. 引入上游設備商 Backlog 訂單指標 (領先下游營收 2 個季度 / 6-9 個月)。
    3. 引入「預期差與共識度過濾器 (Consensus Score)」，專注於低共識、高預期差的非共識標的。
    """
    def __init__(self):
        # 18-24 個月超前世代 (Feynman_Next) 的物理規格限制與價值演進
        self.generation_specs = {
            "Vera_Rubin": {
                "cooling": {"type": "Full Liquid Cooling", "content_value_pct": 8.0, "status": "Mature"},
                "transmission": {"type": "Active Copper / Early CPO", "content_value_pct": 5.0, "status": "Ramping up"},
                "package": {"type": "CoWoS-L", "content_value_pct": 12.0, "status": "Shortage"}
            },
            "Feynman": {
                "cooling": {"type": "Advanced Immersion Cooling", "content_value_pct": 12.0, "status": "Ramp-up Peak"},
                "transmission": {"type": "Silicon Photonics (CPO)", "content_value_pct": 15.0, "status": "Ramp-up Peak"},
                "package": {"type": "3D IC / SoIC", "content_value_pct": 18.0, "status": "Shortage"}
            },
            "Feynman_Next": {
                "cooling": {"type": "Direct-to-Chip (DTC) Liquid", "content_value_pct": 14.0, "status": "Spec Def"},
                "transmission": {"type": "Direct Optical I/O (Silicon Photonics integrated into compute die)", "content_value_pct": 8.0, "status": "Spec Def"},
                "package": {"type": "Hybrid Bonding / 2.5D/3D Hybrid Packaging", "content_value_pct": 25.0, "status": "Early Design"}
            }
        }
        
        # 供應商價值矩陣 (包含設備商、新興材料商，以及在 Feynman_Next 的洗牌效應)
        self.supply_chain_matrix = [
            {
                "company_id": "3450.TW",  # 聯鈞 (FOCI)
                "name": "FOCI",
                "segment": "transmission",
                "content_value_by_gen": {"Vera_Rubin": 4.5, "Feynman": 14.0, "Feynman_Next": 8.0},
                "consensus_score": 92.0,
                "status": "Consensus Winner for Feynman CPO",
                "timeline": {"design_win": "2025-Q1", "pilot": "2026-Q1", "ramp_up": "2026-Q3"}
            },
            {
                "company_id": "3131.TW",  # 弘塑 (GrandProcess)
                "name": "GrandProcess",
                "segment": "equipment",
                "content_value_by_gen": {"Vera_Rubin": 10.0, "Feynman": 18.0, "Feynman_Next": 26.0},
                "consensus_score": 35.0,
                "status": "Entering Feynman_Next Spec Definition",
                "timeline": {"design_win": "2025-Q2", "pilot": "2025-Q4", "ramp_up": "2026-Q2"}
            },
            {
                "company_id": "3013.TW",  # 晟銘電 (MCT)
                "name": "MCT",
                "segment": "cooling",
                "content_value_by_gen": {"Vera_Rubin": 6.0, "Feynman": 9.5, "Feynman_Next": 4.0},
                "consensus_score": 85.0,
                "status": "Mature Rubin/Feynman Supplier",
                "timeline": {"design_win": "2025-Q1", "pilot": "2026-Q1", "ramp_up": "2026-Q3"}
            },
            {
                "company_id": "3324.TW",  # 雙鴻 (Auras)
                "name": "Auras",
                "segment": "cooling",
                "content_value_by_gen": {"Vera_Rubin": 8.0, "Feynman": 12.0, "Feynman_Next": 18.0},
                "consensus_score": 52.0,
                "status": "Co-developing Feynman_Next DTC cooling",
                "timeline": {"design_win": "2025-Q3", "pilot": "2026-Q2", "ramp_up": "2026-Q4"}
            }
        ]
        self.real_revenue_cache = None

    def get_high_frequency_pricing(self, sector: str) -> Dict[str, Any]:
        """
        模擬/獲取高頻報價趨勢。
        """
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
            "catalyst_triggered": trend == "rising"
        }

    def get_supply_chain_schedule(self, current_gen: str, next_gen: str) -> Dict[str, Any]:
        """
        推演架構演進下的供應鏈洗牌，包含 18-24 個月超前世代 (Feynman_Next) 的替代風險。
        """
        analysis = []
        bottlenecks = []
        
        for item in self.supply_chain_matrix:
            val_current = item["content_value_by_gen"].get(current_gen, 0.0)
            val_next = item["content_value_by_gen"].get(next_gen, 0.0)
            val_future = item["content_value_by_gen"].get("Feynman_Next", 0.0)
            
            if val_current > 0:
                change_pct = (val_next - val_current) / val_current * 100
            else:
                change_pct = 999.0
                
            if val_next > 0:
                future_change_pct = (val_future - val_next) / val_next * 100
            else:
                future_change_pct = 999.0
                
            substitution_risk = "LOW"
            if val_future < val_next * 0.7:
                substitution_risk = "HIGH (Content Value Erosion / Substitution)"
            elif val_future > val_next * 1.4:
                substitution_risk = "NONE (Content Value Expanding)"
                
            analysis.append({
                "company_id": item["company_id"],
                "name": item["name"],
                "segment": item["segment"],
                "content_value_current": val_current,
                "content_value_next": val_next,
                "content_value_future": val_future,
                "change_pct": round(change_pct, 2),
                "future_change_pct": round(future_change_pct, 2),
                "consensus_score": item["consensus_score"],
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
            "timeline_matrix": analysis
        }

    def fetch_real_monthly_revenue(self) -> Dict[str, Dict[str, Any]]:
        """
        從台灣證券交易所 (TWSE) 下載最新月份上市與公開發行/上櫃公司營收匯總資料。
        """
        if self.real_revenue_cache is not None:
            return self.real_revenue_cache
            
        import urllib.request
        import json
        
        urls = [
            "https://openapi.twse.com.tw/v1/opendata/t187ap05_L", # 上市公司
            "https://openapi.twse.com.tw/v1/opendata/t187ap05_P"  # 上櫃/公發公司
        ]
        
        revenue_map = {}
        
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode('utf-8'))
                    
                for row in data:
                    company_code = row.get("公司代號", "").strip()
                    if not company_code:
                        continue
                        
                    # 讀取當月營收 (單位: 千元 -> 轉為億元)
                    raw_rev = row.get("營業收入-當月營收", "0")
                    try:
                        revenue_yoy = float(row.get("營業收入-去年同月增減(%)", "0.0"))
                    except ValueError:
                        revenue_yoy = 0.0
                        
                    try:
                        rev_val = float(raw_rev) / 100000.0 # 轉為億元
                    except ValueError:
                        rev_val = 0.0
                        
                    date_ym = row.get("資料年月", "").strip()
                    
                    revenue_map[company_code] = {
                        "revenue_billion": round(rev_val, 2),
                        "yoy_pct": round(revenue_yoy, 2),
                        "date_ym": date_ym,
                        "company_name": row.get("公司名稱", "").strip()
                    }
            except Exception as e:
                # 僅印出警告，讓系統能繼續執行，達到 Robustness
                print(f"[WARN] Cannot fetch real revenue from {url}: {e}")
                
        self.real_revenue_cache = revenue_map
        return revenue_map

    def simulate_revenue_inflection(self, company_ids: List[str]) -> Dict[str, Any]:
        """
        營收 YoY 拐點與設備訂單 Backlog 領先指標模擬器。
        - 嘗試從 TWSE OpenAPI 讀取最新的真實月度營收與真實 YoY 數據。
        - 設備訂單 (Backlog) 領先下游成品營收 2 個季度 (6個月)。
        - 系統透過對比「設備訂單 YoY」與「成品營收 YoY」來捕捉最前瞻的起漲拐點。
        """
        results = {}
        today = datetime.date.today()
        
        # 獲取真實營收資料庫 (有自動 fallback 保障)
        real_rev_data = self.fetch_real_monthly_revenue()
        
        for cid in company_ids:
            item = next((x for x in self.supply_chain_matrix if x["company_id"] == cid), None)
            if not item:
                continue
                
            name = item["name"]
            segment = item["segment"]
            
            # 1. 基礎模擬生成
            base_monthly = 600.0 if segment != "equipment" else 250.0
            last_year_rev = [round(base_monthly * (1 + np.sin(i/3)*0.1 - 0.20), 1) for i in range(12)]
            current_year_rev = [round(base_monthly * (1 + np.sin(i/3)*0.08 - 0.15), 1) for i in range(9)]
            
            # 2. 嘗試結合 TWSE 真實數據 (以個股代碼如 3450 去配對)
            clean_code = cid.replace(".TW", "").replace(".TWO", "").strip()
            real_info = real_rev_data.get(clean_code)
            
            has_real = False
            real_date_ym = ""
            real_rev_val = 0.0
            real_yoy_pct = 0.0
            
            if real_info:
                has_real = True
                real_date_ym = real_info["date_ym"]
                real_rev_val = real_info["revenue_billion"]
                real_yoy_pct = real_info["yoy_pct"]
                
                # 替換最新月份營收 (第 9 個月) 為真實數據
                current_year_rev[-1] = real_rev_val
                # 利用數學逆推：將去年同月基期設定為與真實 YoY 對齊的數值
                # yoy = (curr - prev) / prev * 100 => prev = curr / (1 + yoy/100)
                denom = 1.0 + (real_yoy_pct / 100.0)
                if denom != 0:
                    last_year_rev[8] = round(real_rev_val / denom, 2)
            
            # 3. 模擬未來 3 個月出貨放量 (以最新月份營收為基期，設備商放量預期較陡)
            last_actual_rev = current_year_rev[-1]
            scale_factors = [1.05, 1.15, 1.35] if segment != "equipment" else [1.10, 1.25, 1.50]
            future_simulation = [round(last_actual_rev * f, 1) for f in scale_factors]
            all_current_year = current_year_rev + future_simulation
            
            # 4. 計算成品營收 YoY
            yoy_curve = []
            for idx in range(12):
                denom = last_year_rev[idx]
                yoy = ((all_current_year[idx] - denom) / denom * 100) if denom > 0 else 0.0
                yoy_curve.append(round(yoy, 2))
                
            # 💡 核心優化：模擬設備商或上游特用材料的「訂單 Backlog YoY」
            # 設備訂單比下游營收領先 2 個季度 (6個月) 爆發。
            backlog_yoy_curve = []
            for idx in range(12):
                if idx < 6:
                    backlog_yoy = yoy_curve[idx + 6] * 1.3
                else:
                    backlog_yoy = (100 - (idx - 6) * 10) * (1 + np.random.normal(0, 0.05))
                backlog_yoy_curve.append(round(max(backlog_yoy, 5.0), 2))
                
            future_yoy = yoy_curve[-3:]
            inflection_expected = future_yoy[-1] > future_yoy[0] and future_yoy[-1] > 20.0
            
            # 設備訂單是否已率先觸發爆發
            equipment_lead_active = backlog_yoy_curve[8] > 50.0
            
            # 尋找營收最大 YoY 拐點
            max_yoy_idx = int(np.argmax(yoy_curve[-3:])) + 9
            peak_yoy_val = yoy_curve[max_yoy_idx]
            peak_month = (today + datetime.timedelta(days=30 * (max_yoy_idx - 8))).strftime("%Y-%m")
            
            results[cid] = {
                "name": name,
                "segment": segment,
                "inflection_expected": inflection_expected,
                "peak_month": peak_month,
                "projected_peak_yoy_pct": peak_yoy_val,
                "last_month_yoy": yoy_curve[8],
                "future_3m_yoy": future_yoy,
                "consensus_score": item["consensus_score"],
                
                # 真實數據整合欄位
                "has_real_data": has_real,
                "real_date_ym": real_date_ym,
                "real_revenue_billion": real_rev_val if has_real else None,
                "real_yoy_pct": real_yoy_pct if has_real else None,
                
                # 設備訂單 (超前指標)
                "equipment_lead_active": equipment_lead_active,
                "current_backlog_yoy_pct": backlog_yoy_curve[8],
                "backlog_yoy_curve_3m": backlog_yoy_curve[-3:],
                
                # 第二層思考判定：是否為「低共識 + 設備 Backlog 暴增 + 下游營收在谷底」的黃金潛伏標的
                "is_golden_accumulation_target": (item["consensus_score"] < 60.0 and equipment_lead_active and yoy_curve[8] < 15.0),
                
                # 歷史與預測的月營收曲線數據
                "historical_base": last_year_rev,
                "current_projected": all_current_year
            }
            
        return results

if __name__ == "__main__":
    monitor = MarketInformationMonitor()
    print("=== 1. 超前供應鏈洗牌時程與下世代替代風險 ===")
    print(monitor.get_supply_chain_schedule("Vera_Rubin", "Feynman"))
    print("\n=== 2. 營收基期與設備 Backlog 領先指標 ===")
    print(monitor.simulate_revenue_inflection(["3450.TW", "3131.TW", "3324.TW"]))
