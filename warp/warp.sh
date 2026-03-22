#!/usr/bin/env bash
# Description: Cloudflare WARP Installer
# System Required: Debian, Ubuntu, Fedora, CentOS, Oracle Linux, Rocky, AlmaLinux, Arch Linux, Alpine
# Version: 1.0.40_Final_universal_fix1

FontColor_Red="\033[31m"
FontColor_Red_Bold="\033[1;31m"
FontColor_Green="\033[32m"
FontColor_Green_Bold="\033[1;32m"
FontColor_Yellow="\033[33m"
FontColor_Yellow_Bold="\033[1;33m"
FontColor_Purple="\033[35m"
FontColor_Purple_Bold="\033[1;35m"
FontColor_Suffix="\033[0m"

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"

log() {
    local LEVEL="$1"
    local MSG="$2"
    case "${LEVEL}" in
    INFO)
        LEVEL="[${FontColor_Green}${LEVEL}${FontColor_Suffix}]"
        MSG="${LEVEL} ${MSG}"
        ;;
    WARN)
        LEVEL="[${FontColor_Yellow}${LEVEL}${FontColor_Suffix}]"
        MSG="${LEVEL} ${MSG}"
        ;;
    ERROR)
        LEVEL="[${FontColor_Red}${LEVEL}${FontColor_Suffix}]"
        MSG="${LEVEL} ${MSG}"
        ;;
    *) ;;
    esac
    echo -e "${MSG}"
}

if [[ "$(uname -s)" != "Linux" ]]; then
    log ERROR "This operating system is not supported."
    exit 1
fi

if [[ "$(id -u)" != "0" ]]; then
    log ERROR "This script must be run as root."
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    log ERROR "cURL is not installed."
    exit 1
fi

WGCF_Profile='wgcf-profile.conf'
WGCF_ProfileDir="/etc/warp"
WGCF_ProfilePath="${WGCF_ProfileDir}/${WGCF_Profile}"

WireGuard_Interface='wgcf'
WireGuard_ConfPath="/etc/wireguard/${WireGuard_Interface}.conf"

WireGuard_Interface_DNS_IPv4='8.8.8.8,8.8.4.4'
WireGuard_Interface_DNS_IPv6='2001:4860:4860::8888,2001:4860:4860::8844'
WireGuard_Interface_DNS_46="${WireGuard_Interface_DNS_IPv4},${WireGuard_Interface_DNS_IPv6}"
WireGuard_Interface_DNS_64="${WireGuard_Interface_DNS_IPv6},${WireGuard_Interface_DNS_IPv4}"
WireGuard_Interface_Rule_table='51888'
WireGuard_Interface_Rule_fwmark='51888'
WireGuard_Interface_MTU='1280'

WireGuard_Peer_Endpoint_IP4='162.159.192.1'
WireGuard_Peer_Endpoint_IP6='2606:4700:d0::a29f:c001'
WireGuard_Peer_Endpoint_IPv4="${WireGuard_Peer_Endpoint_IP4}:2408"
WireGuard_Peer_Endpoint_IPv6="[${WireGuard_Peer_Endpoint_IP6}]:2408"
WireGuard_Peer_Endpoint_Domain='engage.cloudflareclient.com:2408'
WireGuard_Peer_AllowedIPs_IPv4='0.0.0.0/0'
WireGuard_Peer_AllowedIPs_IPv6='::/0'
WireGuard_Peer_AllowedIPs_DualStack='0.0.0.0/0,::/0'

TestIPv4_1='1.0.0.1'
TestIPv4_2='9.9.9.9'
TestIPv6_1='2606:4700:4700::1001'
TestIPv6_2='2620:fe::fe'
CF_Trace_URL='https://www.cloudflare.com/cdn-cgi/trace'

SysInfo_OS_CodeName=''
SysInfo_OS_Name_lowercase=''
SysInfo_OS_Name_Full=''
SysInfo_RelatedOS=''
SysInfo_Kernel=''
SysInfo_Kernel_Ver_major=''
SysInfo_Kernel_Ver_minor=''
SysInfo_Arch=''
SysInfo_Virt=''
SysInfo_OS_Ver_major=''
SysInfo_Init='none'
WireGuard_ServiceName=''
WARP_Client_ServiceName='warp-svc'
WireGuard_Control_Mode='direct'

Command_Exists() {
    command -v "$1" >/dev/null 2>&1
}

Find_Local_Binary() {
    local NAME="$1"
    local PATTERN="$2"
    local FILE=''

    for FILE in \
        "${SCRIPT_DIR}/${NAME}" \
        "/root/${NAME}" \
        "/usr/local/bin/${NAME}" \
        "/usr/bin/${NAME}"
    do
        if [[ -f "${FILE}" ]]; then
            echo "${FILE}"
            return 0
        fi
    done

    if [[ -n "${PATTERN}" ]]; then
        for FILE in "${SCRIPT_DIR}"/${PATTERN} "/root"/${PATTERN}; do
            if [[ -f "${FILE}" ]]; then
                echo "${FILE}"
                return 0
            fi
        done
    fi

    return 1
}

Detect_Init_System() {
    if Command_Exists systemctl && [[ -d /run/systemd/system ]]; then
        SysInfo_Init='systemd'
    elif Command_Exists rc-service; then
        SysInfo_Init='openrc'
    else
        SysInfo_Init='none'
    fi
}

Detect_Virtualization() {
    if Command_Exists systemd-detect-virt; then
        SysInfo_Virt="$(systemd-detect-virt 2>/dev/null || true)"
    fi

    if [[ -z "${SysInfo_Virt}" || "${SysInfo_Virt}" = "none" ]]; then
        if grep -qa 'lxc' /proc/1/environ 2>/dev/null || grep -qa 'container=lxc' /proc/1/environ 2>/dev/null; then
            SysInfo_Virt='lxc'
        elif [[ -f /proc/user_beancounters ]]; then
            SysInfo_Virt='openvz'
        else
            SysInfo_Virt='none'
        fi
    fi
}

