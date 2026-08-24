from authScan import AuthFinger, AuthPin, AuthRFID
from camera import start_access_capture
from notifier import trigger_security_alert
from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import *
from PyQt5.uic import loadUi

from .custom_dialog import CustomMessageBox


class Login(QMainWindow):
  go_back = pyqtSignal()
  goto_finger = pyqtSignal()
  goto_rfid = pyqtSignal()
  goto_pin = pyqtSignal()
  goto_register = pyqtSignal()  # Sinyal navigasi ke layar Register
  login_success = pyqtSignal(
      str, str, str, str
  )  # Sinyal navigasi ke layar Home (nrp, nama, id_locker, status)

  def __init__(self, clock_helper, serial_handler=None, gudang="GLOCK17"):
    super().__init__()
    loadUi("ui2/loginn.ui", self)

    self.gudang = gudang
    self.serial_handler = serial_handler

    # Reference dialog autentikasi yang sedang aktif
    self.active_auth_dialog = None

    # --- LOGIKA SANKSI / LOCKOUT (GLOBAL 3X FAIL) ---
    self.global_failed_attempts = 0
    self.MAX_FAILED_ATTEMPTS = 3

    self.lock_timer = QTimer(self)
    self.lock_timer.timeout.connect(self.update_lock_countdown)
    self.remaining_seconds = 60  # Durasi hukuman: 1 Menit (60 Detik)

    # --- BINDING TOMBOL ---
    self.btCls_login.clicked.connect(self.handle_close)
    self.btFinger.clicked.connect(self.open_auth_finger)
    self.btRfid.clicked.connect(self.open_auth_rfid)
    self.btPin.clicked.connect(self.open_auth_pin)
    self.btRegis.clicked.connect(self.goto_register.emit)

  def handle_serial_data(self, role, tag, value):
    """Pintu masuk data serial untuk layar Login."""
    if self.active_auth_dialog and hasattr(
        self.active_auth_dialog, "handle_serial_data"
    ):
      self.active_auth_dialog.handle_serial_data(role, tag, value)

  def reset_all_auth_data(self):
    """Mereset seluruh dialog autentikasi dan buffer input."""
    print("🔄 Memulai reset seluruh dialog & data authentikasi...")

    if self.active_auth_dialog:
      try:
        if hasattr(self.active_auth_dialog, "stop_scanning"):
          self.active_auth_dialog.stop_scanning()
        if hasattr(self.active_auth_dialog, "reset_data"):
          self.active_auth_dialog.reset_data()
        self.active_auth_dialog.reject()
      except Exception as e:
        print(f"Error saat menutup dialog aktif: {e}")
      finally:
        self.active_auth_dialog = None

    if hasattr(self, "temp_nrp"):
      self.temp_nrp = None
    if hasattr(self, "temp_nama"):
      self.temp_nama = None

    if self.serial_handler:
      try:
        self.serial_handler.send_command_to(
            "MAIN_CONTROLLER", "CMD:CANCEL_AUTH\n"
        )
      except Exception as e:
        print(f"Gagal mengirim command cancel ke Serial: {e}")

    print("✅ Seluruh data autentikasi berhasil direset.")

  def handle_close(self):
    """Callback saat tombol btCls_login diklik."""
    self.reset_all_auth_data()
    self.go_back.emit()

  # --- LOGIKA SANKSI AKUMULASI GAGAL & COUNTDOWN TIMER ---

  def handle_failed_attempt(self, auth_type="unknown"):
    """Dipanggil setiap kali ada kegagalan dari salah satu dialog (Finger, RFID, PIN)."""
    self.global_failed_attempts += 1
    print(
        f"⚠️ Total Percobaan Gagal:"
        f" {self.global_failed_attempts}/{self.MAX_FAILED_ATTEMPTS}"
    )

    if self.global_failed_attempts >= self.MAX_FAILED_ATTEMPTS:
      self.lock_all_auth_buttons(auth_type)
    else:
      sisa = self.MAX_FAILED_ATTEMPTS - self.global_failed_attempts
      CustomMessageBox.show_warning(
          self,
          "Akses Ditolak",
          f"Verifikasi {auth_type.upper()} gagal!\nSisa kesempatan mencoba:"
          f" {sisa} kali.",
      )

  def lock_all_auth_buttons(self, last_auth_type):
    """Disable semua tombol login dan mulai countdown 1 menit."""
    self.global_failed_attempts = 0  # Reset akumulasi kegagalan
    self.remaining_seconds = 60  # Reset waktu ke 1 Menit

    # Disable Seluruh Tombol Utama
    self.btFinger.setEnabled(False)
    self.btRfid.setEnabled(False)
    self.btPin.setEnabled(False)

    # 🚨 Pemicu Keamanan & Capture
    try:
      start_access_capture(
          self,
          reason=f"3x_wrong_{last_auth_type}",
          save_dir=f"captures/{self.gudang}",
      )
      trigger_security_alert(self.gudang, last_auth_type, "3x_failed_attempt")
    except Exception as e:
      print(f"Error trigger security alert: {e}")

    # Tampilkan Peringatan Penguncian
    CustomMessageBox.show_warning(
        self,
        "Sistem Terkunci",
        "Akses ditolak 3 kali berturut-turut!\nSeluruh tombol verifikasi"
        " dibekukan selama 1 menit.",
    )

    # Jalankan timer hitung mundur
    self.lock_timer.start(1000)
    self.update_lock_countdown()

  def update_lock_countdown(self):
    """Update tampilan UI tiap detik selama terkunci."""
    mins, secs = divmod(self.remaining_seconds, 60)
    time_str = f"Terkunci ({mins:02d}:{secs:02d})"

    if hasattr(self, "lbStatus"):
      self.lbStatus.setText(
          f"Sistem Terkunci. Silakan tunggu {self.remaining_seconds} detik."
      )
      self.lbStatus.setStyleSheet("color: red; font-weight: bold;")

    # Ubah label tombol sementara saat terkunci
    self.btFinger.setText(f"Locked ({secs}s)")
    self.btRfid.setText(f"Locked ({secs}s)")
    self.btPin.setText(f"Locked ({secs}s)")

    if self.remaining_seconds <= 0:
      self.unlock_all_auth_buttons()
    else:
      self.remaining_seconds -= 1

  def unlock_all_auth_buttons(self):
    """Mengaktifkan kembali tombol login setelah waktu hukuman selesai."""
    self.lock_timer.stop()

    # Enable kembali semua tombol
    self.btFinger.setEnabled(True)
    self.btRfid.setEnabled(True)
    self.btPin.setEnabled(True)

    # Kembalikan teks asli pada tombol
    self.btFinger.setText("Fingerprint")
    self.btRfid.setText("RFID Card")
    self.btPin.setText("PIN")

    if hasattr(self, "lbStatus"):
      self.lbStatus.setText("Silakan pilih metode autentikasi")
      self.lbStatus.setStyleSheet("color: black;")

    CustomMessageBox.show_info(
        self, "Sistem Aktif", "Masa penguncian selesai. Silakan mencoba kembali."
    )
    print(
        "🔓 Kunci 1 menit berakhir. Seluruh tombol autentikasi kembali aktif."
    )

  # --- PENANGANAN PROSES AUTENTIKASI ---

  def open_auth_finger(self):
    self.reset_all_auth_data()

    self.active_auth_dialog = AuthFinger(parent=self.window(),
        serial_handler=self.serial_handler, gudang=self.gudang
    )
    res = self.active_auth_dialog.exec_()

    if res == QDialog.Accepted:
      self.global_failed_attempts = 0
      self.login_success.emit(
          self.active_auth_dialog.user_nrp,
          self.active_auth_dialog.user_nama,
          self.active_auth_dialog.user_id_locker,
          self.active_auth_dialog.user_status,
      )
    else:
      if getattr(self.active_auth_dialog, "was_failed", False):
        self.handle_failed_attempt(auth_type="finger")

    self.active_auth_dialog = None

  def open_auth_rfid(self):
    self.reset_all_auth_data()

    self.active_auth_dialog = AuthRFID( parent=self.window(),
        serial_handler=self.serial_handler, gudang=self.gudang
    )
    res = self.active_auth_dialog.exec_()

    if res == QDialog.Accepted:
      self.global_failed_attempts = 0
      self.login_success.emit(
          self.active_auth_dialog.user_nrp,
          self.active_auth_dialog.user_nama,
          self.active_auth_dialog.user_id_locker,
          self.active_auth_dialog.user_status,
      )
    else:
      if getattr(self.active_auth_dialog, "was_failed", False):
        self.handle_failed_attempt(auth_type="rfid")

    self.active_auth_dialog = None

  def open_auth_pin(self):
    self.reset_all_auth_data()

    self.active_auth_dialog = AuthPin(parent=self.window(),
        serial_handler=self.serial_handler, gudang=self.gudang
    )
    res = self.active_auth_dialog.exec_()

    if res == QDialog.Accepted:
      self.global_failed_attempts = 0
      self.login_success.emit(
          self.active_auth_dialog.user_nrp,
          self.active_auth_dialog.user_nama,
          self.active_auth_dialog.user_id_locker,
          self.active_auth_dialog.user_status,
      )
    else:
      if getattr(self.active_auth_dialog, "was_failed", False):
        self.handle_failed_attempt(auth_type="pin")

    self.active_auth_dialog = None