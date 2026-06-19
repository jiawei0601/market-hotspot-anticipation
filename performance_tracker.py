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
            print(f"[WARN] 讀取 watchlist.json 失敗: {e}，建立新名單。")
            return []
    return []

def save_watchlist(watchlist: List[Dict[str, Any]]):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False)
        print(f"Watchlist 已成功儲存至 {WATCHLIST_FILE}")
    except Exception as e:
        print(f"[ERROR] 儲存 watchlist.json 失敗: {e}")

def add_to_watchlist(company_id: str, name: str, entry_price: float, sector: str, entry_date: str = ""):
    """
    將新出現的標的加入觀察名單 (Watchlist)
    """
    watchlist = load_watchlist()
    
    # 檢查是否已在名單中，避免重複加入
    if any(item["company_id"] == company_id for item in watchlist):
        print(f"標的 {name} ({company_id}) 已在觀察名單中，跳過。")
        return
        
    date_str = entry_date if entry_date else datetime.date.today().strftime("%Y-%m-%d")
    new_target = {
        "company_id": company_id,
        "name": name,
        "sector": sector,
        "entry_date": date_str,
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
    print(f"[OK] 成功將新標的 {name} ({company_id}) 加入觀察追蹤名單，進場基準價: {entry_price}，日期: {date_str}")

def update_watchlist_daily_prices(as_of_date: str = ""):
    """
    透過 yfinance 獲取每日 K 線數據，更新名單中所有標的自進場日以來的最高/最低/當前股價。
    - 支援 as_of_date 進行點時間 (Point-in-Time) 數據截斷，避免未來數據偏誤。
    """
    watchlist = load_watchlist()
    if not watchlist:
        print("觀察名單為空，無需更新價格。")
        return
        
    print(f"====== 開始 K 線數據追蹤與更新 (共 {len(watchlist)} 支標的) ======")
    today_limit = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date() if as_of_date else datetime.date.today()
    
    for item in watchlist:
        if item["status"] != "tracking":
            continue
            
        cid = item["company_id"]
        entry_date_str = item["entry_date"]
        entry_price = item["entry_price"]
        
        print(f"正在更新 {item['name']} ({cid})，進場日期: {entry_date_str}...")
        
        try:
            # 計算前推 3 個月的 start_date，確保有足夠的歷史 K 線
            entry_date = datetime.datetime.strptime(entry_date_str, "%Y-%m-%d").date()
            start_date = (entry_date - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
            
            # 限制終止日，防止讀取未來價格
            end_date_limit = (today_limit + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            
            df = yf.download(cid, start=start_date, end=end_date_limit, progress=False)
            
            if df.empty:
                print(f"[WARN] 無法取得 {cid} 自 {start_date} 至今的 K 線數據。")
                continue
                
            # 將欄位名稱轉為小寫，並處理 MultiIndex
            if df.columns.nlevels > 1:
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            
            # 儲存全數日 K 線數據，提供前端網頁繪製圖表使用
            kline_list = []
            for date_idx, row in df.iterrows():
                kline_list.append({
                    "date": date_idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["open"]), 2),
                    "high": round(float(row["high"]), 2),
                    "low": round(float(row["low"]), 2),
                    "close": round(float(row["close"]), 2),
                    "volume": int(row["volume"])
                })
            item["kline_data"] = kline_list
            
            # 核心修正：計算「進場以來」的最高、最低、當前收盤價，必須只過濾進場日之後的數據！
            df_after_entry = df.loc[entry_date_str:]
            if df_after_entry.empty:
                # 剛加入當天如果無後續 K 線，使用最新一筆作為基準
                df_after_entry = df.tail(1)
                
            # 取得歷史 K 線之最高價、最低價及最新收盤價 (使用 ffill 處理盤中最新可能之 NaN)
            max_price = float(df_after_entry["high"].max())
            min_price = float(df_after_entry["low"].min())
            current_price = float(df_after_entry["close"].ffill().iloc[-1])
            
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
            print(f"[ERROR] 更新 {cid} 股價失敗: {e}")
            
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

## 三、 個股歷史走勢與進場標記 (Interactive Charts)
"""
    for item in watchlist:
        chart_id = f"chart_{item['company_id'].replace('.', '_')}"
        report += f"\n### 📈 {item['name']} ({item['company_id']}) 走勢與進場點\n"
        report += f'<div id="{chart_id}" class="stock-chart" style="margin: 20px 0; height: 260px; background: rgba(15, 23, 42, 0.4); border-radius: 12px; border: 1px solid rgba(255,255,255,0.06); padding: 16px;"></div>\n'

    report += """
---

## 四、 長期績效評估方法論說明
1. **進場基準判定**：當系統透過 LangGraph 品質評審 (PASS) 輸出報告時，會同步呼叫營收基期與設備 Backlog 模擬器。若篩選出「共識度低於 60% 且設備 Backlog YoY > 50%、下游營收在谷底」的非共識黃金建倉標的，即以**報告產生當日的收盤價**作為推薦基準買入價，並於本名單中開立追蹤。
2. **K 線追蹤與時間加長**：系統自動獲取該股進場日期**往前推 3 個月 (90天)** 至今日的歷史日 K 線。計算收益率與最高/最低波段價格時，僅過濾並計算進場後之數據，防範 NaN 出錯，同時於圖表上標記進場錨點。
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