Get_System_Info() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
    else
        log ERROR "/etc/os-release not found."
        exit 1
    fi

    SysInfo_OS_CodeName="${VERSION_CODENAME:-}"
    SysInfo_OS_Name_lowercase="${ID:-linux}"
    SysInfo_OS_Name_Full="${PRETTY_NAME:-${NAME:-Linux}}"
    SysInfo_RelatedOS="${ID_LIKE:-}"
    SysInfo_Kernel="$(uname -r)"
    SysInfo_Kernel_Ver_major="$(uname -r | awk -F . '{print $1}')"
    SysInfo_Kernel_Ver_minor="$(uname -r | awk -F . '{print $2}')"
    SysInfo_Arch="$(uname -m)"
    Detect_Virtualization
    Detect_Init_System

    if Command_Exists rpm && [[ "${SysInfo_RelatedOS}" == *rhel* || "${SysInfo_RelatedOS}" == *fedora* || "${SysInfo_OS_Name_lowercase}" == *rhel* || "${SysInfo_OS_Name_lowercase}" == *centos* || "${SysInfo_OS_Name_lowercase}" == *rocky* || "${SysInfo_OS_Name_lowercase}" == *almalinux* || "${SysInfo_OS_Name_lowercase}" == *ol* || "${SysInfo_OS_Name_lowercase}" == *oracle* ]]; then
        SysInfo_OS_Ver_major="$(rpm -E '%{rhel}' 2>/dev/null)"
        [[ -z "${SysInfo_OS_Ver_major}" || "${SysInfo_OS_Ver_major}" = "%{rhel}" ]] && SysInfo_OS_Ver_major="$(echo "${VERSION_ID:-0}" | cut -d. -f1)"
    else
        SysInfo_OS_Ver_major="$(echo "${VERSION_ID:-0}" | cut -d. -f1)"
    fi

    case "${SysInfo_Init}" in
    systemd)
        WireGuard_ServiceName="wg-quick@${WireGuard_Interface}"
        ;;
    openrc)
        WireGuard_ServiceName="wg-quick.${WireGuard_Interface}"
        ;;
    *)
        WireGuard_ServiceName="wg-quick"
        ;;
    esac
}

Print_System_Info() {
    echo -e "
System Information
---------------------------------------------------
  Operating System: ${SysInfo_OS_Name_Full}
      Linux Kernel: ${SysInfo_Kernel}
      Architecture: ${SysInfo_Arch}
    Virtualization: ${SysInfo_Virt}
       Init System: ${SysInfo_Init}
---------------------------------------------------
"
}

Print_Delimiter() {
    local cols="${COLUMNS:-80}"
    printf '%*s\n' "${cols}" '' | tr ' ' '='
}

Ensure_OpenRC_WG_Service_Instance() {
    if [[ "${SysInfo_Init}" = "openrc" ]]; then
        if [[ -f /etc/init.d/wg-quick && ! -e "/etc/init.d/${WireGuard_ServiceName}" ]]; then
            ln -sf /etc/init.d/wg-quick "/etc/init.d/${WireGuard_ServiceName}" 2>/dev/null || true
        fi
    fi
}

Systemd_WG_Template_Exists() {
    [[ -f /etc/systemd/system/wg-quick@.service || -f /usr/lib/systemd/system/wg-quick@.service || -f /lib/systemd/system/wg-quick@.service ]]
}

Is_WireGuard_Service() {
    [[ "$1" = "${WireGuard_ServiceName}" ]]
}

Resolve_WireGuard_Control_Mode() {
    WireGuard_Control_Mode='direct'

    if ! Command_Exists wg-quick; then
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        if Systemd_WG_Template_Exists; then
            WireGuard_Control_Mode='service'
        else
            WireGuard_Control_Mode='direct'
        fi
        ;;
    openrc)
        Ensure_OpenRC_WG_Service_Instance
        if [[ -x "/etc/init.d/${WireGuard_ServiceName}" ]]; then
            WireGuard_Control_Mode='service'
        else
            WireGuard_Control_Mode='direct'
        fi
        ;;
    *)
        WireGuard_Control_Mode='direct'
        ;;
    esac
}

Service_Is_Active() {
    local SERVICE="$1"

    if Is_WireGuard_Service "${SERVICE}" && [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        if Command_Exists wg && wg show "${WireGuard_Interface}" >/dev/null 2>&1; then
            echo active
        else
            echo inactive
        fi
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        if systemctl is-active --quiet "${SERVICE}" 2>/dev/null; then
            echo active
        else
            echo inactive
        fi
        ;;
    openrc)
        if [[ -x "/etc/init.d/${SERVICE}" ]] && rc-service "${SERVICE}" status >/dev/null 2>&1; then
            echo active
        else
            echo inactive
        fi
        ;;
    *)
        echo inactive
        ;;
    esac
}

Service_Is_Enabled() {
    local SERVICE="$1"

    if Is_WireGuard_Service "${SERVICE}" && [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        echo disabled
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        if systemctl is-enabled --quiet "${SERVICE}" 2>/dev/null; then
            echo enabled
        else
            echo disabled
        fi
        ;;
    openrc)
        if [[ -e "/etc/runlevels/default/${SERVICE}" ]]; then
            echo enabled
        else
            echo disabled
        fi
        ;;
    *)
        echo disabled
        ;;
    esac
}

Service_Enable_Now() {
    local SERVICE="$1"

    if Is_WireGuard_Service "${SERVICE}" && [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        wg-quick up "${WireGuard_Interface}"
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        systemctl enable "${SERVICE}" --now
        ;;
    openrc)
        rc-update add "${SERVICE}" default >/dev/null 2>&1 || true
        rc-service "${SERVICE}" start
        ;;
    *)
        if Is_WireGuard_Service "${SERVICE}"; then
            wg-quick up "${WireGuard_Interface}"
        fi
        ;;
    esac
}

Service_Start() {
    local SERVICE="$1"

    if Is_WireGuard_Service "${SERVICE}" && [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        wg-quick up "${WireGuard_Interface}"
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        systemctl start "${SERVICE}"
        ;;
    openrc)
        rc-service "${SERVICE}" start
        ;;
    *)
        if Is_WireGuard_Service "${SERVICE}"; then
            wg-quick up "${WireGuard_Interface}"
        fi
        ;;
    esac
}

Service_Stop() {
    local SERVICE="$1"

    if Is_WireGuard_Service "${SERVICE}" && [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        wg-quick down "${WireGuard_Interface}" >/dev/null 2>&1 || true
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        systemctl stop "${SERVICE}"
        ;;
    openrc)
        rc-service "${SERVICE}" stop
        ;;
    *)
        if Is_WireGuard_Service "${SERVICE}"; then
            wg-quick down "${WireGuard_Interface}" >/dev/null 2>&1 || true
        fi
        ;;
    esac
}

