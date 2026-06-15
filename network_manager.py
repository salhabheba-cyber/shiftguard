import socket
import subprocess
import re
import platform
import os

OS_TYPE = platform.system()
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts" if OS_TYPE == "Windows" else "/etc/hosts"

# ─────────────────────────────────────────────────────────────────────────────
# NETWORK INFO
# ─────────────────────────────────────────────────────────────────────────────

def get_network_info():
    """Get server IP, router IP, device count"""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        router_ip = _get_gateway()
        device_count = _get_device_count()
        return {
            "status": "success",
            "hostname": hostname,
            "local_ip": local_ip,
            "router_ip": router_ip,
            "device_count": device_count
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_hosts_status():
    """Check if hosts file blocking is active"""
    try:
        with open(HOSTS_PATH, 'r') as f:
            content = f.read()
        blocked = [l for l in content.split('\n')
                   if l.strip() and not l.strip().startswith('#')
                   and '127.0.0.1' in l
                   and len(l.split()) >= 2
                   and l.split()[1] not in ('localhost', 'localhost.localdomain')]
        return {
            "active": len(blocked) > 0,
            "blocked_count": len(blocked)
        }
    except Exception as e:
        return {"active": False, "blocked_count": 0, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# NETWORK SCAN
# ─────────────────────────────────────────────────────────────────────────────

def scan_network():
    """Scan network using Windows ARP table — no admin required"""
    try:
        devices = []

        if OS_TYPE == "Windows":
            output = subprocess.check_output(['arp', '-a'], text=True, timeout=15)
            for line in output.split('\n'):
                line = line.strip()
                if not line or line.startswith('Interface') or 'dynamic' not in line.lower():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    ip  = parts[0]
                    mac = parts[1] if len(parts) > 1 else "Unknown"
                    hostname = _reverse_dns(ip)
                    devices.append({
                        "ip": ip,
                        "mac": mac,
                        "hostname": hostname,
                        "status": "online"
                    })
        else:
            # Linux fallback
            output = subprocess.check_output(['ip', 'neigh'], text=True, timeout=15)
            for line in output.split('\n'):
                parts = line.split()
                if len(parts) >= 5 and 'REACHABLE' in line:
                    ip  = parts[0]
                    mac = parts[4]
                    hostname = _reverse_dns(ip)
                    devices.append({
                        "ip": ip,
                        "mac": mac,
                        "hostname": hostname,
                        "status": "online"
                    })

        return {
            "status": "success",
            "device_count": len(devices),
            "devices": devices[:50]
        }

    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Scan timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# HOSTS FILE BLOCKING
# ─────────────────────────────────────────────────────────────────────────────

def apply_hosts_blocking(domains):
    """Write domains to hosts file to block them"""
    try:
        # Read existing content
        with open(HOSTS_PATH, 'r') as f:
            existing = f.read()

        # Build new entries (skip duplicates)
        new_entries = []
        for domain in domains:
            domain = domain.strip().lower()
            if domain and domain not in existing:
                new_entries.append(f"127.0.0.1 {domain}")
                new_entries.append(f"127.0.0.1 www.{domain}")

        if not new_entries:
            return True, "All domains already blocked"

        # Append to hosts file
        marker = "\n# ShiftGuard Blocked Sites\n"
        with open(HOSTS_PATH, 'a') as f:
            f.write(marker + '\n'.join(new_entries) + '\n')

        # Flush DNS cache
        _flush_dns()
        return True, f"Blocked {len(domains)} domains successfully"

    except PermissionError:
        return False, "Permission denied — run ShiftGuard as Administrator"
    except Exception as e:
        return False, str(e)


def remove_hosts_blocking():
    """Remove all ShiftGuard blocked entries from hosts file"""
    try:
        with open(HOSTS_PATH, 'r') as f:
            lines = f.readlines()

        # Keep only lines that are not ShiftGuard blocks
        new_lines = []
        skip = False
        for line in lines:
            if '# ShiftGuard Blocked Sites' in line:
                skip = True
                continue
            if skip and line.strip().startswith('127.0.0.1'):
                continue
            skip = False
            new_lines.append(line)

        with open(HOSTS_PATH, 'w') as f:
            f.writelines(new_lines)

        _flush_dns()
        return True, "All blocks removed successfully"

    except PermissionError:
        return False, "Permission denied — run ShiftGuard as Administrator"
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_gateway():
    try:
        if OS_TYPE == "Windows":
            out = subprocess.check_output(['ipconfig'], text=True, timeout=5)
            m = re.search(r'Default Gateway\s*\.+\s*:\s*([\d\.]+)', out, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        else:
            out = subprocess.check_output(['ip', 'route'], text=True, timeout=5)
            m = re.search(r'default via ([\d\.]+)', out)
            if m:
                return m.group(1).strip()
    except:
        pass
    return "Unknown"


def _get_device_count():
    try:
        if OS_TYPE == "Windows":
            out = subprocess.check_output(['arp', '-a'], text=True, timeout=10)
            return len([l for l in out.split('\n') if 'dynamic' in l.lower()])
        else:
            out = subprocess.check_output(['ip', 'neigh'], text=True, timeout=10)
            return len([l for l in out.split('\n') if 'REACHABLE' in l])
    except:
        return 0


def _reverse_dns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except:
        return "Unknown"


def _flush_dns():
    try:
        if OS_TYPE == "Windows":
            subprocess.run(['ipconfig', '/flushdns'], capture_output=True, timeout=5)
        else:
            subprocess.run(['systemctl', 'restart', 'systemd-resolved'],
                           capture_output=True, timeout=5)
    except:
        pass
