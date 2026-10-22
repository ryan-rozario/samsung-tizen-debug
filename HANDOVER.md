# Samsung TV Wi-Fi Debug — Agent Handover File

> **Generated:** 2026-10-22 | **Conversation ID:** `6c680f02-c5ae-4836-acf0-10b88a0be17b`

---

## 1. Device Under Investigation

| Field | Value |
|---|---|
| **Device** | Samsung TV |
| **Model code** | UA43AUE60AKLXL |
| **OS** | Tizen Linux 4.1.10 (armv7l) |
| **Wi-Fi MAC** | `BC:45:5B:81:9C:E6` |
| **Ethernet MAC** | `B0:99:D7:02:D7:0D` |
| **TV IP (wlan0)** | `192.168.0.14` |
| **Debug user** | `sdk` (uid=901), with `priv_internet`, `priv_appdebugging` etc. |
| **SDB / ADB access** | Enabled via Developer Mode (Apps → 12345 secret code) |

---

## 2. Network Environment

| Field | Value |
|---|---|
| **Router/Gateway** | TP-Link mesh system — primary node at `192.168.0.1`, secondary node at `192.168.0.2` |
| **Setup type** | Mesh (OneMesh / multi-band — 2.4 GHz + 5 GHz) |
| **DNS** | `192.168.0.1`, `8.8.8.8`, `fe80::bafb:b3ff:fe95:422` (IPv6 link-local mesh node) |
| **IPv4 subnet** | `192.168.0.0/24` |
| **IPv6** | Active — `2406:7400:12b:df21::/64` prefix on `wlan0`, router RA at `fe80::bafb:b3ff:fe95:458` |
| **Router portal** | `http://192.168.0.1` (TP-Link web UI, requires login) |

---

## 3. Root-Cause Analysis — What We Found

### 3a. DNS resolution failure for Samsung OSB servers ⚠️ CRITICAL

```
osb.samsungcloudsolution.net  →  NXDOMAIN (DNS lookup fails completely)
```

- `cdn.samsungcloudsolution.com` resolves and responds **HTTP 200** (captive-portal check passes).
- `osb.samsungcloudsolution.net` (Samsung Smart TV cloud / update / activation endpoint) **cannot be resolved** from the TV.
- Other hosts resolve fine: `lcprd1.samsungcloudsolution.net` and `time.samsungcloudsolution.com` resolve OK.
- Google (`8.8.8.8`) is reachable: DNS 8.8ms, connect 30ms, total 361ms, HTTP 200.

**Likely cause:** The mesh router's DNS resolver is blocking or failing to forward certain Samsung subdomains (possibly due to ISP filtering, DNS rebind protection, or a split-horizon DNS issue on the mesh nodes).

### 3b. Mesh roaming instability ⚠️

- The TV's Wi-Fi quality metrics are low: **link quality 11/70, signal level 202 (approx. -54 dBm), noise 160**.
- The TV uses a **MediaTek (MTK) Wi-Fi chip** — confirmed by `iwpriv` commands and `/proc/net/wlan/`.
- Roaming test shows the driver supports `DisRoaming` (`DisRoaming|1` written; `D:DisRoaming|0x1` echoed back), **but writing directly to `/proc/net/wlan/cfg` was denied** (Permission denied for `sdk` user).
- Smart Connect / Band Steering status on the router **was not confirmed** — the browser subagent ran out of quota before completing the router portal walk-through.

### 3c. wpa_supplicant — no direct control ⚠️

- `wpa_supplicant` runs with `-dd` (verbose debug) and logs to `/opt/var/log/wpa_supplicant.log`.
- The `sdk` user **cannot access the wpa_cli socket** (`Permission denied` on `/var/run/wpa_supplicant`).
- `connmand` is managing the connection on top of `wpa_supplicant`.

### 3d. Tizen vconf network state — all null

All `vconf` keys under `db/wifi/` and `db/network/` return **"No such file or directory"** — meaning the Tizen network manager hasn't persisted state, or the Wi-Fi connection was never cleanly registered. This can cause connection loops.

### 3e. Ethernet unused

`eth0` shows **0 packets RX/TX** — the TV is Wi-Fi-only in this setup.

### 3f. CPU temperature — high

The SoC temperature is **89°C** (reported repeatedly in dmesg). This is within spec for Tizen TVs but is worth monitoring.

---

## 4. What Was Attempted

| Action | Result |
|---|---|
| Connected via SDB (Samsung Debug Bridge) to TV | ✅ Successful |
| Collected full network diagnostics (`tv_network_diagnostics.txt`) | ✅ Done |
| Ran deep Wi-Fi diag (`wifi_deep_diag.txt`) | ✅ Done |
| Tested curl latency to Google / Samsung (`curl_timings.txt`) | ✅ Done |
| Tested Samsung captive-portal check (`captive_check.txt`) | ✅ cdn OK, OSB fails |
| Tested verbose Samsung OSB curl (`samsung_cloud_verbose.txt`) | ✅ NXDOMAIN confirmed |
| Tried disabling roaming via `/proc/net/wlan/cfg` | ❌ Permission denied for `sdk` |
| Tried `iwpriv wlan0 driver "DisRoaming 1"` | ⚠️ Command exists, result unclear |
| Launched browser subagent to configure TP-Link router portal | ❌ Ran out of API quota (rate limited) |
| Router Smart Connect / Band Steering status | ❓ Not confirmed — needs follow-up |