Service_Restart() {
    local SERVICE="$1"

    if Is_WireGuard_Service "${SERVICE}" && [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        wg-quick down "${WireGuard_Interface}" >/dev/null 2>&1 || true
        wg-quick up "${WireGuard_Interface}"
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        systemctl restart "${SERVICE}"
        ;;
    openrc)
        rc-service "${SERVICE}" restart || rc-service "${SERVICE}" start
        ;;
    *)
        if Is_WireGuard_Service "${SERVICE}"; then
            wg-quick down "${WireGuard_Interface}" >/dev/null 2>&1 || true
            wg-quick up "${WireGuard_Interface}"
        fi
        ;;
    esac
}

Service_Disable_Now() {
    local SERVICE="$1"

    if Is_WireGuard_Service "${SERVICE}" && [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        wg-quick down "${WireGuard_Interface}" >/dev/null 2>&1 || true
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        systemctl disable "${SERVICE}" --now
        ;;
    openrc)
        rc-service "${SERVICE}" stop >/dev/null 2>&1 || true
        rc-update del "${SERVICE}" default >/dev/null 2>&1 || true
        ;;
    *)
        if Is_WireGuard_Service "${SERVICE}"; then
            wg-quick down "${WireGuard_Interface}" >/dev/null 2>&1 || true
        fi
        ;;
    esac
}

Print_WG_Service_Log() {
    if [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        if Command_Exists wg; then
            wg show "${WireGuard_Interface}" || true
        fi
        ip link show "${WireGuard_Interface}" 2>/dev/null || true
        dmesg 2>/dev/null | tail -n 50 || true
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        journalctl -u "${WireGuard_ServiceName}" --no-pager
        ;;
    openrc)
        rc-service "${WireGuard_ServiceName}" status || true
        if Command_Exists wg; then
            wg show "${WireGuard_Interface}" || true
        fi
        dmesg 2>/dev/null | tail -n 50 || true
        ;;
    *)
        if Command_Exists wg; then
            wg show "${WireGuard_Interface}" || true
        fi
        dmesg 2>/dev/null | tail -n 50 || true
        ;;
    esac
}

Install_wgcf() {
    local BIN=''

    if Command_Exists wgcf; then
        log INFO "wgcf is already installed: $(command -v wgcf)"
        return 0
    fi

    BIN="$(Find_Local_Binary 'wgcf' 'wgcf_*_linux_*')"
    if [[ -n "${BIN}" && -f "${BIN}" ]]; then
        install -m 0755 "${BIN}" /usr/local/bin/wgcf
    else
        log ERROR "Local wgcf binary not found. Put wgcf in the same directory as warp.sh or /root."
        exit 1
    fi
}

Uninstall_wgcf() {
    rm -f /usr/local/bin/wgcf
}

Register_WARP_Account() {
    while [[ ! -f wgcf-account.toml ]]; do
        Install_wgcf
        log INFO "Cloudflare WARP Account registration in progress..."
        yes | wgcf register
        sleep 5
    done
}

Generate_WGCF_Profile() {
    while [[ ! -f ${WGCF_Profile} ]]; do
        Register_WARP_Account
        log INFO "WARP WireGuard profile (wgcf-profile.conf) generation in progress..."
        wgcf generate
    done
    Uninstall_wgcf
}

Backup_WGCF_Profile() {
    mkdir -p "${WGCF_ProfileDir}"

    [[ -f wgcf-account.toml ]] && mv -f wgcf-account.toml "${WGCF_ProfileDir}/"
    [[ -f "${WGCF_Profile}" ]] && mv -f "${WGCF_Profile}" "${WGCF_ProfileDir}/"
}

Read_WGCF_Profile() {
    WireGuard_Interface_PrivateKey="$(sed -n 's/^[[:space:]]*PrivateKey[[:space:]]*=[[:space:]]*//p' "${WGCF_ProfilePath}" | head -n1)"
    WireGuard_Interface_Address="$(sed -n 's/^[[:space:]]*Address[[:space:]]*=[[:space:]]*//p' "${WGCF_ProfilePath}" | head -n1)"
    WireGuard_Peer_PublicKey="$(sed -n 's/^[[:space:]]*PublicKey[[:space:]]*=[[:space:]]*//p' "${WGCF_ProfilePath}" | head -n1)"

    WireGuard_Interface_Address_IPv4="$(echo "${WireGuard_Interface_Address}" | cut -d, -f1 | cut -d'/' -f1 | xargs)"
    WireGuard_Interface_Address_IPv6="$(echo "${WireGuard_Interface_Address}" | cut -d, -f2 | cut -d'/' -f1 | xargs)"
}

Load_WGCF_Profile() {
    if [[ -f ${WGCF_Profile} ]]; then
        Backup_WGCF_Profile
        Read_WGCF_Profile
    elif [[ -f ${WGCF_ProfilePath} ]]; then
        Read_WGCF_Profile
    else
        Generate_WGCF_Profile
        Backup_WGCF_Profile
        Read_WGCF_Profile
    fi
}

Install_WireGuardTools_Debian() {
    if [[ "${SysInfo_OS_Ver_major}" = "10" ]]; then
        if ! grep -Rqs "^deb .*buster-backports.* main" /etc/apt/sources.list /etc/apt/sources.list.d 2>/dev/null; then
            echo "deb http://deb.debian.org/debian buster-backports main" >/etc/apt/sources.list.d/backports.list
        fi
    elif [[ "${SysInfo_OS_Ver_major}" -lt 10 ]]; then
        log ERROR "This operating system is not supported."
        exit 1
    fi

    apt update
    apt install -y iproute2 openresolv wireguard-tools --no-install-recommends
}

Install_WireGuardTools_Ubuntu() {
    apt update
    apt install -y iproute2 openresolv wireguard-tools --no-install-recommends
}

Install_WireGuardTools_CentOS() {
    local PM=''
    PM="$(command -v dnf || command -v yum || true)"
    if [[ -z "${PM}" ]]; then
        log ERROR "Neither dnf nor yum found."
        exit 1
    fi

    "${PM}" install -y epel-release >/dev/null 2>&1 || true
    "${PM}" install -y iproute iptables wireguard-tools >/dev/null 2>&1 || \
    "${PM}" install -y iproute iptables kmod-wireguard wireguard-tools >/dev/null 2>&1 || {
        log ERROR "Failed to install wireguard-tools on RHEL/CentOS family."
        exit 1
    }
}

