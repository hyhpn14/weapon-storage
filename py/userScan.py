import mysql.connector
from dialogs import DbMessage
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.uic import loadUi
from serial_handler import SerialHandler
from log_client import send_log
from db_config import get_db_connection

# Mapping keyword dari Arduino -> teks UI yang rapi
FINGER_STATUS_MAP = {
    "PLACE1": "Place your finger on the device",
    "LIFT": "Lift your finger",
    "PLACE2": "Place the same finger again",
    "PROCESSING": "Processing scan...",
    "SUCCESS": "Enrollment successful!",
    "FAIL": "Scan failed, please try again",
}


# --- CLASS SCAN FINGER ---
class ScanFinger(QDialog):

    def __init__(self, nrp, serial_handler=None, finger_id=None, gudang="GLOCK17"):
        super().__init__()
        loadUi("ui2/dialogs/enroll_finger.ui", self)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.nrp = nrp
        self.target_id = finger_id
        self.scan_count = 0
        self.enroll_success = False

        self.serial = serial_handler
        self.gudang = gudang

        # Dapatkan target role yang tepat berdasarkan gudang dari SerialHandler
        if self.serial and hasattr(self.serial, 'get_main_role_for_gudang'):
            self.target_role = self.serial.get_main_role_for_gudang()
        else:
            self.target_role = "MAIN_CONTROLLER"

        if hasattr(self, "lbNrpRF"):
            self.lbNrpRF.setText(f"{nrp}")

        if hasattr(self, "lbFingerR") and self.target_id is not None:
            self.lbFingerR.setText(str(self.target_id))

        self.start_pulsing_animation()
        
        # Samakan penutupan tombol dengan authScan
        self.btn_close.clicked.connect(self.stop_and_close)
        self.buttonBox.accepted.connect(self.save_data)
        self.buttonBox.rejected.connect(self.stop_and_close)

        # Trigger pendaftaran ke Target Controller
        if self.serial and self.target_id is not None:
            self.serial.send_command_to(self.target_role, f"e{self.target_id}")

    def stop_scanning(self):
        if self.serial:
            self.serial.send_command_to(self.target_role, "s")

    def stop_and_close(self):
        self.stop_scanning()
        self.reject()

    def start_pulsing_animation(self):
        self.opacity_effect = QGraphicsOpacityEffect(self.lbIconF)
        self.lbIconF.setGraphicsEffect(self.opacity_effect)

        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(1000)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.2)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.start()

    def handle_serial_data(self, role, tag, value):
        # Cocokkan dengan target_role yang valid
        if role != self.target_role:
            return

        if self.enroll_success:
            return

        for keyword, ui_text in FINGER_STATUS_MAP.items():
            if keyword in value:
                self.lbInfoF.setText(ui_text)

                if keyword == "SUCCESS":
                    self.enroll_success = True
                    self.stop_animation()
                    self.lbIconF.setStyleSheet(
                        "background-color: #28a745; border-radius: 50px;"
                    )
                    send_log(
                        kategori="user_auth",
                        aktivitas="finger_enroll",
                        detail="Fingerprint enrollment successful",
                        locker_id=self.target_id,
                        nrp=self.nrp,
                        nama="Device",
                        gudang=self.gudang,
                        metode="fingerprint"
                    )
                return

        self.lbInfoF.setText(value)

    def stop_animation(self):
        if hasattr(self, "animation"):
            self.animation.stop()
            self.opacity_effect.setOpacity(1.0)

    def save_data(self):
        if not self.enroll_success:
            self.lbInfoF.setText("Please complete the fingerprint scan first!")
            self.lbInfoF.setStyleSheet("color: red;")
            return
        self.stop_scanning()
        self.accept()

    def reset_form(self):
        if self.serial and self.target_id is not None:
            self.serial.send_command_to(self.target_role, "d", str(self.target_id))
        self.scan_count = 0
        self.enroll_success = False
        self.lbInfoF.setText("Please Scan Finger Again...")
        self.lbIconF.setStyleSheet("background-color: transparent;")
        self.start_pulsing_animation()

    def closeEvent(self, event):
        self.stop_scanning()
        event.accept()


