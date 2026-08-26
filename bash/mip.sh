private_ip() {
    local copy_flag=false
    local extended_flag=false
    local ip=""
    local interface=""

    # ANSI color codes
    local cyan="" green="" yellow="" red="" reset=""
    
    # Only apply colors if output is a terminal
    if [ -t 1 ]; then
        cyan="\033[1;36m"
        green="\033[1;32m"
        yellow="\033[1;33m"
        red="\033[1;31m"
        reset="\033[0m"
    fi

    # 1. Process parameters
    while [ "$#" -gt 0 ]; do
        case "$1" in
            -c) copy_flag=true ;;
            -a) extended_flag=true ;;
            *) echo -e "${red}Unknown parameter: $1${reset}" >&2; return 1 ;;
        esac
        shift
    done

    # 2. Get local IP and active interface
    # Filters for the first non-loopback IPv4 address
    interface=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $5; exit}')
    ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')

    if [ -z "$ip" ]; then
        echo -e "${red}Error: Could not retrieve local IP. Are you connected?${reset}" >&2
        return 1
    fi

    # 3. Print the IP
    echo -e "${cyan}${ip}${reset}"

    # 4. Copy to clipboard
    if [ "$copy_flag" = true ]; then
        if command -v copy_to_clipboard &> /dev/null; then
            printf "%s" "$ip" | copy_to_clipboard
            echo -e "${green}📋 Local IP copied to clipboard.${reset}"
        fi
    fi

    # 5. Show extra information
    if [ "$extended_flag" = true ]; then
        echo -e "${yellow}--- Extra Information ---${reset}"
        
        local gateway=$(ip route | grep default | awk '{print $3}' | head -n 1)
        
        # DNS retrieval (consistent with your public_ip logic)
        local dns_servers=""
        if [ -f /etc/resolv.conf ]; then
            dns_servers=$(grep '^nameserver' /etc/resolv.conf | grep -v '127.0.0.1' | awk '{print $2}' | xargs | sed 's/ /, /g')
        fi
        if [ -z "$dns_servers" ] && command -v nmcli &> /dev/null; then
            dns_servers=$(nmcgli dev show "$interface" | grep 'IP4.DNS' | awk '{print $2}' | xargs | sed 's/ /, /g')
        fi

        echo -e "${cyan}Interface:${reset} ${interface:-Unknown}"
        echo -e "${cyan}Gateway:${reset}   ${gateway:-Unknown}"
        echo -e "${cyan}DNS Servers:${reset} ${dns_servers:-Unknown}"
    fi
}


public_ip() {
    local copy_flag=false
    local extended_flag=false
    local ip=""
    local json_data=""

    # ANSI color codes
    local cyan="" green="" yellow="" red="" reset=""
    
    # Only apply colors if output is a terminal (prevents color codes in pipes/clipboard)
    if [ -t 1 ]; then
        cyan="\033[1;36m"
        green="\033[1;32m"
        yellow="\033[1;33m"
        red="\033[1;31m"
        reset="\033[0m"
    fi

    # 1. Process parameters
    while [ "$#" -gt 0 ]; do
        case "$1" in
            -c) copy_flag=true ;;
            -a) extended_flag=true ;;
            *) echo -e "${red}Unknown parameter: $1${reset}" >&2; return 1 ;;
        esac
        shift
    done

    # 2. Get data (Optimized with jq for -a flag)
    if [ "$extended_flag" = true ]; then
        if ! command -v jq &> /dev/null; then
            echo -e "${red}Error: 'jq' is not installed.${reset}" >&2
            return 1
        fi
        json_data=$(curl -s https://ipinfo.io)
        ip=$(echo "$json_data" | jq -r '.ip // empty')
    else
        ip=$(curl -s ifconfig.me || curl -s ipinfo.io/ip)
    fi

    # Validate IP retrieval
    if [ -z "$ip" ] || [ "$ip" = "null" ]; then
        echo -e "${red}Error: Could not retrieve public IP.${reset}" >&2
        return 1
    fi

    # 3. Print the IP
    echo -e "${cyan}${ip}${reset}"

    # 4. Copy to clipboard (Uses the raw $ip string, no colors)
    if [ "$copy_flag" = true ]; then
        if command -v copy_to_clipboard &> /dev/null; then
            printf "%s" "$ip" | copy_to_clipboard
            echo -e "${green}📋 IP copied to clipboard.${reset}"
        else
            echo -e "${yellow}⚠️ Warning: copy_to_clipboard function not found.${reset}" >&2
        fi
    fi

    # 5. Show extra information
    if [ "$extended_flag" = true ]; then
        echo -e "${yellow}--- Extra Information ---${reset}"
        
        local country=$(echo "$json_data" | jq -r '.country // "Unknown"')
        local isp=$(echo "$json_data" | jq -r '.org // "Unknown"')
        local city=$(echo "$json_data" | jq -r '.city // "Unknown"')
        
        # Robust DNS retrieval
        local dns_servers=""
        if [ -f /etc/resolv.conf ]; then
            # Filter out comments and loopback addresses, grab nameservers
            dns_servers=$(grep '^nameserver' /etc/resolv.conf | grep -v '127.0.0.1' | awk '{print $2}' | xargs | sed 's/ /, /g')
        fi

        # Fallback to NetworkManager if resolv.conf was empty or only had local loopback
        if [ -z "$dns_servers" ] && command -v nmcli &> /dev/null; then
            dns_servers=$(nmcli dev show | grep 'IP4.DNS' | awk '{print $2}' | xargs | sed 's/ /, /g')
        fi

        echo -e "${cyan}City:${reset} ${city}"
        echo -e "${cyan}Country:${reset} ${country}"
        echo -e "${cyan}Provider:${reset} ${isp}"
        echo -e "${cyan}DNS Servers:${reset} ${dns_servers:-Unknown}"
    fi

}

