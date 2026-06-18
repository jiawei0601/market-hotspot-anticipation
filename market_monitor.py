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
                # 下下一代 (18-24個月能見度)：CPO 面臨晶粒整合 (Optical I/O) 被替代風險，散熱朝 DTC 整合發展
                "cooling": {"type": "Direct-to-Chip (DTC) Liquid", "content_value_pct": 14.0, "status": "Spec Def"},
                "transmission": {"type": "Direct Optical I/O (Silicon Photonics integrated into compute die)", "content_value_pct": 8.0, "status": "Spec Def"},
                "package": {"type": "Hybrid Bonding / 2.5D/3D Hybrid Packaging", "content_value_pct": 25.0, "status": "Early Design"}
            }
        }
        
        # 擴充後的供應商價值矩陣 (包含設備商、新興材料商，以及在 Feynman_Next 的洗牌效應)
        self.supply_chain_matrix = [
            {
                "company_id": "3450.TW",  # 聯鈞 (FOCI) - 光學元件
                "name": "FOCI",
                "segment": "transmission",
                "content_value_by_gen": {"Vera_Rubin": 4.5, "Feynman": 14.0, "Feynman_Next": 8.0}, # 注意：Feynman_Next 中因晶片內光電整合，獨立CPO模組面臨被替代，CV腰斬
                "consensus_score": 92.0,  # ⚠️ 共識度極高，媒體已炒翻，代表股價已「大幅反映」
                "status": "Consensus Winner for Feynman CPO",
                "timeline": {"design_win": "2025-Q1", "pilot": "2026-Q1", "ramp_up": "2026-Q3"}
            },
            {
                "company_id": "3131.TW",  # 弘塑 (GrandProcess) - 先進封裝上游濕製程設備
                "name": "GrandProcess",
                "segment": "equipment",  # 設備商 (超前指標)
                "content_value_by_gen": {"Vera_Rubin": 10.0, "Feynman": 18.0, "Feynman_Next": 26.0}, # Feynman_Next 因 3D 堆疊難度倍增，設備價值暴漲
                "consensus_score": 35.0,  # 💡 共識度低，目前正值半導體設備去化空窗，市場尚未廣泛報導
                "status": "Entering Feynman_Next Spec Definition",
                "timeline": {"design_win": "2025-Q2", "pilot": "2025-Q4", "ramp_up": "2026-Q2"} # 設備放量比元件早 2 個季度
            },
            {
                "company_id": "3013.TW",  # 晟銘電 (MCT) - 散熱機殼
                "name": "MCT",
                "segment": "cooling",
                "content_value_by_gen": {"Vera_Rubin": 6.0, "Feynman": 9.5, "Feynman_Next": 4.0}, # Feynman_Next 朝晶片內直接水冷 (DTC) 發展，傳統機殼價值下降
                "consensus_score": 85.0,  # ⚠️ 共識度高，Rubin/Feynman 訂單已廣為人知
                "status": "Mature Rubin/Feynman Supplier",
                "timeline": {"design_win": "2025-Q1", "pilot": "2026-Q1", "ramp_up": "2026-Q3"}
            },
            {
                "company_id": "3324.TW",  # 雙鴻 (Auras) - 水冷 DTC 設計
                "name": "Auras",
                "segment": "cooling",
                "content_value_by_gen": {"Vera_Rubin": 8.0, "Feynman": 12.0, "Feynman_Next": 18.0}, # Feynman_Next 導入 DTC 直接水冷，技術升級帶來價值量增加
                "consensus_score": 52.0,  # 💡 共識度中等，水冷技術領先，但 Feynman_Next DTC 技術壁壘剛被少數人看懂
                "status": "Co-developing Feynman_Next DTC cooling",
                "timeline": {"design_win": "2025-Q3", "pilot": "2026-Q2", "ramp_up": "2026-Q4"}
            }
        ]

    def get_high_frequency_pricing(self, sector: str) -> Dict[str, Any]:
        """
        模擬/獲取高頻報價趨勢。
        """
        today = datetime.date.today()
        dates = [today - datetime.timedelta(weeks=i) for i in range(12)][::-1]
        
        # 模擬高頻光學/設備特用材料報價 (USD/unit)
        base_price = 150.0
        prices = []
        for idx in range(12):
            if idx < 5:
                # 底部打底
                price = base_price - idx * 0.8
            elif idx < 9:
                price = base_price - 4.0 + (idx - 5) * 1.2
            else:
                # 突破起漲
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
            
            # 計算內容價值變動百分比 (當前世代 -> 下一代)
            if val_current > 0:
                change_pct = (val_next - val_current) / val_current * 100
            else:
                change_pct = 999.0
                
            # 計算內容價值變動百分比 (下一代 -> 下下一代) - 超前預判洗牌
            if val_next > 0:
                future_change_pct = (val_future - val_next) / val_next * 100
            else:
                future_change_pct = 999.0
                
            # 判斷下下一代替代風險 (Content Value 顯著流失)
            substitution_risk = "LOW"
            if val_future < val_next * 0.7:
                # 內容價值流失超過 30%，代表有被替代的巨大風險 (如 FOCI 與 MCT 在 Feynman_Next 世代)
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

    def simulate_revenue_inflection(self, company_ids: List[str]) -> Dict[str, Any]:
        """
        營收 YoY 拐點與設備訂單 Backlog 領先指標模擬器。
        - 設備訂單 (Backlog) 領先下游成品營收 2 個季度 (6個月)。
        - 系統透過對比「設備訂單 YoY」與「成品營收 YoY」來捕捉最前瞻的起漲拐點。
        """
        results = {}
        today = datetime.date.today()
        
        for cid in company_ids:
            item = next((x for x in self.supply_chain_matrix if x["company_id"] == cid), None)
            if not item:
                continue
                
            name = item["name"]
            segment = item["segment"]
            
            # 模擬月度營收歷史數據 (台股為核心)
            base_monthly = 600.0
            # 去年低基期
            last_year_rev = [round(base_monthly * (1 + np.sin(i/3)*0.1 - 0.20), 1) for i in range(12)]
            # 今年已實現的月營收 (前 9 個月，目前依然處於平淡或去庫存谷底)
            current_year_rev = [round(base_monthly * (1 + np.sin(i/3)*0.08 - 0.15), 1) for i in range(9)]
            
            # 模擬未來 3 個月出貨放量 (Ramp-up)
            last_actual_rev = current_year_rev[-1]
            future_simulation = [
                round(last_actual_rev * 1.05, 1),
                round(last_actual_rev * 1.15, 1),
                round(last_actual_rev * 1.35, 1)
            ]
            all_current_year = current_year_rev + future_simulation
            
            # 計算成品營收 YoY
            yoy_curve = []
            for idx in range(12):
                yoy = (all_current_year[idx] - last_year_rev[idx]) / last_year_rev[idx] * 100
                yoy_curve.append(round(yoy, 2))
                
            # 💡 核心優化：模擬設備商或上游特用材料的「訂單 Backlog YoY」
            # 設備訂單比下游營收領先 2 個季度 (6個月) 爆發。
            # 因此當下游成品營收目前依然在谷底時，設備 Backlog 已在 6 個月前大幅飆升，現在正處於峰值。
            backlog_yoy_curve = []
            for idx in range(12):
                # 設備 Backlog 領先 6 個月爆發 (即 index + 6)
                if idx < 6:
                    backlog_yoy = yoy_curve[idx + 6] * 1.3 # 提前反應且增幅更大
                else:
                    # 後續因下游開始量產，設備拉貨動能逐漸平緩，但仍在高位
                    backlog_yoy = (100 - (idx - 6) * 10) * (1 + np.random.normal(0, 0.05))
                backlog_yoy_curve.append(round(max(backlog_yoy, 5.0), 2))
                
            future_yoy = yoy_curve[-3:]
            inflection_expected = future_yoy[-1] > future_yoy[0] and future_yoy[-1] > 20.0
            
            # 設備訂單是否已率先觸發爆發
            equipment_lead_active = backlog_yoy_curve[8] > 50.0 # 設備訂單 YoY 目前已大於 50%
            
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
