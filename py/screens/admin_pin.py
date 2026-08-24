from PyQt5.QtWidgets import QDialog, QLineEdit
from PyQt5.QtCore import Qt
from PyQt5.uic import loadUi
from utils import center_on_screen

class AdminPinDialog(QDialog):
    def __init__(self, parent=None, instruction="Masukkan PIN Super Admin:"):
        super().__init__()   # <-- TIDAK diteruskan parent-nya ke QDialog, hindari konflik render
        loadUi("ui2/dialogs/admin_pin.ui", self)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(Qt.ApplicationModal)   # tetap modal, mengunci layar di belakang

        self.input_pin = ""

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
            self.txtPin.setFocus()

    def showEvent(self, event):
        center_on_screen(self)
        super().showEvent(event)

    def handle_confirm(self):
        if hasattr(self, 'txtPin'):
            self.input_pin = self.txtPin.text().strip()
        self.accept()

    @staticmethod
    def get_pin(parent, instruction="Masukkan PIN Super Admin:"):
        dialog = AdminPinDialog(parent, instruction)
        result = dialog.exec_()
        return dialog.input_pin, result == QDialog.Accepted