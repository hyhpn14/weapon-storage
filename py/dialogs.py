from PyQt5.QtWidgets import QDialog
from PyQt5.uic import loadUi
from PyQt5.QtCore import Qt
from utils import center_on_screen 


class DbMessage(QDialog):
    def __init__(self, parent=None, title=None, message=None, success=True):
        super().__init__(parent)
        ui_file = "db_success.ui" if success else "db_fail.ui"
        loadUi(f"ui/{ui_file}", self)
          

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint) 
        self.setAttribute(Qt.WA_TranslucentBackground)

        if title:
            self.label_3.setText(title)
        if message:
            self.label_2.setText(message)

        self.pushButton.clicked.connect(self.accept)

    def showEvent(self, event):
        center_on_screen(self)
        super().showEvent(event)