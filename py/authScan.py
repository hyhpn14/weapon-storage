import subprocess
from db_config import get_db_connection, log_login_attempt
from dialogs import DbMessage
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.uic import loadUi
from camera import start_access_capture
from serial_handler import SerialHandler
from log_client import send_log
from screens.custom_dialog import CustomMessageBox


# --- CLASS AUTH FINGER ---
class AuthFinger(QDialog):
    go_back = pyqtSignal()
    success = pyqtSignal()

    def __init__(self, parent=None, serial_handler=None, gudang="GLOCK17"):
        super().__init__(parent)
        loadUi("ui/auth_finger.ui", self)
        self.setWindowFlags(
                    Qt.Window
                    | Qt.FramelessWindowHint
                    | Qt.WindowStaysOnTopHint
                    | Qt.CustomizeWindowHint
                )
        self.setWindowModality(Qt.ApplicationModal)
        self.center_dialog()

        self.btCls_finger.clicked.connect(self.stop_and_close)

        self.gudang = gudang
        self.user_nrp = None
        self.user_nama = None
        self.user_status = None
        self.user_id_locker = None
        self.was_failed = False

        self.serial = serial_handler
        
        # Ambil role utama berdasarkan gudang aktif
        if self.serial and hasattr(self.serial, 'get_main_role_for_gudang'):
            self.target_role = self.serial.get_main_role_for_gudang()
        else:
            self.target_role = "MAIN_CONTROLLER"

        if self.serial:
            self.serial.send_command_to(self.target_role, "v")
            self.serial.send_command_to(self.target_role, "beep")
            print(f"Perintah 'v & beep' dikirim ke {self.target_role}")

    def center_dialog(self):
            """Memaksa posisi dialog berada di tengah-tengah MainApp/Screen."""
            if self.parent():
                # Jika ada parent (MainApp), posisikan tepat di tengah MainApp
                parent_rect = self.parent().geometry()
                geo = self.geometry()
                x = parent_rect.x() + (parent_rect.width() - geo.width()) // 2
                y = parent_rect.y() + (parent_rect.height() - geo.height()) // 2
                self.move(x, y)
            else:
                # Fallback ke tengah layar kiosk 1024x600 jika parent belum siap
                from utils import center_on_screen
                center_on_screen(self)

    def handle_serial_data(self, role, tag, value):
        if role != self.target_role or tag not in ("FP", "FINGER"):
            return

        value = value.strip()

        if value.startswith("MATCH"):
            parts = value.split(":")
            finger_id = parts[1].strip() if len(parts) > 1 else None
            if finger_id:
                self.check_finger_in_db(finger_id)
                print(f"DEBUG: Finger ID yang diterima: {finger_id}")
        elif value == "NOMATCH":
            self.lbInfoF.setText("Fingerprint not recognized")
            self.lbInfoF.setStyleSheet("color: red;")
            log_login_attempt("Unknown", "finger", 0, self.gudang, self.user_id_locker)
            
            self.was_failed = True
            self.stop_scanning()
            QTimer.singleShot(1000, self.reject)

    def check_finger_in_db(self, finger_id):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            query = """
                        SELECT nrp, nama, finger, status, id_locker 
                        FROM tb_users 
                        WHERE finger = %s AND (gudang = %s OR status = 'ADMIN')
                    """
            cursor.execute(query, (finger_id, self.gudang))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                self.user_nrp = user["nrp"]
                self.user_nama = user["nama"]
                self.user_status = user.get("status", "USER")
                self.user_id_locker = user["id_locker"]

                self.lbInfoF.setText(f"Welcome {self.user_nama}!")
                self.lbInfoF.setStyleSheet("color: green;")

                if hasattr(self, "lbNrpF"):
                    self.lbNrpF.setText(str(user["nrp"]))

                display_finger_id = (
                    finger_id if finger_id else str(user.get("finger", ""))
                )
                if hasattr(self, "lbFinger"):
                    self.lbFinger.setText(str(display_finger_id))

                start_access_capture(
                    self,
                    reason="success_fingerprint",
                    save_dir=f"captures/{self.gudang}",
                )
                send_log(
                    kategori="user_auth",
                    aktivitas="finger_login",            
                    detail=f"User {self.user_nrp} ({self.user_nama}) berhasil login via Fingerprint.",
                    locker_id=self.user_id_locker,
                    nrp=self.user_nrp,
                    nama=self.user_nama,
                    gudang=self.gudang,
                    metode="fingerprint",
                    status="success"
                )
                self.stop_scanning()
                log_login_attempt(
                    self.user_nrp, "finger", 1, self.gudang, self.user_id_locker
                )
                QTimer.singleShot(2000, self.accept)
            else:
                self.lbInfoF.setText("Fingerprint not registered")
                self.lbInfoF.setStyleSheet("color: red;")
                send_log(
                    kategori="user_auth",
                    aktivitas="finger_login_failed",
                    detail="Percobaan login fingerprint gagal.",
                    locker_id=self.user_id_locker,
                    nrp="Unknown",
                    nama="Device",
                    gudang=self.gudang,
                    metode="fingerprint",
                    status="failed"
                )
                log_login_attempt("Unknown", "finger", 0, self.gudang, self.user_id_locker)

                self.was_failed = True
                self.stop_scanning()
                QTimer.singleShot(1000, self.reject)
        except Exception as err:
            print(f"Error Database: {err}")

    def stop_scanning(self):
        if self.serial:
            self.serial.send_command_to(self.target_role, "s")

    def stop_and_close(self):
        self.stop_scanning()
        self.reject()

    def closeEvent(self, event):
        self.stop_scanning()
        event.accept()


