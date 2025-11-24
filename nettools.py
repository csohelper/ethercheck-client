import asyncio
from datetime import datetime
import platform
import re
import subprocess

# Для Windows: импортируем CREATE_NO_WINDOW только если на Windows
if platform.system().lower() == "windows":
    from subprocess import CREATE_NO_WINDOW


async def async_ping(host, count=4):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, ping, host, count)


async def async_trace(host):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, trace, host)


def parse_windows_ipconfig(output):
    """
    Парсит вывод ipconfig в список интерфейсов.
    """
    interfaces = []
    current_interface = None
    lines = output.splitlines()

    for line in lines:
        line = line.strip()

        # Начало нового адаптера
        if line.endswith(':') and not line.startswith(('IPv4', 'Subnet', 'Default')):
            if current_interface:
                interfaces.append(current_interface)
            current_interface = {
                "name": line[:-1].strip(),  # Убираем ':'
                "description": None,
                "mac": None,
                "ipv4": None,
                "netmask": None,
                "gateway": None,
                "dhcp_server": None,
                "status": None,  # ipconfig не показывает up/down явно, но если есть IP — считаем up
                "inferred_type": "unknown"
            }

            # Определяем тип по имени
            lower_name = current_interface["name"].lower()
            if "wi-fi" in lower_name or "wireless" in lower_name:
                current_interface["inferred_type"] = "wifi"
            elif "ethernet" in lower_name:
                current_interface["inferred_type"] = "ethernet"
            elif "vpn" in lower_name or "virtual" in lower_name:
                current_interface["inferred_type"] = "vpn"
            elif "loopback" in lower_name:
                current_interface["inferred_type"] = "loopback"

            continue

        if not current_interface:
            continue

        # Парсим ключ-значение
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()

            if "description" in key or "описание" in key:
                current_interface["description"] = value
            elif "physical address" in key or "физический адрес" in key:
                current_interface["mac"] = value.replace('-', ':')  # Нормализуем MAC
            elif "ipv4" in key:
                current_interface["ipv4"] = value
            elif "subnet mask" in key or "маска подсети" in key:
                current_interface["netmask"] = value
            elif "default gateway" in key or "основной шлюз" in key:
                current_interface["gateway"] = value
            elif "dhcp server" in key or "сервер dhcp" in key:
                current_interface["dhcp_server"] = value

    if current_interface:
        interfaces.append(current_interface)

    # Фильтруем "рабочие" — с IPv4 или MAC
    working_interfaces = [
        iface for iface in interfaces
        if iface["ipv4"] or iface["mac"]
    ]

    return working_interfaces


def parse_linux_ip_addr(output):
    """
    Парсит вывод ip addr show в список интерфейсов.
    """
    interfaces = []
    current_interface = None
    lines = output.splitlines()

    for line in lines:
        line = line.strip()

        # Начало нового интерфейса: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ..."
        if re.match(r'^\d+:\s', line):
            if current_interface:
                interfaces.append(current_interface)
            name = line.split(':', 1)[1].split()[0].strip()
            status_match = re.search(r'<(.*?)>', line)
            status = "up" if status_match and "UP" in status_match.group(1) else "down"
            current_interface = {
                "name": name,
                "description": None,
                "mac": None,
                "ipv4": None,
                "netmask": None,
                "gateway": None,  # ip addr не показывает gateway, для этого route
                "dhcp_server": None,  # Не в ip addr
                "status": status,
                "inferred_type": "unknown"
            }

            # Определяем тип по имени
            lower_name = name.lower()
            if lower_name.startswith("wlan") or lower_name.startswith("wifi"):
                current_interface["inferred_type"] = "wifi"
            elif lower_name.startswith("eth") or lower_name.startswith("en"):
                current_interface["inferred_type"] = "ethernet"
            elif lower_name.startswith("tun") or lower_name.startswith("tap") or "vpn" in lower_name:
                current_interface["inferred_type"] = "vpn"
            elif lower_name == "lo":
                current_interface["inferred_type"] = "loopback"

            continue

        if not current_interface:
            continue

        # link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff
        if line.startswith("link/ether"):
            current_interface["mac"] = line.split()[1]

        # inet 192.168.1.100/24 brd 192.168.1.255 scope global eth0
        elif line.startswith("inet "):
            ip_cidr = line.split()[1]
            ipv4, netmask_bits = ip_cidr.split('/')
            current_interface["ipv4"] = ipv4
            # Преобразуем /24 в 255.255.255.0
            netmask = '.'.join(
                [str((0xffffffff << (32 - int(netmask_bits) - i * 8) & 0xffffffff) >> 24) for i in range(4)][::-1])
            current_interface["netmask"] = netmask

    if current_interface:
        interfaces.append(current_interface)

    # Для gateway — отдельно вызовем ip route
    # Поскольку это Linux, нет нужды в creationflags
    route_proc = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
    route_output = route_proc.stdout
    for line in route_output.splitlines():
        if line.startswith("default via"):
            gateway = line.split()[2]
            dev = line.split("dev ")[1].split()[0]
            for iface in interfaces:
                if iface["name"] == dev:
                    iface["gateway"] = gateway

    # Фильтруем "рабочие" — up и с IPv4 или MAC
    working_interfaces = [
        iface for iface in interfaces
        if iface["status"] == "up" and (iface["ipv4"] or iface["mac"])
    ]

    return working_interfaces


