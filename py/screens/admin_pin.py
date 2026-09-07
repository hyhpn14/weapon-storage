import subprocess
from PyQt5.QtWidgets import QDialog, QLineEdit 
from PyQt5.QtCore import Qt, QEvent, QTimer
from PyQt5.uic import loadUi
from utils import center_on_screen

class AdminPinDialog(QDialog):
    def __init__(self, parent=None, instruction="Masukkan PIN Super Admin:"):
        super().__init__(parent)
        loadUi("ui2/dialogs/admin_pin.ui", self)
        
        self._custom_parent = parent

        # Gunakan Qt.Window agar berdiri sebagai window paling atas di Wayland/X11
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        # ApplicationModal otomatis MEMBEKUKAN PendingDialog & Register di belakangnya
        self.setWindowModality(Qt.ApplicationModal)       

        self.input_pin = ""
        self.keyboard_process = None

        # --- TAMBAHKAN INI: timer anti-tenggelam ---
        self._stay_on_top_timer = QTimer(self)
        self._stay_on_top_timer.timeout.connect(self._enforce_on_top)
        # 150-250ms cukup responsif tanpa membebani CPU RPi

        if hasattr(self, 'lbInstruction'):
            self.lbInstruction.setText(instruction)

        if hasattr(self, 'btnConfirm'):
            self.btnConfirm.clicked.connect(self.handle_confirm)
        if hasattr(self, 'btnCancel'):
            self.btnCancel.clicked.connect(self.reject)
        if hasattr(self, 'btn_close'):
            self.btn_close.clicked.connect(self.reject)

        if hasattr(self, 'txtPin'):
            self.txtPin.returnPressed.connect(self.handle_confirm)
            self.txtPin.installEventFilter(self)

    def force_to_front(self):
        """Memaksa dialog naik ke paling depan dan mengambil fokus input."""
        self.raise_()
        self.activateWindow()
        if hasattr(self, 'txtPin'):
            self.txtPin.setFocus()

    def center_dialog(self):
        if self._custom_parent and hasattr(self._custom_parent, 'geometry'):
            parent_rect = self._custom_parent.geometry()
            geo = self.geometry()
            x = parent_rect.x() + (parent_rect.width() - geo.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - geo.height()) // 2
            self.move(x, y)
        else:
            center_on_screen(self)

    def _enforce_on_top(self):
        """Dipanggil berkala untuk memaksa dialog ini tetap di depan,
        menutup celah saat WM menaikkan window lain akibat sentuhan tak sengaja."""
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        self.center_dialog()
        # Beri jeda 50ms agar OS selesai menggambar dialog sebelum dipaksa ke paling depan
        QTimer.singleShot(50, self.force_to_front)
        self._stay_on_top_timer.start(200)  # Mulai timer anti-tenggelam

    def eventFilter(self, obj, event):
        if hasattr(self, 'txtPin') and obj == self.txtPin and event.type() == QEvent.FocusIn:
            self.open_default_keyboard()
            # Jeda 100ms agar dialog tidak tertutup saat wvkbd mencuri fokus OS
            QTimer.singleShot(100, self.force_to_front)
        return super().eventFilter(obj, event)

    def open_default_keyboard(self):
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
        try:
            subprocess.Popen(["killall", "wvkbd-mobintl", "wvkbd"])
            self.keyboard_process = None
        except Exception as e:
            print(f"Gagal menutup keyboard: {e}")

    def closeEvent(self, event):
        self._stay_on_top_timer.stop()
        self.close_virtual_keyboard()
        super().closeEvent(event)

    def reject(self):
        self._stay_on_top_timer.stop()
        self.close_virtual_keyboard()
        super().reject()

    def accept(self):
        self._stay_on_top_timer.stop()
        self.close_virtual_keyboard()
        super().accept()

    def handle_confirm(self):
        if hasattr(self, 'txtPin'):
            self.input_pin = self.txtPin.text().strip()
        self.accept()

    @staticmethod
    def get_pin(parent=None, instruction="Masukkan PIN Super Admin:"):
        dialog = AdminPinDialog(parent, instruction)
        result = dialog.exec_()
        return dialog.input_pin, result == QDialog.Accepted