# --- CLASS AUTH RFID ---
class AuthRFID(QDialog):
    go_back = pyqtSignal()
    success = pyqtSignal()

    SCAN_TIMEOUT_MS = 10000
    MAX_ATTEMPTS = 3

    def __init__(self, parent=None, serial_handler=None, gudang="GLOCK17"):
        super().__init__(parent)
        loadUi("ui/auth_rfid.ui", self)
        self.setWindowFlags(
                    Qt.Window
                    | Qt.FramelessWindowHint
                    | Qt.WindowStaysOnTopHint
                    | Qt.CustomizeWindowHint
                )
        self.setWindowModality(Qt.ApplicationModal)
        self.center_dialog()

        self.btCls_rfid.clicked.connect(self.stop_and_close)

        self.gudang = gudang
        self.user_nrp = None
        self.user_nama = None
        self.user_status = None
        self.user_id_locker = None
        self.scan_attempts = 0
        self.was_failed = False

        self.scan_timeout_timer = QTimer(self)
        self.scan_timeout_timer.setSingleShot(True)
        self.scan_timeout_timer.timeout.connect(self.handle_scan_timeout)

        self.serial = serial_handler
        
        # Ambil role utama berdasarkan gudang aktif
        if self.serial and hasattr(self.serial, 'get_main_role_for_gudang'):
            self.target_role = self.serial.get_main_role_for_gudang()
        else:
            self.target_role = "MAIN_CONTROLLER"

        if self.serial:
            self.serial.send_command_to(self.target_role, "beep")
            self.start_scan_attempt()

    def center_dialog(self):
            """Memaksa posisi dialog berada di tengah-tengah MainApp/Screen."""
            if self.parent():
                # Jika ada parent (MainApp), posisikan tepat di tengah MainApp
                parent_rect = self.parent().geometry()
                geo = self.geometry()
                x = parent_rect.x() + (parent_rect.width() - geo.width()) // 2
                y = parent_rect.y() + (parent_rect.height() - geo.height()) // 2
                self.move(x, y)
            else:
                # Fallback ke tengah layar kiosk 1024x600 jika parent belum siap
                from utils import center_on_screen
                center_on_screen(self)

    def start_scan_attempt(self):
        self.scan_attempts += 1

        if hasattr(self, "lbInfoR"):
            if self.scan_attempts == 1:
                self.lbInfoR.setText("Tempelkan kartu...")
                self.lbInfoR.setStyleSheet("color:white;")
            else:
                self.lbInfoR.setText(
                    f"Kartu tidak terdeteksi, mencoba lagi... "
                    f"({self.scan_attempts}/{self.MAX_ATTEMPTS})"
                )
                self.lbInfoR.setStyleSheet("color: yellow;")

        self.serial.send_command_to(self.target_role, "r")
        self.scan_timeout_timer.start(self.SCAN_TIMEOUT_MS)

    def handle_scan_timeout(self):
        if self.scan_attempts < self.MAX_ATTEMPTS:
            self.start_scan_attempt()
        else:
            self.stop_scanning()
            if hasattr(self, "lbInfoR"):
                self.lbInfoR.setText(
                    f"Kartu tidak terdeteksi setelah {self.MAX_ATTEMPTS}x percobaan."
                )
                self.lbInfoR.setStyleSheet("color: red;")
            log_login_attempt("Unknown", "rfid", 0, self.gudang, self.user_id_locker)

            self.was_failed = True
            QTimer.singleShot(1000, self.reject)

    def handle_serial_data(self, role, tag, value):
        if role != self.target_role or tag != "RFID":
            return

        self.scan_timeout_timer.stop()
        uid = value.strip().replace(" ", "").upper()
        self.check_rfid_in_db(uid)

    def check_rfid_in_db(self, uid):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            query = (
                "SELECT nrp, nama, uid, status, id_locker FROM tb_users WHERE"
                " UPPER(uid) = %s AND (gudang = %s OR status = 'ADMIN')"
            )
            cursor.execute(query, (uid, self.gudang))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                self.user_nrp = user["nrp"]
                self.user_nama = user["nama"]
                self.user_status = user["status"]
                self.user_id_locker = user["id_locker"]

                self.lbInfoR.setText(f"Welcome {self.user_nama}!")
                self.lbInfoR.setStyleSheet("color: green;")

                if hasattr(self, "lbNrpC"):
                    self.lbNrpC.setText(str(user["nrp"]))
                if hasattr(self, "lbCard"):
                    self.lbCard.setText(str(user["uid"]))

                log_login_attempt(
                    self.user_nrp, "rfid", 1, self.gudang, self.user_id_locker
                )
                self.serial.send_command_to(self.target_role, "beeptrue")
                send_log(
                    kategori="user_auth",
                    aktivitas="rfid_login",
                    detail=f"User {self.user_nrp} ({self.user_nama}) berhasil login via RFID.",
                    locker_id=self.user_id_locker,
                    nrp=self.user_nrp,
                    nama=self.user_nama,
                    gudang=self.gudang,
                    metode="rfid",
                    status="success"
                )
                start_access_capture(
                    self, reason="success_rfid", save_dir=f"captures/{self.gudang}"
                )

                self.stop_scanning()
                QTimer.singleShot(2000, self.accept)
            else:
                self.lbInfoR.setText("ID Card not registered")
                self.serial.send_command_to(self.target_role, "beepfail")
                send_log(
                    kategori="user_auth",
                    aktivitas="rfid_login_failed",
                    detail=f"Percobaan login RFID gagal.",
                    locker_id=self.user_id_locker,
                    nrp="Unknown",
                    nama="Unknown",
                    gudang=self.gudang,
                    metode="rfid",
                    status="failed"
                )
                self.lbInfoR.setStyleSheet("color: red;")
                log_login_attempt("Unknown", "rfid", 0, self.gudang, self.user_id_locker)

                self.was_failed = True
                self.stop_scanning()
                QTimer.singleShot(1000, self.reject)
        except Exception as err:
            print(f"Error Database: {err}")

    def stop_scanning(self):
        self.scan_timeout_timer.stop()
        if self.serial:
            self.serial.send_command_to(self.target_role, "s")

    def stop_and_close(self):
        self.stop_scanning()
        self.reject()

    def closeEvent(self, event):
        self.stop_scanning()
        event.accept()