Install_WireGuardTools_Fedora() {
    dnf install -y iproute iptables wireguard-tools
}

Install_WireGuardTools_Arch() {
    pacman -Sy --noconfirm iproute2 openresolv wireguard-tools
}

Install_WireGuardTools_Alpine() {
    apk add --no-cache iproute2 openresolv wireguard-tools iptables nftables >/dev/null 2>&1 || \
    apk add --no-cache iproute2 openresolv wireguard-tools-wg wireguard-tools-wg-quick iptables nftables >/dev/null 2>&1 || {
        log ERROR "Failed to install wireguard tools/firewall backend on Alpine."
        exit 1
    }
}

Install_WireGuardTools() {
    log INFO "Installing wireguard-tools..."

    case "${SysInfo_OS_Name_lowercase}" in
    debian)
        Install_WireGuardTools_Debian
        ;;
    ubuntu)
        Install_WireGuardTools_Ubuntu
        ;;
    centos | rhel | rocky | almalinux | ol | ol8 | ol9 | oracle | oraclelinux)
        Install_WireGuardTools_CentOS
        ;;
    fedora)
        Install_WireGuardTools_Fedora
        ;;
    arch | archlinux)
        Install_WireGuardTools_Arch
        ;;
    alpine)
        Install_WireGuardTools_Alpine
        ;;
    *)
        if [[ "${SysInfo_RelatedOS}" == *rhel* || "${SysInfo_RelatedOS}" == *fedora* ]]; then
            Install_WireGuardTools_CentOS
        elif [[ "${SysInfo_RelatedOS}" == *debian* ]]; then
            Install_WireGuardTools_Debian
        else
            log ERROR "This operating system is not supported."
            exit 1
        fi
        ;;
    esac
}

Ensure_WGQuick_Firewall_Backend() {
    if command -v nft >/dev/null 2>&1 || command -v iptables-restore >/dev/null 2>&1; then
        return 0
    fi

    log INFO "Installing firewall backend required by wg-quick..."

    case "${SysInfo_OS_Name_lowercase}" in
    debian | ubuntu)
        apt update
        apt install -y nftables iptables
        ;;
    alpine)
        apk add --no-cache nftables iptables
        ;;
    centos | rhel | rocky | almalinux | ol | ol8 | ol9 | oracle | oraclelinux)
        local PM=''
        PM="$(command -v dnf || command -v yum || true)"
        if [[ -z "${PM}" ]]; then
            log ERROR "Neither dnf nor yum found."
            exit 1
        fi
        "${PM}" install -y nftables iptables
        ;;
    fedora)
        dnf install -y nftables iptables
        ;;
    arch | archlinux)
        pacman -Sy --noconfirm nftables iptables
        ;;
    *)
        if [[ "${SysInfo_RelatedOS}" == *rhel* || "${SysInfo_RelatedOS}" == *fedora* ]]; then
            local PM=''
            PM="$(command -v dnf || command -v yum || true)"
            if [[ -z "${PM}" ]]; then
                log ERROR "Neither dnf nor yum found."
                exit 1
            fi
            "${PM}" install -y nftables iptables
        elif [[ "${SysInfo_RelatedOS}" == *debian* ]]; then
            apt update
            apt install -y nftables iptables
        else
            log ERROR "No supported method to install firewall backend."
            exit 1
        fi
        ;;
    esac

    if ! command -v nft >/dev/null 2>&1 && ! command -v iptables-restore >/dev/null 2>&1; then
        log ERROR "wg-quick firewall backend still missing: need nft or iptables-restore."
        exit 1
    fi
}

Install_WireGuardGo() {
    local NEED_WIREGUARD_GO='off'
    local BIN=''

    case "${SysInfo_Virt}" in
    openvz | lxc*)
        NEED_WIREGUARD_GO='on'
        ;;
    *)
        if [[ "${SysInfo_Kernel_Ver_major}" -lt 5 ]]; then
            NEED_WIREGUARD_GO='on'
        elif [[ "${SysInfo_Kernel_Ver_major}" -eq 5 && "${SysInfo_Kernel_Ver_minor}" -lt 6 ]]; then
            NEED_WIREGUARD_GO='on'
        fi
        ;;
    esac

    if [[ "${NEED_WIREGUARD_GO}" != 'on' ]]; then
        return 0
    fi

    if Command_Exists wireguard-go; then
        log INFO "wireguard-go is already installed: $(command -v wireguard-go)"
        return 0
    fi

    BIN="$(Find_Local_Binary 'wireguard-go' 'wireguard-go')"
    if [[ -n "${BIN}" && -f "${BIN}" ]]; then
        install -m 0755 "${BIN}" /usr/local/bin/wireguard-go
    else
        log ERROR "Local wireguard-go binary not found. Put wireguard-go in the same directory as warp.sh or /root."
        exit 1
    fi
}

Check_WARP_Client() {
    if [[ "${SysInfo_Init}" = "systemd" ]]; then
        WARP_Client_Status="$(Service_Is_Active "${WARP_Client_ServiceName}")"
        WARP_Client_SelfStart="$(Service_Is_Enabled "${WARP_Client_ServiceName}")"
    else
        WARP_Client_Status='inactive'
        WARP_Client_SelfStart='disabled'
    fi
}

Check_WireGuard() {
    Resolve_WireGuard_Control_Mode
    WireGuard_Status="$(Service_Is_Active "${WireGuard_ServiceName}")"
    WireGuard_SelfStart="$(Service_Is_Enabled "${WireGuard_ServiceName}")"
}

Install_WireGuard() {
    Print_System_Info
    Check_WireGuard
    if [[ "${WireGuard_Status}" = active ]]; then
        log INFO "WireGuard is installed and running."
        return 0
    fi

    Install_WireGuardTools
    Ensure_WGQuick_Firewall_Backend
    Install_WireGuardGo
    Check_WireGuard
}

Start_WireGuard() {
    Check_WARP_Client
    log INFO "Starting WireGuard..."
    if [[ "${WARP_Client_Status}" = active ]]; then
        Service_Stop "${WARP_Client_ServiceName}"
        Service_Enable_Now "${WireGuard_ServiceName}"
        Service_Start "${WARP_Client_ServiceName}"
    else
        Service_Enable_Now "${WireGuard_ServiceName}"
    fi
    Check_WireGuard
    if [[ "${WireGuard_Status}" = active ]]; then
        log INFO "WireGuard is running."
    else
        log ERROR "WireGuard failure to run!"
        Print_WG_Service_Log
        exit 1
    fi
}

