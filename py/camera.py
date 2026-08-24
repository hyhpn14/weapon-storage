import os
import sys
import time

try:
  import cv2

  CV2_AVAILABLE = True
except ImportError:
  CV2_AVAILABLE = False

from db_config import get_db_connection
from PyQt5.QtCore import QThread, pyqtSignal


def log_capture_to_db(gudang, reason, filepath):
    """Simpan record capture ke tb_unauthorized_capture."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tb_unauthorized_capture (gudang, reason, photo_path)"
            " VALUES (%s, %s, %s)",
            (gudang, reason, os.path.abspath(filepath)),
        )
        conn.commit()
        cursor.close()
        conn.close()
        print(
            f"[Capture] Record tersimpan ke DB: gudang={gudang}, reason={reason}"
        )
    except Exception as e:
        print(f"[Capture] Gagal simpan record capture ke DB: {e}")


class CaptureWorker(QThread):
    """Worker thread untuk mengambil 1 frame dari kamera (Cross-Platform)."""

    finished_capture = pyqtSignal(str)
    failed_capture = pyqtSignal(str)

    def __init__(self,reason="unauthorized", save_dir="captures", camera_index=None, parent=None,):
        super().__init__(parent)
        self.reason = reason
        self.save_dir = save_dir
        self.camera_index = camera_index

    def _open_camera(self):
        indices_to_try = (
            [self.camera_index] if self.camera_index is not None else [0, 1, 2, 3]
        )
        is_windows = sys.platform.startswith("win")
        is_linux = sys.platform.startswith("linux")

        for idx in indices_to_try:
            if is_windows:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            elif is_linux:
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            else:
                cap = cv2.VideoCapture(idx)

            if cap.isOpened():
                if is_linux:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

                ret, _ = cap.read()
                if ret:
                    os_name = ( "Windows" if is_windows else ("Linux" if is_linux else "Other"))                    
                    print(f"[Capture] Berhasil membuka kamera index {idx} ({os_name})")
                    return cap, idx

                cap.release()

        return None, None

    def run(self):
        if not CV2_AVAILABLE:
            self.failed_capture.emit("Modul opencv-python belum terpasang.")
            return

        try:
            os.makedirs(self.save_dir, exist_ok=True)
            cap, used_index = self._open_camera()

            if cap is None:
                self.failed_capture.emit("Tidak ada kamera yang terdeteksi.")
                return

            # Flush frame awal agar auto-exposure/focus menyesuaikan
            for _ in range(3):
                cap.read()
                time.sleep(0.05)

            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                self.failed_capture.emit(f"Gagal mengambil frame dari kamera index {used_index}.")                
                return

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_reason = "".join(  c if c.isalnum() or c in "-_" else "_" for c in self.reason )            
            filename = f"{timestamp}_{safe_reason}.jpg"
            filepath = os.path.join(self.save_dir, filename)

            cv2.imwrite(filepath, frame)
            self.finished_capture.emit(filepath)

        except Exception as e:
            self.failed_capture.emit(str(e))


def start_access_capture(owner, reason="access", save_dir="captures", camera_index=None):
    """Helper utama dipanggil dari dialog auth saat BERHASIL atau GAGAL."""
    if not hasattr(owner, "_capture_workers"):
        owner._capture_workers = []

    gudang = getattr(owner, "gudang", "UNKNOWN")
    worker = CaptureWorker(
        reason=reason, save_dir=save_dir, camera_index=camera_index
    )

    def _on_finished(path):
        print(f"[Capture] Foto ({reason}) tersimpan: {path}")
        log_capture_to_db(gudang, reason, path)
        if worker in owner._capture_workers:
            owner._capture_workers.remove(worker)

    def _on_failed(err):
        print(f"[Capture] Gagal ambil foto ({reason}): {err}")
        if worker in owner._capture_workers:
            owner._capture_workers.remove(worker)

    worker.finished_capture.connect(_on_finished)
    worker.failed_capture.connect(_on_failed)

    owner._capture_workers.append(worker)
    worker.start()
    return worker


# Alias penyesuaian versi lama
def start_unauthorized_capture(owner, reason, save_dir="captures", camera_index=None):
    return start_access_capture(owner, reason=reason, save_dir=save_dir, camera_index=camera_index  )