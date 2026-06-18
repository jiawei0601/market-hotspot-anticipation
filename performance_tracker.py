import os
import json
import datetime
import glob
from typing import Dict, List, Any
import yfinance as yf

# 設定資料儲存路徑 (使用 Git 追蹤的 JSON 實現無伺服器持久化)
WATCHLIST_FILE = "watchlist.json"
PERFORMANCE_REPORT = "reports/performance_tracker_summary.md"

def load_watchlist() -> List[Dict[str, Any]]:
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[⚠️ 警告] 讀取 watchlist.json 失敗: {e}，建立新名單。")
            return []
    return []

def save_watchlist(watchlist: List[Dict[str, Any]]):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False)
        print(f"Watchlist 已成功儲存至 {WATCHLIST_FILE}")
    except Exception as e:
        print(f"[❌ 錯誤] 儲存 watchlist.json 失敗: {e}")

def add_to_watchlist(company_id: str, name: str, entry_price: float, sector: str):
    """
    將新出現的標的加入觀察名單 (Watchlist)
    """
    watchlist = load_watchlist()
    
    # 檢查是否已在名單中，避免重複加入
    if any(item["company_id"] == company_id for item in watchlist):
        print(f"標的 {name} ({company_id}) 已在觀察名單中，跳過。")
        return
        
    new_target = {
        "company_id": company_id,
        "name": name,
        "sector": sector,
        "entry_date": datetime.date.today().strftime("%Y-%m-%d"),
        "entry_price": round(entry_price, 2),
        "current_price": round(entry_price, 2),
        "max_price_since": round(entry_price, 2),
        "min_price_since": round(entry_price, 2),
        "max_return_pct": 0.0,
        "min_return_pct": 0.0,
        "current_return_pct": 0.0,
        "status": "tracking", # tracking | closed
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    watchlist.append(new_target)
    save_watchlist(watchlist)
    print(f"🎉 成功將新標的 {name} ({company_id}) 加入觀察追蹤名單，進場基準價: {entry_price}")

def update_watchlist_daily_prices():
    """
    透過 yfinance 獲取每日 K 線數據，更新名單中所有標的自進場日以來的最高/最低/當前股價。
    """
    watchlist = load_watchlist()
    if not watchlist:
        print("觀察名單為空，無需更新價格。")
        return
        
    print(f"====== 開始每日 K 線數據追蹤與更新 (共 {len(watchlist)} 支標的) ======")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    for item in watchlist:
        if item["status"] != "tracking":
            continue
            
        cid = item["company_id"]
        entry_date_str = item["entry_date"]
        entry_price = item["entry_price"]
        
        print(f"正在更新 {item['name']} ({cid})，進場日期: {entry_date_str}...")
        
        try:
            # 下載自進場日至今的歷史日 K 線數據
            # yfinance 的 start date 需要格式為 YYYY-MM-DD
            # 設定結束日期為明天，以獲取今日最新收盤價
            end_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            df = yf.download(cid, start=entry_date_str, end=end_date, progress=False)
            
            if df.empty:
                print(f"[⚠️ 警告] 無法取得 {cid} 自 {entry_date_str} 至今的 K 線數據。")
                continue
                
            # 將欄位名稱轉為小寫
            df.columns = [c.lower() for c in df.columns]
            
            # 取得歷史 K 線之最高價、最低價及最新收盤價 (使用 ffill 處理盤中最新可能之 NaN)
            max_price = float(df["high"].max())
            min_price = float(df["low"].min())
            current_price = float(df["close"].ffill().iloc[-1])
            
            # 計算回報率
            current_return = (current_price - entry_price) / entry_price * 100
            max_return = (max_price - entry_price) / entry_price * 100
            min_return = (min_price - entry_price) / entry_price * 100 # 最大跌幅/回撤
            
            # 更新資料
            item["current_price"] = round(current_price, 2)
            item["max_price_since"] = round(max_price, 2)
            item["min_price_since"] = round(min_price, 2)
            item["current_return_pct"] = round(current_return, 2)
            item["max_return_pct"] = round(max_return, 2)
            item["min_return_pct"] = round(min_return, 2)
            item["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 定義結案條件 (例如：持有超過 12 個月，或達到特定的停利/停損，本系統為長期評估，預設維持 tracking)
            # 此處可供後續策略擴充
            
        except Exception as e:
            print(f"[❌ 錯誤] 更新 {cid} 股價失敗: {e}")
            
    save_watchlist(watchlist)
    print("====== 觀察名單價格更新完畢 ======")

def generate_performance_report() -> str:
    """
    計算系統勝率與績效，並產出 reports/performance_tracker_summary.md 評估報告。
    勝率定義：推薦標的在推薦後的最大潛在漲幅 (max_return_pct) 大於 +15% 視為「成功 (Win)」。
    """
    watchlist = load_watchlist()
    os.makedirs("reports", exist_ok=True)
    
    if not watchlist:
        empty_report = """# 觀察名單與系統勝率長期評估報告

目前觀察名單中尚無追蹤標的。當系統產出可行性報告並篩選出「非共識黃金建倉標的」後，將會自動在此處進行每日 K 線追蹤。
"""
        with open(PERFORMANCE_REPORT, "w", encoding="utf-8") as f:
            f.write(empty_report)
        return empty_report

    # 計算統計指標
    total_targets = len(watchlist)
    wins = 0
    total_current_return = 0.0
    total_max_return = 0.0
    total_max_drawdown = 0.0
    
    # 定義成功獲利目標為 15.0%
    target_win_threshold = 15.0
    
    for item in watchlist:
        if item["max_return_pct"] >= target_win_threshold:
            wins += 1
        total_current_return += item["current_return_pct"]
        total_max_return += item["max_return_pct"]
        total_max_drawdown += item["min_return_pct"]
        
    win_rate = (wins / total_targets) * 100 if total_targets > 0 else 0.0
    avg_current_return = total_current_return / total_targets
    avg_max_return = total_max_return / total_targets
    avg_max_drawdown = total_max_drawdown / total_targets # 平均最大跌幅

    # 建立 Markdown 報告
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    report = f"""# 系統長期績效與勝率評估報告

*最後更新日期：{today_str}*
*評估標準：推薦標的自進場日起，最大潛在漲幅 $\ge {target_win_threshold}\%$ 判定為「成功 (Win)」*

---

## 一、 系統綜合績效統計 (Summary Statistics)

| 指標名稱 | 統計結果 | 說明 |
| :--- | :--- | :--- |
| **追蹤標的總數** | **{total_targets} 支** | 系統主動甄選之非共識黃金建倉標的 |
| **系統勝率 (Win Rate)** | **{win_rate:.2f}%** | 最大漲幅達標 $\ge {target_win_threshold}\%$ 的標的比率 |
| **平均當前回報率** | **{avg_current_return:+.2f}%** | 若買入持有至今的等權重平均收益率 |
| **平均最大潛在漲幅** | **{avg_max_return:+.2f}%** | 推薦後平均最大波段漲幅 |
| **平均最大波段回撤** | **{avg_max_drawdown:.2f}%** | 推薦後曾遭遇的平均最大跌幅 |

---

## 二、 觀察標的明細追蹤表 (Detailed Watchlist)

| 股票代碼 / 名稱 | 技術板塊 | 進場日期 | 進場價 | 最新價 | 當前收益率 | 最大潛在漲幅 | 最大跌幅 (回撤) | 追蹤狀態 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""

    for item in watchlist:
        status_emoji = "🟢 追蹤中" if item["status"] == "tracking" else "🔴 已結案"
        report += (
            f"| **{item['company_id']}**<br>{item['name']} | {item['sector']} | "
            f"{item['entry_date']} | {item['entry_price']} | {item['current_price']} | "
            f"**{item['current_return_pct']:+.2f}%** | **{item['max_return_pct']:+.2f}%** | "
            f"{item['min_return_pct']:.2f}% | {status_emoji} |\n"
        )
        
    report += """
---

## 三、 長期績效評估方法論說明
1. **進場基準判定**：當系統透過 LangGraph 品質評審 (PASS) 輸出報告時，會同步呼叫營收基期與設備 Backlog 模擬器。若篩選出「共識度低於 60% 且設備 Backlog YoY > 50%、下游營收在谷底」的非共識黃金建倉標的，即以**報告產生當日的收盤價**作為推薦基準買入價，並於本名單中開立追蹤。
2. **K 線追蹤防看前偏差**：系統每天利用 yfinance 自動拉取追蹤標的之每日日 K 線數據，動態刷新「推薦日之後的最高價與最低價」，排除任何歷史 look-ahead bias。
3. **退場與勝率計算**：勝率專注於中期（12-18個月）的「波段最大漲幅能否達標 ($15\%$)」，作為系統能否精確領先市場預見熱點的勝率證明。
"""

    with open(PERFORMANCE_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"績效評估報告已儲存至 {PERFORMANCE_REPORT}")
    return report

if __name__ == "__main__":
    # 本地測試
    # 模擬加入一隻標的
    # add_to_watchlist("3131.TW", "GrandProcess", 1100.0, "CPO_Optical_Transceiver")
    update_watchlist_daily_prices()
    generate_performance_report()