Restart_WireGuard() {
    Check_WARP_Client
    log INFO "Restarting WireGuard..."
    if [[ "${WARP_Client_Status}" = active ]]; then
        Service_Stop "${WARP_Client_ServiceName}"
        Service_Restart "${WireGuard_ServiceName}"
        Service_Start "${WARP_Client_ServiceName}"
    else
        Service_Restart "${WireGuard_ServiceName}"
    fi
    Check_WireGuard
    if [[ "${WireGuard_Status}" = active ]]; then
        log INFO "WireGuard has been restarted."
    else
        log ERROR "WireGuard failure to run!"
        Print_WG_Service_Log
        exit 1
    fi
}

Enable_IPv6_Support() {
    local NEED_FIX='off'

    if Command_Exists sysctl; then
        if sysctl -a 2>/dev/null | grep -q 'disable_ipv6.*=.*1'; then
            NEED_FIX='on'
        fi
    fi

    if grep -Rqs 'disable_ipv6.*=.*1' /etc/sysctl.conf /etc/sysctl.d 2>/dev/null; then
        NEED_FIX='on'
    fi

    if [[ "${NEED_FIX}" = 'on' ]]; then
        sed -i '/disable_ipv6/d' /etc/sysctl.conf 2>/dev/null || true
        find /etc/sysctl.d -type f -maxdepth 1 2>/dev/null -exec sed -i '/disable_ipv6/d' {} \; || true
        mkdir -p /etc/sysctl.d
        echo 'net.ipv6.conf.all.disable_ipv6 = 0' >/etc/sysctl.d/ipv6.conf
        sysctl -w net.ipv6.conf.all.disable_ipv6=0 >/dev/null 2>&1 || true
    fi
}

Enable_WireGuard() {
    Enable_IPv6_Support
    Check_WireGuard
    if [[ "${WireGuard_Control_Mode}" = "service" && "${WireGuard_SelfStart}" = enabled ]]; then
        Restart_WireGuard
    else
        Start_WireGuard
    fi
}

Stop_WireGuard() {
    Check_WARP_Client
    Check_WireGuard
    if [[ "${WireGuard_Status}" = active ]]; then
        log INFO "Stoping WireGuard..."
        if [[ "${WARP_Client_Status}" = active ]]; then
            Service_Stop "${WARP_Client_ServiceName}"
            Service_Stop "${WireGuard_ServiceName}"
            Service_Start "${WARP_Client_ServiceName}"
        else
            Service_Stop "${WireGuard_ServiceName}"
        fi
        Check_WireGuard
        if [[ "${WireGuard_Status}" != active ]]; then
            log INFO "WireGuard has been stopped."
        else
            log ERROR "WireGuard stop failure!"
        fi
    else
        log INFO "WireGuard is stopped."
    fi
}

Disable_WireGuard() {
    Check_WARP_Client
    Check_WireGuard
    if [[ "${WireGuard_SelfStart}" = enabled || "${WireGuard_Status}" = active ]]; then
        log INFO "Disabling WireGuard..."
        if [[ "${WARP_Client_Status}" = active ]]; then
            Service_Stop "${WARP_Client_ServiceName}"
            Service_Disable_Now "${WireGuard_ServiceName}"
            Service_Start "${WARP_Client_ServiceName}"
        else
            Service_Disable_Now "${WireGuard_ServiceName}"
        fi
        Check_WireGuard
        if [[ "${WireGuard_SelfStart}" != enabled && "${WireGuard_Status}" != active ]]; then
            log INFO "WireGuard has been disabled."
        else
            log ERROR "WireGuard disable failure!"
        fi
    else
        log INFO "WireGuard is disabled."
    fi
}

Print_WireGuard_Log() {
    Check_WireGuard

    if [[ "${WireGuard_Control_Mode}" = "direct" ]]; then
        if Command_Exists wg; then
            wg show "${WireGuard_Interface}" || true
        fi
        ip link show "${WireGuard_Interface}" 2>/dev/null || true
        return 0
    fi

    case "${SysInfo_Init}" in
    systemd)
        journalctl -u "${WireGuard_ServiceName}" -f
        ;;
    openrc)
        rc-service "${WireGuard_ServiceName}" status
        ;;
    *)
        if Command_Exists wg; then
            wg show "${WireGuard_Interface}"
        fi
        ;;
    esac
}

Ping_IPv4() {
    ping -4 -c1 -W1 "$1" >/dev/null 2>&1 || ping -c1 -W1 "$1" >/dev/null 2>&1
}

Ping_IPv6() {
    if Command_Exists ping6; then
        ping6 -c1 -W1 "$1" >/dev/null 2>&1
    else
        ping -6 -c1 -W1 "$1" >/dev/null 2>&1
    fi
}

Ping_MTU_IPv4() {
    ping -4 -c1 -W1 -s "$1" -M do "$2" >/dev/null 2>&1 || ping -c1 -W1 -s "$1" -M do "$2" >/dev/null 2>&1
}

Ping_MTU_IPv6() {
    if Command_Exists ping6; then
        ping6 -c1 -W1 -s "$1" -M do "$2" >/dev/null 2>&1
    else
        ping -6 -c1 -W1 -s "$1" -M do "$2" >/dev/null 2>&1
    fi
}

Check_Network_Status_IPv4() {
    if Ping_IPv4 "${TestIPv4_1}" || Ping_IPv4 "${TestIPv4_2}"; then
        IPv4Status='on'
    else
        IPv4Status='off'
    fi
}

Check_Network_Status_IPv6() {
    if Ping_IPv6 "${TestIPv6_1}" || Ping_IPv6 "${TestIPv6_2}"; then
        IPv6Status='on'
    else
        IPv6Status='off'
    fi
}

Check_Network_Status() {
    Disable_WireGuard
    Check_Network_Status_IPv4
    Check_Network_Status_IPv6
}

Check_IPv4_addr() {
    IPv4_addr="$(
        ip route get "${TestIPv4_1}" 2>/dev/null | awk '/src/ {for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}' ||
        ip route get "${TestIPv4_2}" 2>/dev/null | awk '/src/ {for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}'
    )"
}