public_ip_display() {
    local ip=""
    
    # 1. Intentar obtener la IP con un timeout de 3 segundos para que no se quede colgado
#    ip=$(curl -s --connect-timeout 3 ifconfig.me) # now returns the IPv6...strange
    
    # Fallback si el primer servicio falla
    if [ -z "$ip" ]; then
        ip=$(curl -s --connect-timeout 3 ipinfo.io/ip)
    fi

    # 2. Manejo de la ausencia de internet
    if [ -z "$ip" ] || [ "$ip" = "null" ]; then
        # Devolvemos un mensaje de error o un icono y forzamos salida exitosa (0)
        echo "Disconnected ❌"
        return 0
    fi

    # 3. Si todo va bien, imprime la IP
    echo "$ip"
    return 0
}


# TODO: extraer funciones color-print, get-dns, private_ip, public_ip,..
# a un archivo sh que se carga aqui. Me permite editar el basrc facilmente sin estar tocando el archivo de configuracion, solo importo mi archivo, es mas limpio

# source utils.sh

# Returns 0 and prints SSID if WiFi has an IP assigned, 1 otherwise
is_wifi_connected() {
    local wifi_interfaces=""
    local ssid=""
    
    # 1. Find all wireless interfaces
    wifi_interfaces=$(iw dev 2>/dev/null | awk '$1=="Interface" {print $2}')
    
    # Fallback to scanning /sys/class/net if igw is not installed
    if [ -z "$wifi_interfaces" ]; then
        wifi_interfaces=$(grep -l "DEVTYPE=wlan" /sys/class/net/*/uevent 2>/dev/null | cut -d/ -f5)
    fi

    # 2. Check if any of them has an IPv4 address
    for iface in $wifi_interfaces; do
        if ip -4 addr show "$iface" 2>/dev/null | grep -q "inet "; then
            # 3. Get the SSID using universal nmcli fields
            if command -v iwgetid &> /dev/null; then
                ssid=$(iwgetid -r "$iface")
            elif command -v nmcli &> /dev/null; then
                # Look for the entry marked as 'yes' in the IN-USE field
                ssid=$(nmcli -t -f IN-USE,SSID device wifi list | grep "^\*:" | cut -d: -f2)
            fi

            # Print SSID and return 0
            echo "${ssid:-Connected}"
            return 0
        fi
    done
    
    return 1
}

# Returns 0 if Ethernet has an IP assigned, 1 otherwise
is_ethernet_connected() {
    # 1. Find all ethernet interfaces
    local eth_interfaces
    # Usually starting with 'e' (eth0, enp3s0, etc.)
    eth_interfaces=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(eth|en|em|p[0-9])')

    # 2. Check if any of them has an IPv4 address
    for iface in $eth_interfaces; do
        if ip -4 addr show "$iface" 2>/dev/null | grep -q "inet "; then
            return 0
        fi
    done
    return 1
}
