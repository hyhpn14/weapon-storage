from db_config import get_db_connection, log_login_attempt
from dialogs import DbMessage
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.uic import loadUi
from camera import start_access_capture
from serial_handler import SerialHandler


# --- CLASS AUTH FINGER ---
class AuthFinger(QDialog):
  go_back = pyqtSignal()
  success = pyqtSignal()

  def __init__(self, serial_handler=None, gudang="GLOCK17"):
    super().__init__()
    loadUi("ui/auth_finger.ui", self)
    self.setWindowFlags(Qt.FramelessWindowHint)
    self.setWindowModality(Qt.ApplicationModal)

    self.btCls_finger.clicked.connect(self.stop_and_close)

    self.gudang = gudang
    self.user_nrp = None
    self.user_nama = None
    self.user_status = None
    self.user_id_locker = None

    # Flag penanda kegagalan untuk ditangkap oleh Login.py
    self.was_failed = False

    self.serial = serial_handler
    if self.serial:
      self.serial.send_command_to("MAIN_CONTROLLER", "v")
      self.serial.send_command_to("MAIN_CONTROLLER", "beep")
      print("Perintah 'v & beep' dikirim ke MAIN_CONTROLLER")

  def handle_serial_data(self, role, tag, value):
    if role != "MAIN_CONTROLLER" or tag not in ("FP", "FINGER"):
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

      # Tandai gagal dan tutup dialog untuk diproses oleh Login
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

        # 📸 Capture Akses Berhasil
        start_access_capture(
            self,
            reason="success_fingerprint",
            save_dir=f"captures/{self.gudang}",
        )
        self.stop_scanning()
        log_login_attempt(
            self.user_nrp, "finger", 1, self.gudang, self.user_id_locker
        )
        QTimer.singleShot(2000, self.accept)
      else:
        self.lbInfoF.setText("Fingerprint not registered")
        self.lbInfoF.setStyleSheet("color: red;")
        log_login_attempt("Unknown", "finger", 0, self.gudang, self.user_id_locker)

        # Tandai gagal dan tutup dialog
        self.was_failed = True
        self.stop_scanning()
        QTimer.singleShot(1000, self.reject)
    except Exception as err:
      print(f"Error Database: {err}")

  def stop_scanning(self):
    if self.serial:
      self.serial.send_command_to("MAIN_CONTROLLER", "s")

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

  SCAN_TIMEOUT_MS = 10000  # 10 detik per percobaan
  MAX_ATTEMPTS = 3

  def __init__(self, serial_handler=None, gudang="GLOCK17"):
    super().__init__()
    loadUi("ui/auth_rfid.ui", self)
    self.setWindowModality(Qt.ApplicationModal)
    self.setWindowFlags(Qt.FramelessWindowHint)

    self.btCls_rfid.clicked.connect(self.stop_and_close)

    self.gudang = gudang
    self.user_nrp = None
    self.user_nama = None
    self.user_status = None
    self.user_id_locker = None
    self.scan_attempts = 0

    # Flag penanda kegagalan untuk ditangkap oleh Login.py
    self.was_failed = False

    self.scan_timeout_timer = QTimer(self)
    self.scan_timeout_timer.setSingleShot(True)
    self.scan_timeout_timer.timeout.connect(self.handle_scan_timeout)

    self.serial = serial_handler
    if self.serial:
      self.serial.send_command_to("MAIN_CONTROLLER", "beep")
      self.start_scan_attempt()

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

    self.serial.send_command_to("MAIN_CONTROLLER", "r")
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

      # Timeout dianggap percobaan gagal
      self.was_failed = True
      QTimer.singleShot(1000, self.reject)

  def handle_serial_data(self, role, tag, value):
    if role != "MAIN_CONTROLLER" or tag != "RFID":
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
        self.serial.send_command_to("MAIN_CONTROLLER", "beeptrue")
        start_access_capture(
            self, reason="success_rfid", save_dir=f"captures/{self.gudang}"
        )
        self.stop_scanning()
        QTimer.singleShot(2000, self.accept)
      else:
        self.lbInfoR.setText("ID Card not registered")
        self.serial.send_command_to("MAIN_CONTROLLER", "beepfail")
        self.lbInfoR.setStyleSheet("color: red;")
        log_login_attempt("Unknown", "rfid", 0, self.gudang, self.user_id_locker)

        # Kartu tidak terdaftar -> Tandai gagal
        self.was_failed = True
        self.stop_scanning()
        QTimer.singleShot(1000, self.reject)
    except Exception as err:
      print(f"Error Database: {err}")

  def stop_scanning(self):
    self.scan_timeout_timer.stop()
    if self.serial:
      self.serial.send_command_to("MAIN_CONTROLLER", "s")

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

  def __init__(self, serial_handler=None, gudang="GLOCK17"):
    super().__init__()
    loadUi("ui/auth_pin2.ui", self)
    self.setWindowModality(Qt.ApplicationModal)
    self.setWindowFlags(Qt.FramelessWindowHint)

    self.btCls_pin2.clicked.connect(self.reject)
    self.btSubmit.clicked.connect(self.checkPin)
    self.lbPin.setEchoMode(QLineEdit.Password)
    self.btSubmit.setDefault(True)

    self.gudang = gudang
    self.user_nrp = None
    self.user_nama = None
    self.user_status = None
    self.user_id_locker = None

    # Flag penanda kegagalan untuk ditangkap oleh Login.py
    self.was_failed = False

    self.serial = serial_handler
    if self.serial:
      self.serial.send_command_to("MAIN_CONTROLLER", "beep")

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
          self.serial.send_command_to("MAIN_CONTROLLER", "beeptrue")

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
          self.serial.send_command_to("MAIN_CONTROLLER", "beepfail")

        log_login_attempt(
            "Unknown", "pin", 0, self.gudang, self.user_id_locker
        )

        # PIN Salah -> Set status gagal lalu tutup dialog
        self.was_failed = True
        self.show_error_dialog("WRONG PIN!")
        self.reject()
    except Exception as err:
      print(f"Error Database: {err}")
      self.show_error_dialog("Terjadi kesalahan pada sistem.")

  def show_error_dialog(self, message="WRONG PIN!"):
    msg = DbMessage(title="Error", message=message, success=False)
    msg.exec_()
    self.lbPin.clear()

  def reset_state(self):
    self.lbPin.clear()