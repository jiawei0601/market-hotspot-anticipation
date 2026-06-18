import os
import datetime
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
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

# 引入狀態機與發信
from main_agent import run_hotspot_scan
from send_email import send_latest_report

app = FastAPI(title="Market Hotspot Anticipation Service")
scheduler = BackgroundScheduler()

# 定義自動化定時工作
def weekly_task():
    print(f"=== [排程觸發] 開始每週熱點掃描與發信 ({datetime.datetime.now()}) ===")
    try:
        run_hotspot_scan("CPO_Optical_Transceiver")
        send_latest_report()
        print("=== [排程觸發] 執行完畢 ===")
    except Exception as e:
        print(f"[❌ 排程出錯] 原因: {e}")

# 啟動排程器 (設定台灣時間每週一早上 08:00)
@app.on_event("startup")
def start_scheduler():
    # 使用 Asia/Taipei 時區設定每週一早上 8:00 執行，不受主機/容器系統時區影響
    scheduler.add_job(
        weekly_task, 
        'cron', 
        day_of_week='mon', 
        hour=8, 
        minute=0, 
        timezone='Asia/Taipei',
        id='weekly_research'
    )
    scheduler.start()
    print("⏰ Background Scheduler 已成功啟動，設定每週一台灣時間 08:00 執行！")

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
        "latest_generated_report": latest_report
    }

# 異步執行包裝
def trigger_analysis_and_mail():
    try:
        run_hotspot_scan("CPO_Optical_Transceiver")
        send_latest_report()
    except Exception as e:
        print(f"手動觸發執行失敗: {e}")

@app.post("/run")
def trigger_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(trigger_analysis_and_mail)
    return JSONResponse(
        content={
            "status": "processing",
            "message": "熱點分析與發信任務已在背景啟動，請稍候查收郵件。"
        }
    )

if __name__ == "__main__":
    # 讀取 Railway 的 Port (預設為 8080)
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
