import pandas as pd
import numpy as np
import datetime
from typing import Dict, List, Any, Optional
import yfinance as yf

class MarketInformationMonitor:
    """
    12-18 個月中期投資核心資訊監控與模擬引擎。
    提煉三大投資思維：物理規格 content value 洗牌、放量排程能見度、高頻報價與營收基期 YoY 拐點。
    """
    def __init__(self):
        # 模擬科技產業架構演進的物理規格限制與供應鏈價值資料
        self.generation_specs = {
            "Blackwell": {
                "cooling": {"type": "Air/Liquid Hybrid", "content_value_pct": 3.0, "status": "Ramping down"},
                "transmission": {"type": "Copper DAC", "content_value_pct": 2.0, "status": "Mature"},
                "package": {"type": "CoWoS-S", "content_value_pct": 10.0, "status": "Bottleneck"}
            },
            "Vera_Rubin": {
                "cooling": {"type": "Full Liquid Cooling", "content_value_pct": 8.0, "status": "Ramping up"},
                "transmission": {"type": "Active Copper / Early CPO", "content_value_pct": 5.0, "status": "Design Win"},
                "package": {"type": "CoWoS-L", "content_value_pct": 12.0, "status": "Shortage"}
            },
            "Feynman": {
                "cooling": {"type": "Advanced Immersion Cooling", "content_value_pct": 12.0, "status": "R&D / Early Design"},
                "transmission": {"type": "Silicon Photonics (CPO)", "content_value_pct": 15.0, "status": "Spec Def"},
                "package": {"type": "3D IC / SoIC", "content_value_pct": 18.0, "status": "Spec Def"}
            }
        }
        
        # 模擬核心供應商名單與在各世代的內含價值佔比
        self.supply_chain_matrix = [
            {
                "company_id": "3013.TW",  # 晟銘電 (MCT) - 散熱機殼
                "name": "MCT",
                "segment": "cooling",
                "content_value_by_gen": {"Blackwell": 2.5, "Vera_Rubin": 6.0, "Feynman": 9.5},
                "status": "Design Win in Rubin",
                "timeline": {"design_win": "2025-Q1", "tooling": "2025-Q3", "pilot": "2026-Q1", "ramp_up": "2026-Q3"}
            },
            {
                "company_id": "3324.TW",  # 雙鴻 (Auras) - 水冷散熱
                "name": "Auras",
                "segment": "cooling",
                "content_value_by_gen": {"Blackwell": 4.0, "Vera_Rubin": 8.0, "Feynman": 12.0},
                "status": "Qualified for Rubin Full Liquid",
                "timeline": {"design_win": "2025-Q2", "tooling": "2025-Q4", "pilot": "2026-Q2", "ramp_up": "2026-Q4"}
            },
            {
                "company_id": "3450.TW",  # 聯鈞 (FOCI) - 光通訊/CPO
                "name": "FOCI",
                "segment": "transmission",
                "content_value_by_gen": {"Blackwell": 0.5, "Vera_Rubin": 4.5, "Feynman": 14.0},
                "status": "Co-designing Feynman Silicon Photonics",
                "timeline": {"design_win": "2025-Q4", "tooling": "2026-Q2", "pilot": "2026-Q4", "ramp_up": "2027-Q2"}
            },
            {
                "company_id": "2330.TW",  # 台積電 (TSMC) - 先進封裝 CoWoS
                "name": "TSMC",
                "segment": "package",
                "content_value_by_gen": {"Blackwell": 10.0, "Vera_Rubin": 12.0, "Feynman": 18.0},
                "status": "Monopolizing CoWoS & SoIC",
                "timeline": {"design_win": "2024-Q1", "tooling": "2024-Q3", "pilot": "2025-Q1", "ramp_up": "2025-Q4"}
            }
        ]

    def get_high_frequency_pricing(self, sector: str) -> Dict[str, Any]:
        """
        模擬/獲取高頻報價趨勢，作為短期資金流入的 Catalyst 驗證。
        """
        # 以 CPO 光電傳輸為例，高頻報價通常包含高速傳輸模組材料或關鍵光收發晶片合約價。
        today = datetime.date.today()
        dates = [today - datetime.timedelta(weeks=i) for i in range(12)][::-1] # 過去 12 週
        
        # CPO 相關材料報價 (以 USD/unit 模擬)
        # 設定在過去 12 週內呈現止跌回升的打底走勢，模擬 YoY 拐點發酵前的 Catalyst
        base_price = 120.0
        prices = []
        for idx in range(12):
            if idx < 4:
                # 打底跌勢止穩
                price = base_price - idx * 1.5
            elif idx < 8:
                # 盤整打底
                price = base_price - 6.0 + (idx - 4) * 0.5
            else:
                # 止跌回升，價格突破
                price = base_price - 4.0 + (idx - 8) * 2.8
            prices.append(round(price, 2))
            
        weekly_data = [{"date": d.strftime("%Y-%m-%d"), "price": p} for d, p in zip(dates, prices)]
        
        # 計算動量指標
        recent_change = (prices[-1] - prices[-4]) / prices[-4] * 100 # 近一月變動
        trend = "rising" if recent_change > 1.5 else ("declining" if recent_change < -1.5 else "stable")
        
        return {
            "sector": sector,
            "metric_name": "High-speed Optical Material Index",
            "trend": trend,
            "weekly_change_pct": round(recent_change, 2),
            "data_points": weekly_data,
            "catalyst_triggered": trend == "rising"
        }

    def get_supply_chain_schedule(self, current_gen: str, next_gen: str) -> Dict[str, Any]:
        """
        推演架構演進下的供應鏈洗牌，計算 Content Value 變動比例與替代風險。
        """
        analysis = []
        bottlenecks = []
        
        for item in self.supply_chain_matrix:
            val_current = item["content_value_by_gen"].get(current_gen, 0.0)
            val_next = item["content_value_by_gen"].get(next_gen, 0.0)
            
            # 計算內含價值變動比例
            if val_current > 0:
                change_pct = (val_next - val_current) / val_current * 100
            else:
                change_pct = 999.0 # 代表新進入者 (New Entry)
                
            # 判斷是否為瓶頸點 (例如 CoWoS 產能或高頻散熱)
            is_bottleneck = item["segment"] in ["package", "cooling"]
            if is_bottleneck:
                bottlenecks.append(f"{item['name']} ({item['segment']})")
                
            # 計算替代風險：如果在新架構中價值降為 0，代表 Content Value 歸零被淘汰
            risk = "HIGH (Substituted)" if val_next == 0 and val_current > 0 else "LOW"
            if val_next > val_current * 1.5:
                potential = "HIGH (Value Expanding)"
            else:
                potential = "NORMAL"
                
            analysis.append({
                "company_id": item["company_id"],
                "name": item["name"],
                "segment": item["segment"],
                "content_value_current": val_current,
                "content_value_next": val_next,
                "change_pct": round(change_pct, 2),
                "status": item["status"],
                "timeline": item["timeline"],
                "substitution_risk": risk,
                "growth_potential": potential
            })
            
        return {
            "current_generation": current_gen,
            "next_generation": next_gen,
            "bottlenecks": bottlenecks,
            "timeline_matrix": analysis
        }

    def simulate_revenue_inflection(self, company_ids: List[str]) -> Dict[str, Any]:
        """
        營收基期與年增率 (YoY) 拐點模擬器。
        模擬未來 3 個月出貨放量，在去年低基期下產生的年增暴增拐點。
        """
        results = {}
        today = datetime.date.today()
        
        # 模擬月度營收歷史數據 (台股為核心)
        # 去年月營收為低基期，今年月營收隨量產 Ramp-up 逐月攀升
        for cid in company_ids:
            name = next((x["name"] for x in self.supply_chain_matrix if x["company_id"] == cid), cid.split(".")[0])
            
            # 生成過去 12 個月的真實/模擬月營收 (以百萬新台幣 NTD M 爲單位)
            # 去年同期 (基期) 的數據：模擬一個低基期（因客戶調整庫存）
            base_monthly = 500.0
            last_year_rev = [round(base_monthly * (1 + np.sin(i/3)*0.1 - 0.15), 1) for i in range(12)] # 低基期
            
            # 今年截至目前的月營收 (已有 9 個月)
            current_year_rev = [round(base_monthly * (1 + np.sin((i)/3)*0.1 + i*0.08), 1) for i in range(9)]
            
            # 模擬未來 3 個月（Ramp-up 放量期）
            # 新晶片架構開始量產，拉貨動能大幅提振
            last_actual_rev = current_year_rev[-1]
            future_simulation = [
                round(last_actual_rev * 1.12, 1), # 第 10 個月 (Ramp-up 開始)
                round(last_actual_rev * 1.25, 1), # 第 11 個月 (加速)
                round(last_actual_rev * 1.40, 1)  # 第 12 個月 (放量高峰)
            ]
            
            all_current_year = current_year_rev + future_simulation
            
            # 計算 YoY % 曲線
            yoy_curve = []
            for idx in range(12):
                yoy = (all_current_year[idx] - last_year_rev[idx]) / last_year_rev[idx] * 100
                yoy_curve.append(round(yoy, 2))
                
            # 判斷未來 3 個月的 YoY 變化，是否出現「拐點向上且大幅暴增」
            future_yoy = yoy_curve[-3:]
            inflection_expected = future_yoy[-1] > future_yoy[0] and future_yoy[-1] > 25.0 # YoY 逐月走高且高於 25%
            
            # 計算峰值
            max_yoy_idx = int(np.argmax(yoy_curve[-3:])) + 9 # 對應未來 3 個月的 index
            peak_yoy_val = yoy_curve[max_yoy_idx]
            peak_month = (today + datetime.timedelta(days=30 * (max_yoy_idx - 8))).strftime("%Y-%m")
            
            results[cid] = {
                "name": name,
                "inflection_expected": inflection_expected,
                "peak_month": peak_month,
                "projected_peak_yoy_pct": peak_yoy_val,
                "last_month_yoy": yoy_curve[8],
                "future_3m_yoy": future_yoy,
                "historical_base": last_year_rev,
                "current_projected": all_current_year
            }
            
        return results

if __name__ == "__main__":
    # 測試引擎運作
    monitor = MarketInformationMonitor()
    
    print("=== 1. 高頻價格監控 ===")
    print(monitor.get_high_frequency_pricing("CPO_Optical_Transceiver"))
    
    print("\n=== 2. 供應鏈洗牌時程 ===")
    print(monitor.get_supply_chain_schedule("Vera_Rubin", "Feynman"))
    
    print("\n=== 3. 營收基期與拐點模擬 ===")
    print(monitor.simulate_revenue_inflection(["3450.TW", "3013.TW"]))
