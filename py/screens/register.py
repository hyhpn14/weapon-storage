from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.uic import loadUi
from dialogs import DbMessage  # Pastikan ini diimpor dari file dialogs.py
from userScan import ScanFinger, ScanRfid, ScanPin
from db_config import get_db_connection  # Pastikan ini diimpor dari file db_config.py
from .pending import PendingDialog

GREEN_STYLE = """
    QPushButton {
        background-color: #28a745;
        border: 2px solid #1e7e34;
        color: white;
        border-radius: 15px;
        font-family: 'Inter';
        font-size : 15px;
        font-weight: bold;
        padding: 10px;
    }"""

DEFAULT_STYLE = """
    QPushButton {
        background-color: #172147;
        color: #556688;
        border: 2px solid #3d4a7d;
        border-radius: 15px;
        font-family: 'Inter';
        font-size: 15px;
        font-weight: bold;
        padding: 10px;
    }
    QPushButton:checked {
        background-color: #FFF701;
        color: #171835;
        border: 2px solid #FFF701;
    }
    QPushButton:hover {
        border: 2px solid #FFF701;
        color: white;
    }
"""

# --- HELPER UNTUK MEMILIH ARDUINO TARGET ---
def get_target_role(serial_handler, fallback="MAIN_CONTROLLER"):
    """
    Mencari role Arduino yang sedang aktif/terhubung.
    Jika ada thread terhubung, gunakan role thread tersebut.
    """
    if serial_handler and hasattr(serial_handler, 'threads'):
        for thread in serial_handler.threads:
            if getattr(thread, 'is_connected', False) and getattr(thread, 'role', 'UNKNOWN') != 'UNKNOWN':
                return thread.role
    return fallback