def parse_macos_ifconfig(output):
    """
    Парсит вывод ifconfig в список интерфейсов (похоже на Linux).
    """
    interfaces = []
    current_interface = None
    lines = output.splitlines()

    for line in lines:
        line = line.strip()

        # Начало нового интерфейса: "en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500"
        if ':' in line and not line.startswith("\t") and not line.startswith("inet"):
            if current_interface:
                interfaces.append(current_interface)
            name = line.split(':')[0].strip()
            status = "up" if "UP" in line else "down"
            current_interface = {
                "name": name,
                "description": None,
                "mac": None,
                "ipv4": None,
                "netmask": None,
                "gateway": None,
                "dhcp_server": None,
                "status": status,
                "inferred_type": "unknown"
            }

            # Определяем тип
            lower_name = name.lower()
            if "wi-fi" in lower_name or "airport" in lower_name or lower_name.startswith("awdl"):
                current_interface["inferred_type"] = "wifi"
            elif lower_name.startswith("en") or lower_name.startswith("eth"):
                current_interface["inferred_type"] = "ethernet"
            elif lower_name.startswith("utun") or "vpn" in lower_name:
                current_interface["inferred_type"] = "vpn"
            elif lower_name == "lo0":
                current_interface["inferred_type"] = "loopback"

            continue

        if not current_interface:
            continue

        # ether aa:bb:cc:dd:ee:ff
        if line.startswith("ether"):
            current_interface["mac"] = line.split()[1]

        # inet 192.168.1.100 netmask 0xffffff00 broadcast 192.168.1.255
        elif line.startswith("inet "):
            parts = line.split()
            current_interface["ipv4"] = parts[1]
            netmask_hex = parts[3]
            netmask = '.'.join([str(int(netmask_hex[i:i + 2], 16)) for i in range(2, 10, 2)])
            current_interface["netmask"] = netmask

    if current_interface:
        interfaces.append(current_interface)

    # Для gateway — используем netstat -rn
    # Поскольку это macOS, нет нужды в creationflags
    route_proc = subprocess.run(["netstat", "-rn"], capture_output=True, text=True)
    route_output = route_proc.stdout
    for line in route_output.splitlines():
        if line.startswith("default"):
            parts = line.split()
            gateway = parts[1]
            iface_name = parts[-1]
            for iface in interfaces:
                if iface["name"] == iface_name:
                    iface["gateway"] = gateway

    # Фильтруем "рабочие"
    working_interfaces = [
        iface for iface in interfaces
        if iface["status"] == "up" and (iface["ipv4"] or iface["mac"])
    ]

    return working_interfaces


def ping(host, count=4):
    """
    Универсальный ping для любой локализации Windows и Linux/macOS.
    """
    system = platform.system().lower()
    param = "-n" if system == "windows" else "-c"
    cmd = ["ping", param, str(count), host]

    # Кодировка для Windows — cp866 (даже если система русская)
    encoding = "cp866" if system == "windows" else "utf-8"

    # Добавляем флаг для скрытия окна на Windows
    kwargs = {}
    if system == "windows":
        kwargs['creationflags'] = CREATE_NO_WINDOW

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace",
        **kwargs
    )
    output = proc.stdout

    if system == "windows":
        # Универсальный паттерн: ловим "время=40мс", "время<1мс", "time=40ms", "time<1ms"
        pattern = r'время[=<]?\s*(\d+(?:\.\d+)?)\s*м[сc]'  # "время=40мс", "время<1мс"
        pattern_en = r'time[=<]?\s*(\d+(?:\.\d+)?)\s*ms'  # английская локаль

        matches = re.findall(pattern, output, re.IGNORECASE)
        if not matches:
            matches = re.findall(pattern_en, output, re.IGNORECASE)

        times = [float(t) for t in matches]
    else:
        # Linux/macOS — стандартный вывод
        matches = re.findall(r'time[=<]?\s*([\d.]+)\s*ms', output)
        times = [float(t) for t in matches]

    avg_ms = sum(times) / len(times) if times else None

    # Получаем информацию о сети
    if system == "windows":
        network_cmd = ["ipconfig"]
    elif system == "darwin":
        network_cmd = ["ifconfig"]
    else:  # linux
        network_cmd = ["ip", "addr", "show"]

    network_proc = subprocess.run(
        network_cmd,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace",
        **kwargs
    )
    network_output = network_proc.stdout

    # Парсим в структурированные интерфейсы
    if system == "windows":
        interfaces = parse_windows_ipconfig(network_output)
    elif system == "darwin":
        interfaces = parse_macos_ifconfig(network_output)
    else:
        interfaces = parse_linux_ip_addr(network_output)

    return {
        "stamp": datetime.now().isoformat(),
        "raw": output,
        "times_ms": times,
        "avg_ms": round(avg_ms, 2) if avg_ms is not None else None,
        "network_info": {
            "raw": network_output,
            "interfaces": interfaces
        }
    }