# --- CLASS AUTH PIN ---
class AuthPin(QDialog):
    go_back = pyqtSignal()
    submitSuccess = pyqtSignal()

    def __init__(self, parent=None, serial_handler=None, gudang="GLOCK17"):
        super().__init__(parent)
        loadUi("ui/auth_pin2.ui", self)

        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.CustomizeWindowHint
        )
        self.setWindowModality(Qt.ApplicationModal)       
        self.center_dialog()

        self.btCls_pin2.clicked.connect(self.reject)
        self.btSubmit.clicked.connect(self.checkPin)
        self.lbPin.setEchoMode(QLineEdit.Password)
        self.btSubmit.setDefault(True)

        self.gudang = gudang
        self.user_nrp = None
        self.user_nama = None
        self.user_status = None
        self.user_id_locker = None
        self.was_failed = False

        self.serial = serial_handler

        # Pemicu Process Virtual Keyboard
        self.keyboard_process = None
        self.lbPin.installEventFilter(self)
        
        # Ambil role utama berdasarkan gudang aktif
        if self.serial and hasattr(self.serial, 'get_main_role_for_gudang'):
            self.target_role = self.serial.get_main_role_for_gudang()
        else:
            self.target_role = "MAIN_CONTROLLER"

        if self.serial:
            self.serial.send_command_to(self.target_role, "beep")

    def center_dialog(self):
        """Memaksa posisi dialog berada di tengah-tengah MainApp/Screen."""
        if self.parent():
            # Jika ada parent (MainApp), posisikan tepat di tengah MainApp
            parent_rect = self.parent().geometry()
            geo = self.geometry()
            x = parent_rect.x() + (parent_rect.width() - geo.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - geo.height()) // 2
            self.move(x, y)
        else:
            # Fallback ke tengah layar kiosk 1024x600 jika parent belum siap
            from utils import center_on_screen
            center_on_screen(self)

    # --- HANDLE VIRTUAL KEYBOARD ---
    def eventFilter(self, obj, event):
        # Trigger hanya pada FocusIn untuk menghindari pemanggilan berulang
        if obj == self.lbPin and event.type() == QEvent.FocusIn:
            self.open_default_keyboard()
        return super().eventFilter(obj, event)

    def open_default_keyboard(self):
        """Membuka keyboard wvkbd bawaan RPi tampilan default lengkap."""
        try:
            if (
                self.keyboard_process is None
                or self.keyboard_process.poll() is not None
            ):
                # Memanggil wvkbd tanpa parameter layout agar memakai tampilan default
                self.keyboard_process = subprocess.Popen(["wvkbd-mobintl", "-H","380"])
        except Exception:
            try:
                # Fallback ke wvkbd standar
                self.keyboard_process = subprocess.Popen(["wvkbd", "-H","380"])
            except Exception as e:
                print(f"Gagal membuka wvkbd: {e}")

    def close_virtual_keyboard(self):
        """Menutup wvkbd secara aman."""
        try:
            subprocess.Popen(["killall", "wvkbd-mobintl", "wvkbd"])
            self.keyboard_process = None
        except Exception as e:
            print(f"Gagal menutup keyboard: {e}")

    def closeEvent(self, event):
        self.close_virtual_keyboard()
        event.accept()

    def reject(self):
        self.close_virtual_keyboard()
        super().reject()

    def accept(self):
        self.close_virtual_keyboard()
        super().accept()

    def show_error_dialog(self, message="WRONG PIN!"):
        # PENTING: Tutup keyboard sebelum membuka dialog error
        self.close_virtual_keyboard()
        CustomMessageBox.show_warning(self, "Error", message)                   
        # msg = DbMessage(title="Error", message=message, success=False, parent=self)
        # msg.exec_()
        self.lbPin.clear()

    def checkPin(self):
        entered_pin = self.lbPin.text()

        if not entered_pin:
            self.show_error_dialog("PIN tidak boleh kosong!")
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT nrp, nama, pin, status, id_locker 
                FROM tb_users 
                WHERE pin = %s AND (gudang = %s OR status = 'ADMIN')
            """
            cursor.execute(query, (entered_pin, self.gudang))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                self.user_nrp = user["nrp"]
                self.user_nama = user["nama"]
                self.user_status = user["status"]
                self.user_id_locker = user["id_locker"]

                if self.serial:
                    self.serial.send_command_to(self.target_role, "beeptrue")
                send_log(
                    kategori="user_auth",
                    aktivitas="pin_login",
                    detail=f"User {self.user_nrp} ({self.user_nama}) berhasil login via PIN.",
                    locker_id=self.user_id_locker,
                    nrp=self.user_nrp,
                    nama=self.user_nama,
                    gudang=self.gudang,
                    metode="pin",
                    status="success"
                )
                self.lbInfoP.setText(f"Welcome {self.user_nama}!")
                self.lbInfoP.setStyleSheet("color: green;")

                start_access_capture(
                    self, reason="success_pin", save_dir=f"captures/{self.gudang}"
                )
                self.lbPin.clear()
                log_login_attempt(
                    self.user_nrp, "pin", 1, self.gudang, self.user_id_locker
                )
                self.submitSuccess.emit()
                QTimer.singleShot(2000, self.accept)
            else:
                if self.serial:
                    self.serial.send_command_to(self.target_role, "beepfail")
                send_log(
                    kategori="user_auth",
                    aktivitas="pin_login_failed",
                    detail=f"Percobaan login PIN gagal.",
                    locker_id=self.user_id_locker,
                    nrp="Unknown",
                    nama="Unknown",
                    gudang=self.gudang,
                    metode="pin",
                    status="failed"
                )
                log_login_attempt(
                    "Unknown", "pin", 0, self.gudang, self.user_id_locker
                )

                self.was_failed = True
                self.show_error_dialog("WRONG PIN!")
                self.reject()
        except Exception as err:
            print(f"Error Database: {err}")
            self.show_error_dialog("Terjadi kesalahan pada sistem.")

    def reset_state(self):
        self.lbPin.clear()