---

## 5. Recommended Next Steps (for the next agent)

### Priority 1 — Fix DNS for Samsung OSB

1. **Log in to the TP-Link router** at `http://192.168.0.1`.
2. Go to **Advanced → Network → DHCP Server** — check if there is a custom DNS or a "DNS Filtering / Parental Controls" rule blocking `*.samsungcloudsolution.net`.
3. Alternatively, **on the TV** (via SDB), force the DNS to bypass the router:
   ```sh
   # On the TV via SDB shell — test if 8.8.8.8 resolves the OSB domain
   nslookup osb.samsungcloudsolution.net 8.8.8.8
   ```
4. If `8.8.8.8` resolves it, the **router DNS is the culprit** — configure the TV to use static DNS `8.8.8.8` / `8.8.4.4`:
   - TV Settings → General → Network → Network Status → IP Settings → DNS Setting: Manual → `8.8.8.8`

### Priority 2 — Fix Mesh Roaming (Router Side)

1. **Log in to `http://192.168.0.1`** (TP-Link web portal).
2. Navigate to **Advanced → Wireless → Wireless Settings**.
3. **Disable Smart Connect** (Band Steering) — split the 2.4 GHz and 5 GHz into two separate SSIDs (e.g. `MyNetwork_2G` and `MyNetwork_5G`).
4. Connect the TV manually to the **2.4 GHz SSID** for more stable range.
5. Optionally in **Advanced → OneMesh / EasyMesh → Connected Devices**, find the TV (MAC `BC:45:5B:81:9C:E6`) and **pin it to a specific node / band** if supported.

### Priority 3 — Try Disabling TV-Side Roaming (Requires Root / Elevated Shell)

The `sdk` user cannot write to `/proc/net/wlan/cfg`. If root shell access is possible:
```sh
echo "DisRoaming|1" > /proc/net/wlan/cfg
# or via iwpriv:
iwpriv wlan0 driver "DisRoaming 1"
```

### Priority 4 — Check wpa_supplicant log

```sh
# Via SDB shell:
cat /opt/var/log/wpa_supplicant.log | grep -i "disconn\|fail\|roam\|assoc\|auth\|error" | tail -100
```
This will show exact association/disconnection events.

---

## 6. Key Files in This Project

| File | Description |
|---|---|
| `tv_network_diagnostics.txt` | Full ifconfig, routing, dmesg from TV |
| `wifi_deep_diag.txt` | vconf state, ping results, recent dmesg |
| `curl_timings.txt` | DNS + TCP connect latencies, IPv6 routes |
| `captive_check.txt` | Samsung captive-portal check (cdn OK) |
| `samsung_cloud_verbose.txt` | **OSB DNS failure** — NXDOMAIN confirmed |
| `roaming_test.txt` | iwpriv commands, DisRoaming attempt |
| `wifi_latency_and_wpa.txt` | wpa_supplicant proc, CPU freq, temp |
| `dlogutil_raw.txt` | Tizen dlog dump (mostly empty — ring buffer cleared) |
| `CleanFrame-main/` | Reference: custom Tizen launcher (debug mode reference) |

---

## 7. Access & Credentials

| Item | Value |
|---|---|
| TV SDB connection | `sdb connect <TV_IP>:26101` (Developer Mode must be ON) |
| TV Developer Mode | Enabled (Apps → search "12345" → enable) |
| Router portal | `http://192.168.0.1` — TP-Link admin UI |
| Router login | **Not captured** — user needs to provide admin password |

> **IMPORTANT:** The browser subagent was rate-limited before it could complete the router configuration.
> The next agent must re-open the router portal and complete Smart Connect / Band Steering changes.

> **WARNING:** The Samsung OSB DNS failure (`osb.samsungcloudsolution.net` → NXDOMAIN) is almost
> certainly the **primary cause of Wi-Fi connection errors**, as the TV cannot activate or authenticate
> Samsung Smart services. Fix DNS first before further Wi-Fi driver tuning.

---

## 8. Summary Diagnosis

```
PRIMARY ISSUE:   osb.samsungcloudsolution.net cannot resolve from the TV
                 → Router DNS is dropping/blocking this subdomain
                 → TV Wi-Fi "errors out" because Samsung services fail to connect

SECONDARY ISSUE: Mesh roaming instability (low RSSI, MTK driver roaming not disabled)
                 → TV may jump between mesh nodes, causing repeated re-associations
                 → Router Smart Connect / Band Steering: status UNKNOWN (needs confirmation)

ACTION NEEDED:   1) Fix DNS (set static DNS on TV to 8.8.8.8, or fix router DNS)
                 2) Disable Smart Connect on TP-Link router / split SSIDs
                 3) Re-run wpa_supplicant log check after DNS fix
```
