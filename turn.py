import os
import time
import json
import socket
import urllib.parse
import subprocess
import tempfile
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# ================= 配置区 =================
# Xray 核心路径 (请确保路径正确)
XRAY_PATH = r"D:\wall\v2rayn\v2rayN\bin\xray\xray.exe"

# 输入文件
INPUT_FILE = "ip_list.txt"

# 输出文件
OUTPUT_PASS_LINKS = "delay_pass_links.txt"       # 明文导入链接
OUTPUT_SUBSCRIBE = "delay_pass_sub.txt"          # Base64 订阅格式
OUTPUT_REPORT = "delay_pass_report.txt"          # 测试报告

# 节点基础信息 (你的 Cloudflare Workers 配置)
DOMAIN = "ak.085580.xyz"
UUID = "7788b4b7-5ea1-4736-bcec-753af6c7f2c7"

# 测试参数
TEST_URL = "https://www.gstatic.com/generate_204" # 谷歌官方连通性测试接口
TIMEOUT = 10                                      # 整体请求超时时间（秒）
MAX_WORKERS = 10                                  # 并发测试的线程数
# ==========================================

def get_free_port():
    """获取一个本地可用的随机端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def build_vless_link(ip, port, country, city):
    """生成 VLESS 分享链接，包含国家和城市备注"""
    raw_path = f"/turn://{ip}:{port}?ed=2560"
    encoded_path = urllib.parse.quote(raw_path, safe='')
    
    # 组合备注并进行 URL 编码，防止中文导致部分客户端解析报错
    remark = f"{country}-{city}-{ip}-{port}"
    encoded_remark = urllib.parse.quote(remark)
    
    link = (
        f"vless://{UUID}@{DOMAIN}:443?"
        f"encryption=none&security=tls&sni={DOMAIN}&"
        f"type=ws&host={DOMAIN}&path={encoded_path}#{encoded_remark}"
    )
    return link

def generate_xray_config(local_port, ip, port):
    """生成 Xray 的临时配置文件 (HTTP 入站, VLESS+WS+TLS 出站)"""
    raw_path = f"/turn://{ip}:{port}?ed=2560"
    
    config = {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": local_port,
            "protocol": "http", # 使用 HTTP 入站，避免 Python 处理 SOCKS 时的 DNS 泄漏和握手异常
            "settings": {"timeout": 0}
        }],
        "outbounds": [{
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": DOMAIN,
                    "port": 443,
                    "users": [{"id": UUID, "encryption": "none"}]
                }]
            },
            "streamSettings": {
                "network": "ws",
                "security": "tls",
                "tlsSettings": {"serverName": DOMAIN},
                "wsSettings": {
                    "path": raw_path,
                    "headers": {"Host": DOMAIN}
                }
            }
        }]
    }
    return config

def test_node(ip, port, country, city):
    """测试单个节点，返回 (是否成功, 延迟毫秒/错误信息, vless链接, 国家, 城市)"""
    link = build_vless_link(ip, port, country, city)
    local_port = get_free_port()
    config_dict = generate_xray_config(local_port, ip, port)
    
    # 将配置写入临时文件
    fd, temp_conf_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f)
        
    xray_process = None
    try:
        # 启动 Xray 进程 (隐藏窗口)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        xray_process = subprocess.Popen(
            [XRAY_PATH, "run", "-c", temp_conf_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo
        )
        
        # 给 Xray 核心 1 秒钟的冷启动和端口绑定时间
        time.sleep(1.0)
        
        # 配置代理，强制所有流量走本地 Xray HTTP 入站
        proxies = {
            "http": f"http://127.0.0.1:{local_port}",
            "https": f"http://127.0.0.1:{local_port}"
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        start_time = time.time()
        # 发起真实连通性测试
        response = requests.get(TEST_URL, proxies=proxies, headers=headers, timeout=TIMEOUT)
        delay = int((time.time() - start_time) * 1000)
        
        # 204 No Content 是连通性测试的标志性成功状态码 (200 也算成功)
        if response.status_code in [200, 204]:
            return True, delay, link, country, city
        else:
            return False, f"HTTP_{response.status_code}", link, country, city
            
    except requests.exceptions.Timeout:
        return False, "Timeout", link, country, city
    except requests.exceptions.RequestException:
        return False, "Connection_Error", link, country, city
    except Exception as e:
        return False, f"Error_{str(e)[:20]}", link, country, city
    finally:
        # 彻底清理进程和临时配置文件
        if xray_process:
            xray_process.kill()
            xray_process.wait()
        try:
            os.remove(temp_conf_path)
        except OSError:
            pass

def main():
    if not os.path.exists(XRAY_PATH):
        print(f"[错误] 找不到 xray.exe，请检查路径：{XRAY_PATH}")
        return
        
    if not os.path.exists(INPUT_FILE):
        print(f"[错误] 找不到输入文件：{INPUT_FILE}")
        return

    # 1. 解析 TXT 文件 (支持新的带国家城市的表格格式)
    candidates = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            # 跳过表头和分隔线
            if 'IP地址' in line or '---' in line:
                continue
                
            parts = [p.strip() for p in line.split('|')]
            # 确保至少有 4 列 (IP, 端口, 国家, 城市)
            if len(parts) >= 4:
                ip = parts[0]
                port = parts[1]
                country = parts[2]
                city = parts[3]
                
                # 简单校验 IP 和端口是否合法
                if ip and port.isdigit():
                    candidates.append((ip, port, country, city))

    if not candidates:
        print("[警告] 没有在输入文件中解析到有效的节点数据！请检查 txt 格式。")
        return

    print(f"[*] 成功解析 {len(candidates)} 个候选节点，开始测速 (并发数: {MAX_WORKERS})...")
    
    pass_links = []
    report_lines = []
    
    # 2. 并发测试
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_node = {
            executor.submit(test_node, ip, port, country, city): (ip, port, country, city) 
            for ip, port, country, city in candidates
        }
        
        for future in as_completed(future_to_node):
            ip, port, country, city = future_to_node[future]
            success, result, link, _, _ = future.result()
            
            if success:
                print(f"[通过] {country}-{city} | {ip}:{port} | 延迟: {result}ms")
                pass_links.append(link)
                report_lines.append(f"PASS  | {ip}:{port:<5} | {country}-{city} | Delay: {result}ms")
            else:
                print(f"[失败] {country}-{city} | {ip}:{port} | 原因: {result}")
                report_lines.append(f"FAIL  | {ip}:{port:<5} | {country}-{city} | Reason: {result}")

    # 3. 输出结果
    raw_links_str = "\n".join(pass_links)
    
    # 写入明文链接文件
    with open(OUTPUT_PASS_LINKS, 'w', encoding='utf-8') as f:
        f.write(raw_links_str)
        
    # 写入 Base64 订阅文件
    if pass_links:
        # 使用 standard b64encode，v2rayN 订阅标准要求
        b64_links = base64.b64encode(raw_links_str.encode('utf-8')).decode('utf-8')
        with open(OUTPUT_SUBSCRIBE, 'w', encoding='utf-8') as f:
            f.write(b64_links)
            
    # 写入测试报告
    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print(f"\n[*] ================= 测试完成 =================")
    print(f"[*] 节点总数: {len(candidates)} | 可用节点: {len(pass_links)}")
    print(f"[*] 明文链接已保存至: {OUTPUT_PASS_LINKS}")
    if pass_links:
        print(f"[*] 订阅文件已保存至: {OUTPUT_SUBSCRIBE} (可用作 v2rayN 本地订阅源)")
    print(f"[*] 详细测试报告已存: {OUTPUT_REPORT}")

if __name__ == "__main__":
    main()