class Register(QMainWindow):
    go_back = pyqtSignal()
    goto_Regfinger = pyqtSignal()
    goto_Regrfid = pyqtSignal()
    goto_Regpin = pyqtSignal()
    goto_Login = pyqtSignal()  # Sinyal untuk navigasi ke layar Login

    def __init__(self, clock_helper, serial_handler=None, gudang="GLOCK17"):
        super().__init__()
        loadUi("ui2/registerr.ui", self)

        self.gudang = gudang   # Simpan untuk dipakai di semua method
        self.serial = serial_handler
        self.target_role = get_target_role(self.serial, fallback="MAIN_CONTROLLER")

        # Tempat simpan data sementara & ID pending
        self.selected_user_id = None
        self.finger_id = None
        self.rfid_uid = None
        self.pin = None

        # Bind event tombol dasar
        self.btCls_regis.clicked.connect(self.handle_close)

        if hasattr(self, 'btReset'):
            self.btReset.clicked.connect(self.reset_form)

        self.btRSFinger.clicked.connect(self.regis_finger)
        self.btRSId.clicked.connect(self.regis_rfid)
        self.btRSPin.clicked.connect(self.regis_pin)
        self.btConfirm.clicked.connect(self.confirm_registration)

        # Setup awal: Kunci seluruh form input
        self.set_form_enabled(False)

        # ============================================================
        # SETUP TIMER & POLLING DATA PENDING
        # ============================================================
        self.update_notif_pending()  # Load notif pertama kali

        self.timer_notif = QTimer(self)
        self.timer_notif.timeout.connect(self.update_notif_pending)
        self.timer_notif.start(3000)  # Cek database setiap 3 detik

        if hasattr(self, 'btNotif'):
            self.btNotif.clicked.connect(self.open_pending_dialog)

    def set_form_enabled(self, state: bool):
        """Mengunci (disable) atau membuka (enable) seluruh QLineEdit, QComboBox, dan Tombol Scan."""
        # Kunci/Buka widget QLineEdit & QComboBox
        for widget in self.findChildren((QLineEdit, QComboBox)):
            widget.setEnabled(state)

        # Kunci/Buka tombol pendaftaran biometrik
        self.btRSFinger.setEnabled(state)
        self.btRSId.setEnabled(state)
        self.btRSPin.setEnabled(state)
        self.btConfirm.setEnabled(state)

    def open_pending_dialog(self):
        """Membuka dialog pending users dan mengisikan form HANYA jika di-ACC oleh Super Admin"""
        dialog = PendingDialog(self, gudang=self.gudang)
        if dialog.exec_() == QDialog.Accepted and dialog.approved_data:
            data = dialog.approved_data
            
            # 1. Buka kuncian form terlebih dahulu
            self.set_form_enabled(True)

            # 2. Simpan ID data pending yang dipilih
            self.selected_user_id = data.get("id")

            # 3. Isi form registrasi utama secara otomatis
            if hasattr(self, 'lbName'): self.lbName.setText(str(data.get("nama", "")))
            if hasattr(self, 'lbTitle'): self.lbTitle.setText(str(data.get("pangkat", "")))
            if hasattr(self, 'lbNRP'): self.lbNRP.setText(str(data.get("nrp", "")))
            
            # Update counter notifikasi setelah dialog ditutup
            self.update_notif_pending()

    # ============================================================
    # CEK DATABASE & UPDATE TEXT BUTTON NOTIFIKASI
    # ============================================================
    def get_pending_user(self):
        """Membaca jumlah user yang uid atau finger-nya masih NULL"""
        try:
            db = get_db_connection()
            cursor = db.cursor()
            
            query = "SELECT COUNT(*) FROM tb_users WHERE status = 'USER' AND (uid IS NULL OR finger IS NULL)"
            cursor.execute(query)
            result = cursor.fetchone()
            
            cursor.close()
            db.close()
            
            return result[0] if result else 0
        except Exception as e:
            print("Error get_pending_user:", e)
            return 0

    def update_notif_pending(self):
        """Update teks pada btNotif dan lb_Notif"""
        count = self.get_pending_user()
        
        if hasattr(self, 'btNotif'):
            self.btNotif.setText(str(count))

        if hasattr(self, 'lb_Notif'):
            self.lb_Notif.setText(str(count))

    def get_nrp_value(self):
        """Helper untuk mengambil text NRP baik dari QLineEdit maupun QLabel"""
        if hasattr(self, 'lbNRP'):
            return self.lbNRP.text() if hasattr(self.lbNRP, 'text') else self.lbNRP.toPlainText()
        return ""

    def regis_finger(self):
        nrp = self.get_nrp_value()
        if not nrp:
            self.show_message("Peringatan", "Pilih data user di tombol Pending terlebih dahulu!", success=False)
            return

        self.get_next_finger_id() 

        if self.serial:
            self.serial.send_command_to(self.target_role, 'e')
            print(f"{self.target_role}e{self.next_id}")

        dialog = ScanFinger(nrp=nrp, serial_handler=self.serial, finger_id=self.next_id)
        if dialog.exec_() == QDialog.Accepted:
            self.finger_id = self.next_id
            self.btRSFinger.setStyleSheet(GREEN_STYLE)
            self.btRSFinger.setEnabled(False)

    def regis_rfid(self):
        nrp = self.get_nrp_value()
        if not nrp:
            self.show_message("Peringatan", "Pilih data user di tombol Pending terlebih dahulu!", success=False)
            return

        if self.serial:
            self.serial.send_command_to(self.target_role, 'r')
            print("r")

        dialog = ScanRfid(nrp=nrp, serial_handler=self.serial)
        if dialog.exec_() == QDialog.Accepted:
            self.rfid_uid = dialog.current_uid
            self.btRSId.setStyleSheet(GREEN_STYLE)
            self.btRSId.setEnabled(False)

    def regis_pin(self):
        nrp = self.get_nrp_value()
        if not nrp:
            self.show_message("Peringatan", "Pilih data user di tombol Pending terlebih dahulu!", success=False)
            return
            
        dialog = ScanPin(nrp=nrp)
        if dialog.exec_() == QDialog.Accepted:
            self.pin = dialog.pin
            self.btRSPin.setStyleSheet(GREEN_STYLE)
            self.btRSPin.setEnabled(False)

    def get_next_finger_id(self):
        try:
            db = get_db_connection()
            cursor = db.cursor()
            cursor.execute("SELECT MAX(finger) FROM tb_users WHERE gudang = %s", (self.gudang,))
            result = cursor.fetchone()[0]
            self.next_id = (result + 1) if result else 1
            db.close()
        except Exception as e:
            print(f"Error get_next_finger_id: {e}") 
            self.next_id = 1

    def confirm_registration(self):
        nama = self.lbName.text() if hasattr(self.lbName, 'text') else ""
        nrp = self.get_nrp_value()
        pangkat = self.lbTitle.text() if hasattr(self.lbTitle, 'text') else ""
        status = self.cbState.currentText() if hasattr(self, 'cbState') else "USER"

        if not all([nama, pangkat, nrp]):
            self.show_message("Warning", "Data user belum terisi secara lengkap.", success=False)
            return

        if self.finger_id is None or self.rfid_uid is None or self.pin is None:
            self.show_message("Warning", "Silakan selesaikan scan Fingerprint, RFID, dan PIN terlebih dahulu.", success=False)
            return

        try:
            db = get_db_connection()
            cursor = db.cursor()

            # Lakukan UPDATE pada baris data pending yang sedang di-enroll
            query = """
                UPDATE tb_users 
                SET nama = %s, status = %s, pangkat = %s, finger = %s, uid = %s, pin = %s, gudang = %s
                WHERE nrp = %s OR id = %s
            """
            cursor.execute(query, (nama, status, pangkat, self.finger_id, self.rfid_uid, self.pin, self.gudang, nrp, self.selected_user_id))
            db.commit()
            db.close()

            self.show_message("Success", f"Registrasi untuk {nama} berhasil diperbarui!", success=True)
            self.reset_form()
            self.go_back.emit()

        except Exception as e:
            self.show_message("Database Error", str(e), success=False)

    def show_message(self, title, message, success=True):
        msg = DbMessage(self, title=title, message=message, success=success)
        msg.exec_()

    def handle_close(self):
        self.reset_form()
        self.go_back.emit()
        
    def reset_form(self):
        """Reset semua input, kunci form kembali, dan kembalikan status tombol registrasi"""
        # Clear Text Field
        if hasattr(self, 'lbName'): self.lbName.clear()
        if hasattr(self, 'lbTitle'): self.lbTitle.clear()
        if hasattr(self, 'lbNRP'): self.lbNRP.clear()
        
        # Reset ComboBox
        if hasattr(self, 'cbState'): self.cbState.setCurrentIndex(0)
        if hasattr(self, 'cbStorage'): self.cbStorage.setCurrentIndex(0)

        # Reset Variable State
        self.selected_user_id = None
        self.finger_id = None
        self.rfid_uid = None
        self.pin = None

        # Reset tombol biometrik ke gaya default
        self.btRSFinger.setStyleSheet(DEFAULT_STYLE)
        self.btRSId.setStyleSheet(DEFAULT_STYLE)
        self.btRSPin.setStyleSheet(DEFAULT_STYLE)

        # KUNCI KEMBALI FORM REGISTER (Baru terbuka jika select enroll di-ACC)
        self.set_form_enabled(False)

        print("🔒 Form registrasi telah dibersihkan dan dikunci kembali.")