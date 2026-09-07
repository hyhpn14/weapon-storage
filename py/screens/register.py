import subprocess
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.uic import loadUi
from dialogs import DbMessage  # Pastikan ini diimpor dari file dialogs.py
from userScan import ScanFinger, ScanRfid, ScanPin
from db_config import get_db_connection  # Pastikan ini diimpor dari file db_config.py
from .pending import PendingDialog
from .custom_dialog import CustomMessageBox  # Pastikan ini diimpor dari file custom_dialog.py

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

class Register(QMainWindow):
    go_back = pyqtSignal()
    goto_Regfinger = pyqtSignal()
    goto_Regrfid = pyqtSignal()
    goto_Regpin = pyqtSignal()
    goto_Login = pyqtSignal()  # Sinyal untuk navigasi ke layar Login

    def __init__(self, clock_helper, serial_handler=None, gudang="GLOCK17"):
        super().__init__()
        loadUi("ui2/registerr.ui", self)

        combo_style = """
            QListView {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #FFF701;
                outline: 0;
            }
            QListView::item {
                min-height: 28px;
                padding: 6px 12px;
            }
            QListView::item:selected {
                background-color: #0248c1;
                color: #ffffff;
            }
            QListView::item:hover {
                background-color: #0248c1;
                color: #ffffff;
            }
        """
        combo_focus_style = """
        QComboBox {
            combobox-popup: 0;
            background-color: #000000;
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            padding: 8px 12px;
            color: #ffffff;
            font-family: Inter;
            font-size: 13px;
            min-height: 32px;
        }
        QComboBox:focus, QComboBox:on {
            border: 2px solid #FFF701;
        }
        """

        for combo in (self.cbState, self.cbStorage):
            combo.setStyleSheet(combo_focus_style)
            combo.view().setFrameShape(QFrame.NoFrame)
            combo.view().setStyleSheet(combo_style)  # yang sudah ada sebelumnyaombo.view().setStyleSheet(combo_style)

        self.gudang = gudang   # Simpan untuk dipakai di semua method
        self.serial = serial_handler

        if self.serial and hasattr(self.serial, 'get_main_role_for_gudang'):
            self.target_role = self.serial.get_main_role_for_gudang()
        else:
            self.target_role = "MAIN_CONTROLLER"

        # Referensi dialog scan yang sedang aktif (sama seperti Login.active_auth_dialog)
        self.active_scan_dialog = None

        # Tempat simpan data sementara & ID pending
        self.selected_user_id = None
        self.finger_id = None
        self.rfid_uid = None
        self.pin = None

        self.keyboard_process = None

        # Bind event tombol dasar
        self.btCls_regis.clicked.connect(self.handle_close)

        if hasattr(self, 'btReset'):
            self.btReset.clicked.connect(self.reset_form)

        self.btRSFinger.clicked.connect(self.regis_finger)
        self.btRSId.clicked.connect(self.regis_rfid)
        self.btRSPin.clicked.connect(self.regis_pin)
        self.btConfirm.clicked.connect(self.confirm_registration)

        # Pass event filter ke semua QLineEdit yang butuh virtual keyboard
        self.lbLoker.installEventFilter(self)
        self.lbName.installEventFilter(self)
        self.lbTitle.installEventFilter(self)
        self.lbNRP.installEventFilter(self)

        # Setup awal: Kunci seluruh form input
        self.set_form_enabled(False)

    
        # SETUP TIMER & POLLING DATA PENDING      
        self.update_notif_pending()  # Load notif pertama kali

        self.timer_notif = QTimer(self)
        self.timer_notif.timeout.connect(self.update_notif_pending)
        self.timer_notif.start(3000)  # Cek database setiap 3 detik

        if hasattr(self, 'btNotif'):
            self.btNotif.clicked.connect(self.open_pending_dialog)

    def eventFilter(self, obj, event):
        # Deteksi saat QLineEdit mendapatkan fokus input
        if event.type() == QEvent.FocusIn:
            if obj in (self.lbLoker, self.lbName, self.lbTitle, self.lbNRP):
                self.open_default_keyboard()
                # Kembalikan fokus ke window utama agar OS tidak 'stuck'
                QTimer.singleShot(100, self.force_to_front)
        return super().eventFilter(obj, event)

    def force_to_front(self):
        self.raise_()
        self.activateWindow()

    def open_default_keyboard(self):
        """Membuka wvkbd persis seperti di AdminPinDialog"""
        try:
            if (
                self.keyboard_process is None
                or self.keyboard_process.poll() is not None
            ):
                self.keyboard_process = subprocess.Popen(["wvkbd-mobintl", "-H", "380"])
        except Exception:
            try:
                self.keyboard_process = subprocess.Popen(["wvkbd", "-H", "380"])
            except Exception as e:
                print(f"Gagal membuka wvkbd: {e}")

    def close_virtual_keyboard(self):
        """Menutup proses wvkbd"""
        try:
            subprocess.Popen(["killall", "wvkbd-mobintl", "wvkbd"])
            self.keyboard_process = None
        except Exception as e:
            print(f"Gagal menutup keyboard: {e}")

    def closeEvent(self, event):
        # Tutup keyboard saat halaman Register ditutup atau kembali
        self.close_virtual_keyboard()
        super().closeEvent(event)

    def handle_serial_data(self, role, tag, value):
        if self.active_scan_dialog and hasattr(self.active_scan_dialog, "handle_serial_data"):
            self.active_scan_dialog.handle_serial_data(role, tag, value)

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
        if hasattr(self, 'timer_notif'):
            self.timer_notif.stop()

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
            if hasattr(self, 'timer_notif'):
                self.timer_notif.start(3000)

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

    def regis_rfid(self):
        nrp = self.get_nrp_value()
        if not nrp:
            self.show_message("Peringatan", "Pilih data user di tombol Pending terlebih dahulu!", success=False)
            return

        # Command 'r' juga tidak dikirim manual di sini lagi — ScanRfid.__init__
        # sudah mengirimnya sendiri, jadi tidak perlu dikirim dua kali.

        self.active_scan_dialog = ScanRfid(
            parent=self,
            nrp=nrp,
            serial_handler=self.serial,
        )
        res = self.active_scan_dialog.exec_()

        if res == QDialog.Accepted:
            self.rfid_uid = self.active_scan_dialog.current_uid
            self.btRSId.setStyleSheet(GREEN_STYLE)
            self.btRSId.setEnabled(False)

        self.active_scan_dialog = None

    def regis_finger(self):
        nrp = self.get_nrp_value()
        if not nrp:
            self.show_message("Peringatan", "Pilih data user di tombol Pending terlebih dahulu!", success=False)
            return

        self.get_next_finger_id()

        # Command 'e{id}' TIDAK dikirim manual di sini lagi — ScanFinger.__init__
        # sudah mengirimnya sendiri dengan format yang benar (f"e{self.target_id}").
        # Baris send_command_to('e') tanpa ID sebelumnya dihapus karena
        # ditolak firmware (arg kosong -> toInt() = 0 -> invalid ID).

        self.active_scan_dialog = ScanFinger(
            parent=self,
            nrp=nrp,
            serial_handler=self.serial,
            finger_id=self.next_id,
            gudang=self.gudang,
        )
        res = self.active_scan_dialog.exec_()

        if res == QDialog.Accepted:
            self.finger_id = self.next_id
            self.btRSFinger.setStyleSheet(GREEN_STYLE)
            self.btRSFinger.setEnabled(False)

        self.active_scan_dialog = None

    def regis_pin(self):
        nrp = self.get_nrp_value()
        if not nrp:
            self.show_message("Peringatan", "Pilih data user di tombol Pending terlebih dahulu!", success=False)
            return
            
        dialog = ScanPin(parent=self, nrp=nrp)
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
        CustomMessageBox.show_info(self, title, message) if success else CustomMessageBox.show_warning(self, title, message)    
        # msg = DbMessage(self, title=title, message=message, success=success)
        # msg.exec_()

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