Check_IPv6_addr() {
    IPv6_addr="$(
        ip -6 route get "${TestIPv6_1}" 2>/dev/null | awk '/src/ {for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}' ||
        ip -6 route get "${TestIPv6_2}" 2>/dev/null | awk '/src/ {for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}'
    )"
}

Get_IP_addr() {
    Check_Network_Status
    if [[ "${IPv4Status}" = on ]]; then
        log INFO "Getting the network interface IPv4 address..."
        Check_IPv4_addr
        if [[ -n "${IPv4_addr}" ]]; then
            log INFO "IPv4 Address: ${IPv4_addr}"
        else
            log WARN "Network interface IPv4 address not obtained."
        fi
    fi
    if [[ "${IPv6Status}" = on ]]; then
        log INFO "Getting the network interface IPv6 address..."
        Check_IPv6_addr
        if [[ -n "${IPv6_addr}" ]]; then
            log INFO "IPv6 Address: ${IPv6_addr}"
        else
            log WARN "Network interface IPv6 address not obtained."
        fi
    fi
}

Get_WireGuard_Interface_MTU() {
    log INFO "Getting the best MTU value for WireGuard..."

    local MTU_Preset=1500
    local MTU_Increment=10

    if ! ping -h 2>&1 | grep -q -- '-M'; then
        log WARN "Ping does not support MTU discovery, using default MTU: ${WireGuard_Interface_MTU}"
        return 0
    fi

    if [[ "${IPv4Status}" = off && "${IPv6Status}" = on ]]; then
        while true; do
            if Ping_MTU_IPv6 "$((MTU_Preset - 28))" "${TestIPv6_1}" || Ping_MTU_IPv6 "$((MTU_Preset - 28))" "${TestIPv6_2}"; then
                MTU_Increment=1
                MTU_Preset=$((MTU_Preset + MTU_Increment))
            else
                MTU_Preset=$((MTU_Preset - MTU_Increment))
                if [[ "${MTU_Increment}" = 1 ]]; then
                    break
                fi
            fi
            if [[ "${MTU_Preset}" -le 1360 ]]; then
                log WARN "MTU is set to the lowest value."
                MTU_Preset='1360'
                break
            fi
        done
    else
        while true; do
            if Ping_MTU_IPv4 "$((MTU_Preset - 28))" "${TestIPv4_1}" || Ping_MTU_IPv4 "$((MTU_Preset - 28))" "${TestIPv4_2}"; then
                MTU_Increment=1
                MTU_Preset=$((MTU_Preset + MTU_Increment))
            else
                MTU_Preset=$((MTU_Preset - MTU_Increment))
                if [[ "${MTU_Increment}" = 1 ]]; then
                    break
                fi
            fi
            if [[ "${MTU_Preset}" -le 1360 ]]; then
                log WARN "MTU is set to the lowest value."
                MTU_Preset='1360'
                break
            fi
        done
    fi

    WireGuard_Interface_MTU=$((MTU_Preset - 80))
    log INFO "WireGuard MTU: ${WireGuard_Interface_MTU}"
}

Generate_WireGuardProfile_Interface() {
    Get_WireGuard_Interface_MTU
    log INFO "WireGuard profile (${WireGuard_ConfPath}) generation in progress..."
    mkdir -p /etc/wireguard
    cat <<EOF >"${WireGuard_ConfPath}"

[Interface]
PrivateKey = ${WireGuard_Interface_PrivateKey}
Address = ${WireGuard_Interface_Address}
DNS = ${WireGuard_Interface_DNS}
MTU = ${WireGuard_Interface_MTU}
EOF
}

Generate_WireGuardProfile_Interface_Rule_TableOff() {
    cat <<EOF >>"${WireGuard_ConfPath}"
Table = off
EOF
}

Generate_WireGuardProfile_Interface_Rule_IPv4_nonGlobal() {
    cat <<EOF >>"${WireGuard_ConfPath}"
PostUP = ip -4 route add default dev ${WireGuard_Interface} table ${WireGuard_Interface_Rule_table}
PostUP = ip -4 rule add from ${WireGuard_Interface_Address_IPv4} lookup ${WireGuard_Interface_Rule_table}
PostDown = ip -4 rule delete from ${WireGuard_Interface_Address_IPv4} lookup ${WireGuard_Interface_Rule_table}
PostUP = ip -4 rule add fwmark ${WireGuard_Interface_Rule_fwmark} lookup ${WireGuard_Interface_Rule_table}
PostDown = ip -4 rule delete fwmark ${WireGuard_Interface_Rule_fwmark} lookup ${WireGuard_Interface_Rule_table}
PostUP = ip -4 rule add table main suppress_prefixlength 0
PostDown = ip -4 rule delete table main suppress_prefixlength 0
EOF
}

Generate_WireGuardProfile_Interface_Rule_IPv6_nonGlobal() {
    cat <<EOF >>"${WireGuard_ConfPath}"
PostUP = ip -6 route add default dev ${WireGuard_Interface} table ${WireGuard_Interface_Rule_table}
PostUP = ip -6 rule add from ${WireGuard_Interface_Address_IPv6} lookup ${WireGuard_Interface_Rule_table}
PostDown = ip -6 rule delete from ${WireGuard_Interface_Address_IPv6} lookup ${WireGuard_Interface_Rule_table}
PostUP = ip -6 rule add fwmark ${WireGuard_Interface_Rule_fwmark} lookup ${WireGuard_Interface_Rule_table}
PostDown = ip -6 rule delete fwmark ${WireGuard_Interface_Rule_fwmark} lookup ${WireGuard_Interface_Rule_table}
PostUP = ip -6 rule add table main suppress_prefixlength 0
PostDown = ip -6 rule delete table main suppress_prefixlength 0
EOF
}

Generate_WireGuardProfile_Interface_Rule_DualStack_nonGlobal() {
    Generate_WireGuardProfile_Interface_Rule_TableOff
    Generate_WireGuardProfile_Interface_Rule_IPv4_nonGlobal
    Generate_WireGuardProfile_Interface_Rule_IPv6_nonGlobal
}

Generate_WireGuardProfile_Interface_Rule_nonGlobal_only_IPv4() {
    Generate_WireGuardProfile_Interface_Rule_TableOff
    Generate_WireGuardProfile_Interface_Rule_IPv4_nonGlobal
}

