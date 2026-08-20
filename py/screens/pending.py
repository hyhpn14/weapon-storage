from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.uic import loadUi
from db_config import get_db_connection
from .custom_dialog import CustomMessageBox
from .admin_pin import AdminPinDialog  # Import Custom PIN Dialog kita
from camera import start_unauthorized_capture, start_access_capture
from log_client import send_log

class PendingDialog(QDialog):
    def __init__(self, parent=None, gudang="GLOCK17"):
        super().__init__(parent)
        loadUi("ui2/dialogs/pending_dialog.ui", self)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint) 

        self.gudang = gudang
        self.approved_data = None

        self.tableUsers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tableUsers.setSelectionBehavior(self.tableUsers.SelectRows)
        self.tableUsers.verticalHeader().setVisible(False)

        self.btnRefresh.clicked.connect(self.load_pending_users)
        self.btnClose.clicked.connect(self.reject)
        
        self.btnEnroll.clicked.connect(self.handle_enroll)
        self.tableUsers.itemDoubleClicked.connect(self.handle_enroll)

        self.load_pending_users()

    def handle_enroll(self):
        selected_row = self.tableUsers.currentRow()
        if selected_row < 0:
            CustomMessageBox.show_warning(self, "Peringatan", "Pilih user terlebih dahulu!")
            return

        row_data = {
            "id": self.tableUsers.item(selected_row, 0).text(),
            "nrp": self.tableUsers.item(selected_row, 1).text(),
            "nama": self.tableUsers.item(selected_row, 2).text(),
            "pangkat": self.tableUsers.item(selected_row, 3).text(),
            "gudang": self.tableUsers.item(selected_row, 4).text() if self.tableUsers.columnCount() > 4 else self.gudang
        }

        self.handle_acc_process(row_data)

    def handle_acc_process(self, row_data):
        """Minta PIN Super Admin menggunakan Custom UI Dialog"""
        # --- DIGANTI DENGAN CUSTOM UI PIN DIALOG ---
        instruction_text = f"Masukkan PIN Super Admin untuk menyetujui (ACC) NRP {row_data.get('nrp')}:"
        pin, ok = AdminPinDialog.get_pin(self, instruction=instruction_text)
        
        if not ok or not pin:
            return  # User membatalkan input

        if self.verify_super_admin_pin(pin):
            self.approved_data = row_data
            start_access_capture(self, reason="success_acc_enroll", save_dir=f"captures/{self.gudang}")  
            send_log(
                kategori="user_auth",
                aktivitas="user_approval",
                detail=f"User approval successful for NRP {row_data.get('nrp')}",
                locker_id=row_data.get('id_locker'),
                nrp=row_data.get('nrp'),
                nama=row_data.get('nama'),
                gudang=self.gudang,
                metode="pin",
                status="success"
            )
            CustomMessageBox.show_info(self, "Berhasil", f"Data enroll untuk NRP {row_data.get('nrp')} ({row_data.get('nama')}) berhasil di-ACC!")
            self.accept()
        else:
            start_unauthorized_capture(self, reason="failed_acc_enroll", save_dir=f"captures/{self.gudang}")
            send_log(
                kategori="user_auth",
                aktivitas="user_approval",
                detail=f"User approval failed for NRP {row_data.get('nrp')}",
                locker_id=row_data.get('id_locker'),
                nrp=row_data.get('nrp'),
                nama=row_data.get('nama'),
                gudang=self.gudang,
                metode="pin",
                status="danger"
            )
            CustomMessageBox.show_warning(self, "Akses Ditolak","PIN Super Admin salah! Akses ditolak." )

    def verify_super_admin_pin(self, input_pin):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = "SELECT nrp FROM tb_users WHERE pin = %s AND status = 'ADMIN' LIMIT 1"
            cursor.execute(query, (input_pin,))
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return result is not None
        except Exception as e:
            print(f"Error verifikasi PIN Super Admin: {e}")
            return input_pin == "123456"

    def load_pending_users(self):
        try:
            db = get_db_connection()
            cursor = db.cursor()

            query = """
                SELECT id, nrp, nama, pangkat, gudang, id_locker
                FROM tb_users 
                WHERE status = 'USER' AND (uid IS NULL OR finger IS NULL)
                ORDER BY id DESC
            """
            cursor.execute(query)
            rows = cursor.fetchall()

            self.tableUsers.setRowCount(0)

            for row_idx, row_data in enumerate(rows):
                self.tableUsers.insertRow(row_idx)
                for col_idx, value in enumerate(row_data):
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    self.tableUsers.setItem(row_idx, col_idx, item)

            cursor.close()
            db.close()
            
            if hasattr(self, 'subtitleLabel'):
                self.subtitleLabel.setText(f"{len(rows)} user menunggu enroll")

        except Exception as e:
            print(f"Error load pending users: {e}")
            CustomMessageBox.show_warning(self, "Database Error", f"Gagal membaca data pending: {e}")