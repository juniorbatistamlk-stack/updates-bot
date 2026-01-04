import platform
import subprocess
import hashlib
import uuid

def get_hwid():
    """Generates a stable Hardware ID based on machine characteristics"""
    try:
        system = platform.system()
        machine = platform.machine()
        node = platform.node()
        
        # Get MAC address using uuid (works on all platforms without external commands)
        mac = uuid.getnode()
        mac_str = ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))
        
        # CPU Info - use platform info instead of wmic
        processor = platform.processor()
        
        # Try to get Windows-specific info via PowerShell (works on Win10/11)
        cpu_id = ""
        disk_id = ""
        
        if system == "Windows":
            try:
                # Use PowerShell instead of deprecated WMIC
                cpu_result = subprocess.run(
                    ["powershell", "-Command", "(Get-CimInstance Win32_Processor).ProcessorId"],
                    capture_output=True, text=True, timeout=5
                )
                if cpu_result.returncode == 0:
                    cpu_id = cpu_result.stdout.strip()
            except Exception:
                cpu_id = processor
            
            try:
                disk_result = subprocess.run(
                    ["powershell", "-Command", "(Get-CimInstance Win32_DiskDrive | Select-Object -First 1).SerialNumber"],
                    capture_output=True, text=True, timeout=5
                )
                if disk_result.returncode == 0:
                    disk_id = disk_result.stdout.strip()
            except Exception:
                disk_id = mac_str
        else:
            cpu_id = processor
            disk_id = mac_str

        # Combine unique identifiers
        raw_id = f"{node}-{machine}-{cpu_id}-{disk_id}-{mac_str}"
        
        # Hash it for privacy and consistent length
        hwid = hashlib.sha256(raw_id.encode()).hexdigest()
        return hwid
        
    except Exception:
        # Fallback using MAC address
        mac = uuid.getnode()
        return hashlib.sha256(f"fallback-{platform.node()}-{mac}".encode()).hexdigest()

if __name__ == "__main__":
    print(f"HWID: {get_hwid()}")
