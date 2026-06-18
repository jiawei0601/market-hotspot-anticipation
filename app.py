import os
import datetime
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
from apscheduler.schedulers.background import BackgroundScheduler
import uvicorn

# 自動讀取本地 .env 檔案並寫入環境變數 (本地測試用，Railway 上會使用平台注入的變數)
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, val = stripped.split("=", 1)
                os.environ[key.strip()] = val.strip()

# 引入狀態機
from main_agent import run_hotspot_scan

app = FastAPI(title="Market Hotspot Anticipation Service")
scheduler = BackgroundScheduler()

# 定義自動化定時工作
def weekly_task():
    print(f"=== [排程觸發] 開始每週熱點掃描 ({datetime.datetime.now()}) ===")
    try:
        run_hotspot_scan("CPO_Optical_Transceiver")
        print("=== [排程觸發] 執行完畢 ===")
    except Exception as e:
        print(f"[❌ 排程出錯] 原因: {e}")

# 啟動排程器 (設定台灣時間每週一早上 07:30)
@app.on_event("startup")
def start_scheduler():
    # 使用 Asia/Taipei 時區設定每週一早上 7:30 執行，不受主機/容器系統時區影響
    scheduler.add_job(
        weekly_task, 
        'cron', 
        day_of_week='mon', 
        hour=7, 
        minute=30, 
        timezone='Asia/Taipei',
        id='weekly_research'
    )
    scheduler.start()
    print("⏰ Background Scheduler 已成功啟動，設定每週一台灣時間 07:30 執行！")

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()
    print("Scheduler 已關閉。")

@app.get("/")
def home():
    jobs = scheduler.get_jobs()
    next_run = jobs[0].next_run_time if jobs else None
    
    # 搜尋最新報告
    latest_report = "無"
    if os.path.exists("reports"):
        import glob
        files = glob.glob("reports/*.md")
        if files:
            latest_report = os.path.basename(max(files, key=os.path.getmtime))
            
    return {
        "status": "online",
        "service": "12-18 Months Market Hotspot Anticipation",
        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Asia/Taipei",
        "next_scheduled_run": str(next_run) if next_run else "未設定",
        "latest_generated_report": latest_report,
        "links": {
            "latest_report_web_view": "/latest-report",
            "performance_tracker_web_view": "/latest-performance"
        }
    }

@app.get("/performance")
def get_performance():
    import json
    watchlist = []
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json", "r", encoding="utf-8") as f:
                watchlist = json.load(f)
        except Exception:
            pass
            
    total_targets = len(watchlist)
    wins = sum(1 for item in watchlist if item["max_return_pct"] >= 15.0)
    win_rate = (wins / total_targets) * 100 if total_targets > 0 else 0.0
    
    return {
        "total_tracked_assets": total_targets,
        "wins_reached_15pct_target": wins,
        "historical_win_rate_pct": round(win_rate, 2),
        "tracked_assets": watchlist
    }

