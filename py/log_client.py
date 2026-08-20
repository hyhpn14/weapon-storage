import requests
import json
import threading

# Sesuaikan dengan IP Server Web Dashboard Anda
SERVER_URL = "http://10.10.20.27/web-storage-fixed/php/logs/log_activity.php"

def send_log(kategori, aktivitas, detail="", locker_id=None, nrp="SYSTEM", nama="Device", gudang="GLOCK17", metode=None, status="success"):
    """
    Kirim data log aktivitas ke Server Web Dashboard via REST API HTTP POST secara Asynchronous.
    """
    # 1. Print informasi log langsung ke terminal Raspberry Pi
    print(f"\n[SEND LOG {status.upper()}] {nrp} - {nama} | {kategori} -> {aktivitas} ({metode}) | Locker: {locker_id}", flush=True)

    payload = {
        "nrp": nrp,
        "nama": nama,
        "kategori": kategori,
        "aktivitas": aktivitas,
        "metode": metode,
        "detail": detail,
        "locker_id": locker_id,
        "gudang": gudang,
        "status": status
    }

    # 2. Kirim payload ke server di background thread
    def _worker():
        try:
            response = requests.post(SERVER_URL, json=payload, timeout=3)
            if response.status_code == 200:
                print(f"  └── [SERVER RESP 200] {response.text}", flush=True)
            else:
                print(f"  └── [LOG WARNING] HTTP Error {response.status_code}: {response.text}", flush=True)
        except Exception as e:
            print(f"  └── [LOG ERROR] Gagal terhubung ke Web Server: {e}", flush=True)

    thread = threading.Thread(target=_worker)
    thread.daemon = True
    thread.start()