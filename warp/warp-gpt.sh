#!/bin/bash

# 定义配置文件路径
WG_CONF="/etc/wireguard/warp.conf"
INTERFACE="warp"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
PLAIN='\033[0m'

# 检查是否为 root
[[ $EUID -ne 0 ]] && echo -e "${RED}错误: 必须使用 root 用户运行此脚本！${PLAIN}" && exit 1

# 检查操作系统类型
get_os_type() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo $ID
    else
        echo "unknown"
    fi
}

# 1. 环境检查与安装
check_env() {
    local os_type
    os_type=$(get_os_type)

    # 检查 wireguard-tools 是否安装
    if ! command -v wg-quick &> /dev/null; then
        echo -e "${YELLOW}正在安装 wireguard-tools...${PLAIN}"
        case $os_type in
            debian|ubuntu)
                apt update && apt install -y wireguard curl openresolv ip6tables
                ;;
            arch|manjaro)
                pacman -Syu --noconfirm wireguard-tools curl openresolv ip6tables
                ;;
            fedora)
                dnf install -y wireguard-tools curl openresolv ip6tables
                ;;
            centos|rocky)
                yum install -y epel-release
                yum install -y wireguard-tools curl openresolv ip6tables
                ;;
            alpine)
                apk update && apk add wireguard-tools curl openresolv ip6tables
                ;;
            *)
                echo -e "${RED}未知操作系统类型: $os_type，请手动安装 wireguard-tools！${PLAIN}"
                exit 1
                ;;
        esac
    fi

    if [ ! -f "$WG_CONF" ]; then
        echo -e "${RED}错误: 未找到配置文件 $WG_CONF${PLAIN}"
        echo -e "${YELLOW}请先将生成的 WireGuard 配置上传至该路径！${PLAIN}"
        exit 1
    fi
}

# 2. 修改路由策略 (修改 AllowedIPs)
set_route() {
    local mode=$1
    echo -e "${YELLOW}正在停止 WARP 接口...${PLAIN}"
    wg-quick down $INTERFACE 2>/dev/null

    # 备份配置文件
    cp $WG_CONF "${WG_CONF}.bak"

    # 使用 sed 修改 AllowedIPs
    # 注意：这里假设配置文件中只有一行 AllowedIPs
    case $mode in
        4)
            # IPv4 出栈：接管 0.0.0.0/0
            echo -e "${GREEN}设置模式: 仅 IPv4 流量走 WARP${PLAIN}"
            sed -i 's/^AllowedIPs.*/AllowedIPs = 0.0.0.0\/0/' $WG_CONF
            ;;
        6)
            # IPv6 出栈：接管 ::/0
            echo -e "${GREEN}设置模式: 仅 IPv6 流量走 WARP (SSH 安全)${PLAIN}"
            sed -i 's/^AllowedIPs.*/AllowedIPs = ::\/0/' $WG_CONF
            ;;
        all)
            # 双栈出栈
            echo -e "${GREEN}设置模式: 所有流量(IPv4+IPv6)走 WARP${PLAIN}"
            sed -i 's/^AllowedIPs.*/AllowedIPs = 0.0.0.0\/0, ::\/0/' $WG_CONF
            ;;
    esac

    echo -e "${YELLOW}正在启动 WARP 接口...${PLAIN}"
    wg-quick up $INTERFACE

    show_ip
}

# 3. 显示当前 IP
show_ip() {
    echo -e "\n${GREEN}当前 IP 信息:${PLAIN}"
    echo -n "IPv4: "
    curl -s4m5 ip.sb --interface $INTERFACE || echo "无连接"
    echo -n "IPv6: "
    curl -s6m5 ip.sb --interface $INTERFACE || echo "无连接"
}

# 4. 菜单
show_menu() {
    clear
    echo -e "=================================="
    echo -e "   WARP 切换脚本"
    echo -e "=================================="
    echo -e "1. 启用 WARP IPv4 出栈 "
    echo -e "2. 启用 WARP IPv6 出栈 "
    echo -e "3. 启用 双栈全局出栈 "
    echo -e "4. 关闭 WARP"
    echo -e "5. 查看当前状态"
    echo -e "0. 退出"
    echo -e "=================================="
    read -p "请输入选项 [0-5]: " num

    case "$num" in
        1) set_route 4 ;;
        2) set_route 6 ;;
        3) set_route all ;;
        4) wg-quick down $INTERFACE ;;
        5) show_ip ;;
        0) exit 0 ;;
        *) echo -e "${RED}无效选项${PLAIN}" ;;
    esac
}

# 执行逻辑
check_env
if [ -n "$1" ]; then
    # 支持命令行传参: bash warp.sh 4
    case "$1" in
        4) set_route 4 ;;
        6) set_route 6 ;;
        all) set_route all ;;
        down) wg-quick down $INTERFACE ;;
        status) show_ip ;;
        *) echo "用法: $0 [4|6|all|down|status]" ;;
    esac
else
    show_menu
fi