Generate_WireGuardProfile_Interface_Rule_nonGlobal_only_IPv6() {
    Generate_WireGuardProfile_Interface_Rule_TableOff
    Generate_WireGuardProfile_Interface_Rule_IPv6_nonGlobal
}

Generate_WireGuardProfile_Interface_Rule_IPv4_Global_srcIP() {
    cat <<EOF >>"${WireGuard_ConfPath}"
PostUp = ip -4 rule add from ${IPv4_addr} lookup main prio 18
PostDown = ip -4 rule delete from ${IPv4_addr} lookup main prio 18
EOF
}

Generate_WireGuardProfile_Interface_Rule_IPv6_Global_srcIP() {
    cat <<EOF >>"${WireGuard_ConfPath}"
PostUp = ip -6 rule add from ${IPv6_addr} lookup main prio 18
PostDown = ip -6 rule delete from ${IPv6_addr} lookup main prio 18
EOF
}

Generate_WireGuardProfile_Peer() {
    cat <<EOF >>"${WireGuard_ConfPath}"

[Peer]
PublicKey = ${WireGuard_Peer_PublicKey}
AllowedIPs = ${WireGuard_Peer_AllowedIPs}
Endpoint = ${WireGuard_Peer_Endpoint}
EOF
}

Check_WireGuard_Status() {
    Check_WireGuard
    case "${WireGuard_Status}" in
    active)
        WireGuard_Status_en="${FontColor_Green}Running${FontColor_Suffix}"
        WireGuard_Status_zh="${FontColor_Green}运行中${FontColor_Suffix}"
        ;;
    *)
        WireGuard_Status_en="${FontColor_Red}Stopped${FontColor_Suffix}"
        WireGuard_Status_zh="${FontColor_Red}未运行${FontColor_Suffix}"
        ;;
    esac
}

Check_WARP_WireGuard_Status() {
    Check_Network_Status_IPv4
    if [[ "${IPv4Status}" = on ]]; then
        WARP_IPv4_Status="$(curl -s4 "${CF_Trace_URL}" --connect-timeout 2 | awk -F= '/^warp=/{print $2; exit}')"
    else
        unset WARP_IPv4_Status
    fi

    case "${WARP_IPv4_Status}" in
    on)
        WARP_IPv4_Status_en="${FontColor_Green}WARP${FontColor_Suffix}"
        WARP_IPv4_Status_zh="${WARP_IPv4_Status_en}"
        ;;
    plus)
        WARP_IPv4_Status_en="${FontColor_Green}WARP+${FontColor_Suffix}"
        WARP_IPv4_Status_zh="${WARP_IPv4_Status_en}"
        ;;
    off)
        WARP_IPv4_Status_en="Normal"
        WARP_IPv4_Status_zh="正常"
        ;;
    *)
        Check_Network_Status_IPv4
        if [[ "${IPv4Status}" = on ]]; then
            WARP_IPv4_Status_en="Normal"
            WARP_IPv4_Status_zh="正常"
        else
            WARP_IPv4_Status_en="${FontColor_Red}Unconnected${FontColor_Suffix}"
            WARP_IPv4_Status_zh="${FontColor_Red}未连接${FontColor_Suffix}"
        fi
        ;;
    esac

    Check_Network_Status_IPv6
    if [[ "${IPv6Status}" = on ]]; then
        WARP_IPv6_Status="$(curl -s6 "${CF_Trace_URL}" --connect-timeout 2 | awk -F= '/^warp=/{print $2; exit}')"
    else
        unset WARP_IPv6_Status
    fi

    case "${WARP_IPv6_Status}" in
    on)
        WARP_IPv6_Status_en="${FontColor_Green}WARP${FontColor_Suffix}"
        WARP_IPv6_Status_zh="${WARP_IPv6_Status_en}"
        ;;
    plus)
        WARP_IPv6_Status_en="${FontColor_Green}WARP+${FontColor_Suffix}"
        WARP_IPv6_Status_zh="${WARP_IPv6_Status_en}"
        ;;
    off)
        WARP_IPv6_Status_en="Normal"
        WARP_IPv6_Status_zh="正常"
        ;;
    *)
        Check_Network_Status_IPv6
        if [[ "${IPv6Status}" = on ]]; then
            WARP_IPv6_Status_en="Normal"
            WARP_IPv6_Status_zh="正常"
        else
            WARP_IPv6_Status_en="${FontColor_Red}Unconnected${FontColor_Suffix}"
            WARP_IPv6_Status_zh="${FontColor_Red}未连接${FontColor_Suffix}"
        fi
        ;;
    esac

    if [[ "${IPv4Status}" = off && "${IPv6Status}" = off ]]; then
        log ERROR "Cloudflare WARP network anomaly, WireGuard tunnel established failed."
        Disable_WireGuard
        exit 1
    fi
}

Print_WARP_WireGuard_Status() {
    log INFO "Status check in progress..."
    Check_WireGuard_Status
    Check_WARP_WireGuard_Status
    echo -e "
 ----------------------------
 WireGuard\t: ${WireGuard_Status_en}
 IPv4 Network\t: ${WARP_IPv4_Status_en}
 IPv6 Network\t: ${WARP_IPv6_Status_en}
 ----------------------------
"
    log INFO "Done."
}

View_WireGuard_Profile() {
    Print_Delimiter
    cat "${WireGuard_ConfPath}"
    Print_Delimiter
}

Check_WireGuard_Peer_Endpoint() {
    if Ping_IPv4 "${WireGuard_Peer_Endpoint_IP4}"; then
        WireGuard_Peer_Endpoint="${WireGuard_Peer_Endpoint_IPv4}"
    elif Ping_IPv6 "${WireGuard_Peer_Endpoint_IP6}"; then
        WireGuard_Peer_Endpoint="${WireGuard_Peer_Endpoint_IPv6}"
    else
        WireGuard_Peer_Endpoint="${WireGuard_Peer_Endpoint_Domain}"
    fi
}

Set_WARP_IPv4() {
    Install_WireGuard
    Get_IP_addr
    Load_WGCF_Profile
    if [[ "${IPv4Status}" = off && "${IPv6Status}" = on ]]; then
        WireGuard_Interface_DNS="${WireGuard_Interface_DNS_64}"
    else
        WireGuard_Interface_DNS="${WireGuard_Interface_DNS_46}"
    fi
    WireGuard_Peer_AllowedIPs="${WireGuard_Peer_AllowedIPs_IPv4}"
    Check_WireGuard_Peer_Endpoint
    Generate_WireGuardProfile_Interface
    if [[ -n "${IPv4_addr}" ]]; then
        Generate_WireGuardProfile_Interface_Rule_IPv4_Global_srcIP
    fi
    Generate_WireGuardProfile_Peer
    View_WireGuard_Profile
    Enable_WireGuard
    Print_WARP_WireGuard_Status
}