# --- CLASS SCAN RFID ---
class ScanRfid(QDialog):

    def __init__(self, nrp, serial_handler=None):
        super().__init__()
        loadUi("ui2/dialogs/enroll_rfid.ui", self)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.nrp = nrp
        self.serial = serial_handler
        self.current_uid = None

        if self.serial and hasattr(self.serial, 'get_main_role_for_gudang'):
            self.target_role = self.serial.get_main_role_for_gudang()
        else:
            self.target_role = "MAIN_CONTROLLER"

        if hasattr(self, "lbNrpRC"):
            self.lbNrpRC.setText(f"{nrp}")

        self.start_pulsing_animation()
        self.btn_close.clicked.connect(self.stop_and_close)
        self.buttonBox.accepted.connect(self.save_data)
        self.buttonBox.rejected.connect(self.stop_and_close)

        if self.serial:
            self.serial.send_command_to(self.target_role, "r")

    def stop_scanning(self):
        if self.serial:
            self.serial.send_command_to(self.target_role, "s")

    def stop_and_close(self):
        self.stop_scanning()
        self.reject()

    def start_pulsing_animation(self):
        self.opacity_effect = QGraphicsOpacityEffect(self.lbIconR)
        self.lbIconR.setGraphicsEffect(self.opacity_effect)

        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(1000)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.2)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.start()

    def handle_serial_data(self, role, tag, value):
        if role == self.target_role and tag == "RFID":
            uid = value.strip().replace(" ", "")
            self.process_rfid_input(uid)

    def is_rfid_registered(self, uid):
        conn = get_db_connection()
        if conn is None:
            print("Warning: Gagal terhubung ke database untuk mengecek RFID")
            return False, None

        try:
            cursor = conn.cursor()
            query = "SELECT nrp FROM tb_users WHERE uid = %s"
            cursor.execute(query, (uid,))
            result = cursor.fetchone()

            cursor.close()
            conn.close()

            if result:
                return True, result[0]
            return False, None

        except mysql.connector.Error as err:
            print(f"Database Error pada is_rfid_registered: {err}")
            if conn:
                conn.close()
            return False, None

    def process_rfid_input(self, uid):
        is_registered, owner_nrp = self.is_rfid_registered(uid)

        if is_registered:
            self.current_uid = None
            if hasattr(self, "lbCardR"):
                self.lbCardR.setText("REJECTED")

            self.lbInfoR.setText(f"Kartu Sudah Terdaftar! (Milik NRP: {owner_nrp})")
            self.lbInfoR.setStyleSheet("color: red; font-weight: bold;")

            DbMessage.warning(
                self,
                "RFID Duplikat",
                f"Kartu RFID ini sudah terikat dengan NRP: {owner_nrp}!\nGunakan kartu lain.",
            )
            return

        self.current_uid = uid
        if hasattr(self, "lbCardR"):
            self.lbCardR.setText(f"{uid}")

        self.lbInfoR.setText("ID Card Successfully Scanned!")
        self.lbInfoR.setStyleSheet("color: green; font-weight: bold;")

        if hasattr(self, "animation"):
            self.animation.stop()
            self.opacity_effect.setOpacity(1.0)

    def save_data(self):
        if self.current_uid is None:
            self.lbInfoR.setText("Please Scan the Card First!")
            self.lbInfoR.setStyleSheet("color: red;")
            return
        self.stop_scanning()
        self.accept()

    def reset_form(self):
        self.current_uid = None
        self.lbInfoR.setText("Silakan tempel kartu RFID...")
        self.lbIconR.setStyleSheet("background-color: transparent;")
        self.start_pulsing_animation()

    def closeEvent(self, event):
        self.stop_scanning()
        event.accept()


# --- CLASS SCAN PIN ---
class ScanPin(QDialog):

    def __init__(self, nrp):
        super().__init__()
        loadUi("ui2/dialogs/enroll_pin.ui", self)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.nrp = nrp

        if hasattr(self, "lbNrpRP"):
            self.lbNrpRP.setText(f"{nrp}")

        save_button = self.buttonBox.button(QDialogButtonBox.Save)
        if save_button:
            save_button.setDefault(True)
            save_button.setFocus()

        self.buttonBox.accepted.connect(self.save_data)
        self.buttonBox.rejected.connect(self.reset_form)
        self.btn_close.clicked.connect(self.reject)

    def save_data(self):
        pin = self.lbPinR.text()
        if len(pin) < 4:
            QMessageBox.warning(self, "Error", "PIN terlalu pendek!")
            return
        self.pin = pin
        self.accept()

    def reset_form(self):
        self.lbPinR.clear()