# ==================== HTML 精美渲染模板與端點 ====================

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;700;800&family=Noto+Sans+TC:wght@300;400;500;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
    <style>
        :root {
            --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            --text-color: #f1f5f9;
            --primary-cyan: #38bdf8;
            --accent-green: #10b981;
            --accent-orange: #f59e0b;
            --card-bg: rgba(30, 41, 59, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --table-border: rgba(255, 255, 255, 0.06);
        }
        body {
            font-family: 'Inter', 'Noto Sans TC', -apple-system, sans-serif;
            background: var(--bg-gradient);
            background-attachment: fixed;
            color: var(--text-color);
            margin: 0;
            padding: 0;
            line-height: 1.7;
        }
        .header {
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .logo {
            font-family: 'Outfit', sans-serif;
            font-size: 1.25rem;
            font-weight: 800;
            color: var(--primary-cyan);
            letter-spacing: 1px;
            display: flex;
            align-items: center;
        }
        .logo span {
            color: #fff;
            margin-left: 6px;
        }
        .nav-links a {
            color: #94a3b8;
            text-decoration: none;
            margin-left: 20px;
            font-size: 0.9rem;
            font-weight: 500;
            transition: color 0.2s;
        }
        .nav-links a:hover, .nav-links a.active {
            color: var(--primary-cyan);
        }
        .container {
            max-width: 960px;
            margin: 40px auto;
            padding: 40px;
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        }
        /* Markdown 內容精細排版 */
        h1, h2, h3, h4 {
            font-family: 'Outfit', 'Noto Sans TC', sans-serif;
            font-weight: 700;
            color: #ffffff;
            margin-top: 1.8em;
            margin-bottom: 0.6em;
        }
        h1 {
            font-size: 2.2rem;
            color: var(--primary-cyan);
            border-bottom: 2px solid rgba(56, 189, 248, 0.2);
            padding-bottom: 12px;
            margin-top: 0;
            background: linear-gradient(to right, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        h2 {
            font-size: 1.6rem;
            border-left: 5px solid var(--accent-green);
            padding-left: 14px;
        }
        h3 {
            font-size: 1.25rem;
            color: #e2e8f0;
        }
        p {
            color: #cbd5e1;
            margin-bottom: 1.5em;
        }
        /* 表格現代化樣式 */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 28px 0;
            background: rgba(15, 23, 42, 0.4);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--table-border);
        }
        th, td {
            padding: 14px 18px;
            text-align: left;
            border-bottom: 1px solid var(--table-border);
            font-size: 0.95rem;
        }
        th {
            background-color: rgba(56, 189, 248, 0.08);
            color: var(--primary-cyan);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }
        tr:last-child td {
            border-bottom: none;
        }
        tr:hover td {
            background: rgba(255, 255, 255, 0.01);
        }
        /* 區塊引用與警示 */
        blockquote {
            background: rgba(56, 189, 248, 0.05);
            border-left: 4px solid var(--primary-cyan);
            padding: 16px 20px;
            margin: 20px 0;
            border-radius: 0 12px 12px 0;
        }
        blockquote p {
            margin: 0;
            color: #93c5fd;
            font-style: italic;
        }
        /* 程式碼與公式 */
        pre {
            background: #0f172a;
            padding: 18px;
            border-radius: 12px;
            overflow-x: auto;
            border: 1px solid var(--border-color);
        }
        code {
            font-family: 'Fira Code', 'Courier New', monospace;
            background: rgba(255, 255, 255, 0.07);
            padding: 3px 7px;
            border-radius: 6px;
            color: #f472b6;
            font-size: 0.9rem;
        }
        pre code {
            background: none;
            padding: 0;
            color: #e2e8f0;
        }
        hr {
            border: none;
            border-top: 1px solid var(--border-color);
            margin: 40px 0;
        }
        a {
            color: var(--primary-cyan);
            text-decoration: none;
            transition: opacity 0.2s;
        }
        a:hover {
            opacity: 0.8;
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">ANTIGRAVITY<span>RESEARCH</span></div>
        <div class="nav-links">
            <a href="/latest-report" id="nav-rep">每週熱點報告</a>
            <a href="/latest-performance" id="nav-perf">系統績效評估</a>
        </div>
    </div>
    <div class="container" id="content">正在渲染報告內容，請稍候...</div>
    <script>
        // 設定導航欄 active 樣式
        const path = window.location.pathname;
        if (path === '/latest-report') document.getElementById('nav-rep').classList.add('active');
        if (path === '/latest-performance') document.getElementById('nav-perf').classList.add('active');

        // 讀取 Raw Markdown 字串並使用 marked 渲染
        const rawMarkdown = `{markdown_content}`;
        document.getElementById('content').innerHTML = marked.parse(rawMarkdown);

        // 動態渲染 ApexCharts K 線圖
        const watchlistData = {watchlist_data_json};
        if (watchlistData && watchlistData.length > 0) {
            watchlistData.forEach(item => {
                const cleanId = 'chart_' + item.company_id.replace('.', '_');
                const container = document.getElementById(cleanId);
                if (container && item.kline_data && item.kline_data.length > 0) {
                    const entryTime = new Date(item.entry_date).getTime();
                    
                    const options = {
                        series: [{
                            name: '收盤價',
                            data: item.kline_data.map(k => [new Date(k.date).getTime(), k.close])
                        }],
                        chart: {
                            type: 'area',
                            height: 240,
                            background: 'transparent',
                            toolbar: { show: false },
                            foreColor: '#94a3b8'
                        },
                        colors: ['#38bdf8'],
                        fill: {
                            type: 'gradient',
                            gradient: {
                                shadeIntensity: 1,
                                opacityFrom: 0.3,
                                opacityTo: 0.05,
                                stops: [0, 90, 100]
                            }
                        },
                        stroke: { curve: 'smooth', width: 2 },
                        xaxis: {
                            type: 'datetime',
                            axisBorder: { show: false },
                            axisTicks: { show: false }
                        },
                        yaxis: {
                            labels: {
                                formatter: (val) => val.toFixed(1)
                            }
                        },
                        grid: { borderColor: 'rgba(255,255,255,0.04)' },
                        annotations: {
                            xaxis: [{
                                x: entryTime,
                                strokeDashArray: 4,
                                borderColor: '#10b981',
                                label: {
                                    borderColor: '#10b981',
                                    style: { color: '#fff', background: '#10b981', fontSize: '11px', padding: [3, 6] },
                                    text: '列入觀察 (' + item.entry_date + ')'
                                }
                            }],
                            points: [{
                                x: entryTime,
                                y: item.entry_price,
                                marker: {
                                    size: 6,
                                    fillColor: '#10b981',
                                    strokeColor: '#fff',
                                    radius: 2
                                },
                                label: {
                                    borderColor: '#10b981',
                                    offsetY: -10,
                                    style: { color: '#fff', background: '#10b981', fontSize: '11px', padding: [3, 6] },
                                    text: '進場點: ' + item.entry_price
                                }
                            }]
                        },
                        tooltip: {
                            theme: 'dark',
                            x: { format: 'yyyy-MM-dd' }
                        }
                    };
                    const chart = new ApexCharts(container, options);
                    chart.render();
                }
            });
        }
    </script>
</body>
</html>
"""

@app.get("/latest-report", response_class=HTMLResponse)
def get_latest_report_web_view():
    """
    固定連結：以精美網頁形式直接渲染最新產出的市場熱點可行性評估報告
    """
    if not os.path.exists("reports"):
        return HTMLResponse("<h2>目前尚未產出任何報告</h2>", status_code=404)
        
    import glob
    # 尋找所有可行性報告，排除績效評估報告
    report_files = [f for f in glob.glob("reports/*.md") if "performance" not in f]
    if not report_files:
        return HTMLResponse("<h2>尚未有市場熱點可行性報告</h2>", status_code=404)
        
    # 取得最新的一份
    latest_file = max(report_files, key=os.path.getmtime)
    
    with open(latest_file, "r", encoding="utf-8") as f:
        md_content = f.read()
        
    # 跳過 js 模板的轉義問題，將反引號作簡單處理以防 js parsing error
    safe_md_content = md_content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    
    html_page = HTML_TEMPLATE.format(
        title="最新市場熱點預見報告",
        markdown_content=safe_md_content,
        watchlist_data_json="[]"
    )
    return HTMLResponse(html_page)

@app.get("/latest-performance", response_class=HTMLResponse)
def get_latest_performance_web_view():
    """
    固定連結：以精美網頁形式渲染觀察名單與系統勝率長期統計評估報告
    """
    performance_file = "reports/performance_tracker_summary.md"
    if not os.path.exists(performance_file):
        return HTMLResponse("<h2>尚未產生績效評估報告</h2>", status_code=404)
        
    with open(performance_file, "r", encoding="utf-8") as f:
        md_content = f.read()
        
    safe_md_content = md_content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    
    watchlist_json = "[]"
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json", "r", encoding="utf-8") as f:
                watchlist_json = f.read()
        except Exception:
            pass
            
    html_page = HTML_TEMPLATE.format(
        title="系統績效與勝率統計報告",
        markdown_content=safe_md_content,
        watchlist_data_json=watchlist_json
    )
    return HTMLResponse(html_page)

# =================================================================

# 異步執行包裝
def trigger_analysis():
    try:
        run_hotspot_scan("CPO_Optical_Transceiver")
    except Exception as e:
        print(f"手動觸發執行失敗: {e}")

@app.post("/run")
def trigger_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(trigger_analysis)
    return JSONResponse(
        content={
            "status": "processing",
            "message": "熱點分析任務已在背景啟動，請稍候重新載入頁面。"
        }
    )

if __name__ == "__main__":
    # 讀取 Railway 的 Port (預設為 8080)
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