def trace(host):
    """
    Выполняет traceroute/tracert до хоста.
    Возвращает dict:
    {
        "stamp": "...",
        "raw": "<текст консоли traceroute>",
        "hops": [{"hop": int, "ip": str|None, "host": str|None}, ...],
        "network_info": {
            "raw": "<вывод ipconfig/ifconfig/ip addr>",
            "interfaces": [структурированные интерфейсы]
        }
    }
    """
    system = platform.system().lower()
    if system == "windows":
        cmd = ["tracert", host]
        encoding = "cp866"
    else:
        cmd = ["traceroute", host]
        encoding = "utf-8"

    # Добавляем флаг для скрытия окна на Windows
    kwargs = {}
    if system == "windows":
        kwargs['creationflags'] = CREATE_NO_WINDOW

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace",
        **kwargs
    )
    output = proc.stdout
    hops = []

    if system == "windows":
        # Windows (RU/EN)
        pattern = (
            r"^\s*(\d+)\s+"
            r"(?:<\d+\s*(?:мс|ms)|\d+\s*(?:мс|ms)|\*)\s+"
            r"(?:<\d+\s*(?:мс|ms)|\d+\s*(?:мс|ms)|\*)\s+"
            r"(?:<\d+\s*(?:мс|ms)|\d+\s*(?:мс|ms)|\*)\s+"
            r"(.+?)$"
        )
        for line in output.splitlines():
            m = re.search(pattern, line, re.IGNORECASE)
            if not m:
                continue
            hop_num = int(m.group(1))
            tail = m.group(2).strip()

            ip_match = re.search(r"\[?(\d+\.\d+\.\d+\.\d+)\]?", tail)
            ip = ip_match.group(1) if ip_match else None

            host_match = re.search(r"([a-zA-Z0-9\.-]+?)(?:\s+\[|$)", tail)
            hostname = host_match.group(1) if host_match else None

            hops.append({"hop": hop_num, "ip": ip, "host": hostname})

    else:
        # Linux / macOS
        pattern = r"^\s*(\d+)\s+([^\s(]+)(?:\s+\(([\d\.]+)\))?"
        for line in output.splitlines():
            m = re.search(pattern, line)
            if not m:
                continue
            hop_num = int(m.group(1))
            host_or_ip = m.group(2)
            ip_brackets = m.group(3)

            if ip_brackets:
                ip = ip_brackets
                hostname = host_or_ip if not re.match(r"\d+\.\d+\.\d+\.\d+", host_or_ip) else None
            else:
                if re.match(r"\d+\.\d+\.\d+\.\d+", host_or_ip):
                    ip = host_or_ip
                    hostname = None
                else:
                    ip = None
                    hostname = host_or_ip
            hops.append({"hop": hop_num, "ip": ip, "host": hostname})

    # ==================== СЕТЕВАЯ ИНФОРМАЦИЯ ====================
    if system == "windows":
        network_cmd = ["ipconfig"]
    elif system == "darwin":
        network_cmd = ["ifconfig"]
    else:  # linux
        network_cmd = ["ip", "addr", "show"]

    network_proc = subprocess.run(
        network_cmd,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace",
        **kwargs
    )
    network_output = network_proc.stdout

    # Парсим в структурированные интерфейсы
    if system == "windows":
        interfaces = parse_windows_ipconfig(network_output)
    elif system == "darwin":
        interfaces = parse_macos_ifconfig(network_output)
    else:
        interfaces = parse_linux_ip_addr(network_output)

    # ============================================================

    return {
        "stamp": datetime.now().isoformat(),
        "raw": output,
        "hops": hops,
        "network_info": {
            "raw": network_output,
            "interfaces": interfaces
        }
    }
