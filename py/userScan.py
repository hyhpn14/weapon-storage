import mysql.connector
from dialogs import DbMessage
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.uic import loadUi
from serial_handler import SerialHandler

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

  def __init__(self, nrp, serial_handler=None, finger_id=None):
    super().__init__()
    loadUi("ui2/dialogs/enroll_finger.ui", self)
    self.setWindowModality(Qt.ApplicationModal)
    self.setWindowFlags(Qt.FramelessWindowHint)

    self.nrp = nrp
    self.target_id = finger_id
    self.scan_count = 0
    self.enroll_success = False

    self.serial = serial_handler

    if hasattr(self, "lbNrpRF"):
      self.lbNrpRF.setText(f"{nrp}")

    if hasattr(self, "lbFingerR") and self.target_id is not None:
      self.lbFingerR.setText(str(self.target_id))

    self.start_pulsing_animation()
    self.btn_close.clicked.connect(self.reject)
    self.buttonBox.accepted.connect(self.save_data)
    self.buttonBox.rejected.connect(self.reset_form)

    # Trigger pendaftaran ke Arduino Utama jika diperlukan
    if self.serial and self.target_id is not None:
      self.serial.send_command_to(
          "MAIN_CONTROLLER", f"e{self.target_id}"
      )  # 'e' + ID untuk Enroll

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
    """Handler otomatis dipanggil oleh Router Centralized MainApp."""
    if role != "MAIN_CONTROLLER":
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
    self.accept()

  def reset_form(self):
    if self.serial and self.target_id is not None:
      # Kirim command delete/reset ID ke Main Controller
      self.serial.send_command_to(
          "MAIN_CONTROLLER", "d", str(self.target_id)
      )
    self.scan_count = 0
    self.enroll_success = False
    self.lbInfoF.setText("Please Scan Finger Again...")
    self.lbIconF.setStyleSheet("background-color: transparent;")
    self.start_pulsing_animation()

  def closeEvent(self, event):
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

    if hasattr(self, "lbNrpRC"):
      self.lbNrpRC.setText(f"{nrp}")

    self.start_pulsing_animation()
    self.btn_close.clicked.connect(self.reject)
    self.buttonBox.accepted.connect(self.save_data)
    self.buttonBox.rejected.connect(self.reset_form)

    # Perintahkan Main Controller untuk standby membaca RFID
    if self.serial:
      self.serial.send_command_to("MAIN_CONTROLLER", "r")

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
    """Handler otomatis dipanggil oleh Router Centralized MainApp."""
    if role == "MAIN_CONTROLLER" and tag == "RFID":
      uid = value.strip().replace(" ", "")
      self.process_rfid_input(uid)

  def process_rfid_input(self, uid):
    self.current_uid = uid
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
    self.accept()

  def reset_form(self):
    self.current_uid = None
    self.lbInfoR.setText("Silakan tempel kartu RFID...")
    self.lbIconR.setStyleSheet("background-color: transparent;")
    self.start_pulsing_animation()

  def closeEvent(self, event):
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