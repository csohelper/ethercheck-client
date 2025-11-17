import asyncio
import datetime
import platform
import re
import subprocess


async def async_ping(host, count=4):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, ping, host, count)


async def async_trace(host):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, trace, host)


def ping(host, count=4):
    """
    Универсальный ping для любой локализации Windows и Linux/macOS.
    """
    system = platform.system().lower()
    param = "-n" if system == "windows" else "-c"
    cmd = ["ping", param, str(count), host]

    # Кодировка для Windows — cp866 (даже если система русская)
    encoding = "cp866" if system == "windows" else "utf-8"

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace"
    )
    output = proc.stdout

    times = []

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

    return {
        "stamp": datetime.datetime.now().isoformat(),
        "raw": output,
        "times_ms": times,
        "avg_ms": round(avg_ms, 2) if avg_ms is not None else None
    }


def trace(host):
    """
    Выполняет traceroute/tracert до хоста.
    Возвращает dict:
    {
        "raw": "<текст консоли>",
        "hops": [{"hop": int, "ip": str|None, "host": str|None}, ...]
    }
    """
    system = platform.system().lower()
    if system == "windows":
        cmd = ["tracert", host]
        encoding = "cp866"
    else:
        cmd = ["traceroute", host]
        encoding = "utf-8"

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding=encoding, errors="replace")
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
            m = re.search(pattern, line)
            if not m:
                continue
            hop_num = int(m.group(1))
            tail = m.group(2)
            ip_match = re.search(r"(\d+\.\d+\.\d+\.\d+)", tail)
            ip = ip_match.group(1) if ip_match else None
            host_match = re.search(r"([a-zA-Z0-9\.-]+)\s*\[", tail)
            hostname = host_match.group(1) if host_match else None
            hops.append({"hop": hop_num, "ip": ip, "host": hostname})

    else:
        # Linux / Mac
        pattern = r"^\s*(\d+)\s+([^\s]+)(?:\s+\(([\d\.]+)\))?"
        for line in output.splitlines():
            m = re.search(pattern, line)
            if not m:
                continue
            hop_num = int(m.group(1))
            host_or_ip = m.group(2)
            ip_brackets = m.group(3)
            if ip_brackets:
                ip = ip_brackets
                hostname = host_or_ip
            else:
                if re.match(r"\d+\.\d+\.\d+\.\d+", host_or_ip):
                    ip = host_or_ip
                    hostname = None
                else:
                    ip = None
                    hostname = host_or_ip
            hops.append({"hop": hop_num, "ip": ip, "host": hostname})

    return {
        "stamp": datetime.datetime.now().isoformat(),
        "raw": output, "hops": hops
    }
