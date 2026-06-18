import os
import sys
import smtplib
import glob
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# 自動讀取本地 .env 檔案並寫入環境變數 (本地測試用)
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, val = stripped.split("=", 1)
                os.environ[key.strip()] = val.strip()

def send_latest_report():
    print("====== 啟動報告 Email 發送程序 ======")
    
    # 讀取發信環境變數
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")
    
    if not all([smtp_username, smtp_password, receiver_email]):
        print("[⚠️ 警告] 缺少必要的發信配置 (SMTP_USERNAME, SMTP_PASSWORD, RECEIVER_EMAIL)。")
        print("請確保在 .env 或 GitHub Secrets 中已設定這些環境變數。發信程序終止。")
        return False

    # 尋找 reports/ 目錄下最新產出的報告 md 檔案
    report_files = glob.glob("reports/*.md")
    if not report_files:
        print("[❌ 錯誤] 在 reports/ 目錄下找不到任何研究報告！")
        return False
        
    # 依檔案修改時間排序，取得最新的一份
    latest_report_path = max(report_files, key=os.path.getmtime)
    report_filename = os.path.basename(latest_report_path)
    print(f"尋找到最新報告: {latest_report_path}")
    
    # 讀取報告內容
    with open(latest_report_path, "r", encoding="utf-8") as f:
        report_content = f.read()

    # 建立 Email 容器
    msg = MIMEMultipart()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    msg["Subject"] = f"【每週市場熱點預見報告】{today_str} - {report_filename.split('-')[3].replace('.md', '')}"
    msg["From"] = smtp_username
    msg["To"] = receiver_email
    
    # 電子郵件內文
    body_text = f"""您好：
    
這是系統每週一自動生成的 12-18 個月中期市場熱點預見報告。
最新報告檔案：{report_filename}

下方為報告摘要，完整 Markdown 檔案已作為附件發送，您可以直接下載查看。

---
報告摘要內容：
---
{report_content[:2000]}... (更多內容請見附件)

---
本信件由 1c7f31f6-0579-46b8-b5d2-7abbafb1fcf5 自動化排程發送。
"""
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    
    # 加入 Markdown 報告作為附件
    try:
        with open(latest_report_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="octet-stream")
            attachment.add_header("Content-Disposition", "attachment", filename=report_filename)
            msg.attach(attachment)
    except Exception as e:
        print(f"[❌ 錯誤] 無法讀取附件檔案: {e}")
        return False
        
    # 連線 SMTP 伺服器並發送
    try:
        print(f"正在連線至 SMTP 伺服器 {smtp_server}:{smtp_port}...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls() # 啟用安全傳輸
        server.login(smtp_username, smtp_password)
        
        print("正在發送電子郵件...")
        server.sendmail(smtp_username, receiver_email, msg.as_string())
        server.close()
        print("🎉 Email 發送成功！")
        return True
    except Exception as e:
        print(f"[❌ 錯誤] 發送 Email 失敗，詳細原因: {e}")
        return False

if __name__ == "__main__":
    send_latest_report()