Set_WARP_IPv6() {
    Install_WireGuard
    Get_IP_addr
    Load_WGCF_Profile
    if [[ "${IPv4Status}" = off && "${IPv6Status}" = on ]]; then
        WireGuard_Interface_DNS="${WireGuard_Interface_DNS_64}"
    else
        WireGuard_Interface_DNS="${WireGuard_Interface_DNS_46}"
    fi
    WireGuard_Peer_AllowedIPs="${WireGuard_Peer_AllowedIPs_IPv6}"
    Check_WireGuard_Peer_Endpoint
    Generate_WireGuardProfile_Interface
    if [[ -n "${IPv6_addr}" ]]; then
        Generate_WireGuardProfile_Interface_Rule_IPv6_Global_srcIP
    fi
    Generate_WireGuardProfile_Peer
    View_WireGuard_Profile
    Enable_WireGuard
    Print_WARP_WireGuard_Status
}

Set_WARP_DualStack() {
    Install_WireGuard
    Get_IP_addr
    Load_WGCF_Profile
    WireGuard_Interface_DNS="${WireGuard_Interface_DNS_46}"
    WireGuard_Peer_AllowedIPs="${WireGuard_Peer_AllowedIPs_DualStack}"
    Check_WireGuard_Peer_Endpoint
    Generate_WireGuardProfile_Interface
    if [[ -n "${IPv4_addr}" ]]; then
        Generate_WireGuardProfile_Interface_Rule_IPv4_Global_srcIP
    fi
    if [[ -n "${IPv6_addr}" ]]; then
        Generate_WireGuardProfile_Interface_Rule_IPv6_Global_srcIP
    fi
    Generate_WireGuardProfile_Peer
    View_WireGuard_Profile
    Enable_WireGuard
    Print_WARP_WireGuard_Status
}

Set_WARP_DualStack_nonGlobal() {
    Install_WireGuard
    Get_IP_addr
    Load_WGCF_Profile
    WireGuard_Interface_DNS="${WireGuard_Interface_DNS_46}"
    WireGuard_Peer_AllowedIPs="${WireGuard_Peer_AllowedIPs_DualStack}"
    Check_WireGuard_Peer_Endpoint
    Generate_WireGuardProfile_Interface
    Generate_WireGuardProfile_Interface_Rule_DualStack_nonGlobal
    Generate_WireGuardProfile_Peer
    View_WireGuard_Profile
    Enable_WireGuard
    Print_WARP_WireGuard_Status
}

Set_WARP_DualStack_nonGlobal_IPv4() {
    Install_WireGuard
    Get_IP_addr
    Load_WGCF_Profile
    WireGuard_Interface_DNS="${WireGuard_Interface_DNS_46}"
    WireGuard_Peer_AllowedIPs="${WireGuard_Peer_AllowedIPs_DualStack}"
    Check_WireGuard_Peer_Endpoint
    Generate_WireGuardProfile_Interface
    Generate_WireGuardProfile_Interface_Rule_nonGlobal_only_IPv4
    Generate_WireGuardProfile_Peer
    View_WireGuard_Profile
    Enable_WireGuard
    Print_WARP_WireGuard_Status
}

Set_WARP_DualStack_nonGlobal_IPv6() {
    Install_WireGuard
    Get_IP_addr
    Load_WGCF_Profile
    WireGuard_Interface_DNS="${WireGuard_Interface_DNS_46}"
    WireGuard_Peer_AllowedIPs="${WireGuard_Peer_AllowedIPs_DualStack}"
    Check_WireGuard_Peer_Endpoint
    Generate_WireGuardProfile_Interface
    Generate_WireGuardProfile_Interface_Rule_nonGlobal_only_IPv6
    Generate_WireGuardProfile_Peer
    View_WireGuard_Profile
    Enable_WireGuard
    Print_WARP_WireGuard_Status
}

Print_Usage() {
    echo -e "

USAGE:
    bash ./warp.sh [SUBCOMMAND]

PREREQUISITES:
    Put local binaries 'wgcf' and 'wireguard-go' in the same directory as warp.sh
    or in /root, unless they are already installed in /usr/local/bin.

SUBCOMMANDS:
    wg4             Configuration WARP IPv4 Global Network (with WireGuard), all IPv4 outbound data over the WARP network
    wg6             Configuration WARP IPv6 Global Network (with WireGuard), all IPv6 outbound data over the WARP network
    wgd             Configuration WARP Dual Stack Global Network (with WireGuard), all outbound data over the WARP network
    wgx             Configuration WARP Non-Global Network (with WireGuard), set fwmark or interface IP Address to use the WARP network
    wgy             Configuration WARP IPv4 Non-Global Network (with WireGuard), set fwmark or interface IP Address to use the WARP network
    wgz             Configuration WARP IPv6 Non-Global Network (with WireGuard), set fwmark or interface IP Address to use the WARP network
    rwg             Restart WARP WireGuard service
    dwg             Disable WARP WireGuard service
    status          Prints status information
    help            Prints this message or the help of the given subcommand(s)
"
}

if [[ $# -ge 1 ]]; then
    Get_System_Info
    case "${1}" in
    wg4 | 4)
        Set_WARP_IPv4
        ;;
    wg6 | 6)
        Set_WARP_IPv6
        ;;
    wgd | d)
        Set_WARP_DualStack
        ;;
    wgx | x)
        Set_WARP_DualStack_nonGlobal
        ;;
    wgy | y)
        Set_WARP_DualStack_nonGlobal_IPv4
        ;;
    wgz | z)
        Set_WARP_DualStack_nonGlobal_IPv6
        ;;
    rwg)
        Restart_WireGuard
        ;;
    dwg)
        Disable_WireGuard
        ;;
    status)
        Print_WARP_WireGuard_Status
        ;;
    help)
        Print_Usage
        ;;
    *)
        log ERROR "Invalid Parameters: $*"
        Print_Usage
        exit 1
        ;;
    esac
else
    Print_Usage
fi
