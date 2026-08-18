from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog
from PyQt5.uic import loadUi
from utils import center_on_screen


class CustomMessageBox(QDialog):
  # Enum / Konstanta Tipe Pesan
  INFO = "INFO"
  WARNING = "WARNING"
  CONFIRM = "CONFIRM"

  def __init__(self, parent=None, title="Pemberitahuan", message="", msg_type=INFO):
    super().__init__()  # Tanpa parent untuk menghindari issue render/clipping
    loadUi("ui2/dialogs/custom_msg.ui", self)

    self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
    self.setAttribute(Qt.WA_TranslucentBackground)
    self.setWindowModality(Qt.ApplicationModal)

    # Set Teks
    if hasattr(self, "lbTitle"):
      self.lbTitle.setText(title)
    if hasattr(self, "lbMessage"):
      self.lbMessage.setText(message)

    # Binding Tombol Dialog & Close Button (X)
    if hasattr(self, "btnOk"):
      self.btnOk.clicked.connect(self.accept)
    if hasattr(self, "btnCancel"):
      self.btnCancel.clicked.connect(self.reject)
    if hasattr(self, "btn_close"):
      self.btn_close.clicked.connect(self.reject)

    # Konfigurasi Tampilan Berdasarkan Tipe
    self.setup_type(msg_type)

  def showEvent(self, event):
    center_on_screen(self)
    super().showEvent(event)

  def setup_type(self, msg_type):
    if msg_type == self.INFO:
      if hasattr(self, "btnCancel"):
        self.btnCancel.hide()
      if hasattr(self, "btnOk"):
        self.btnOk.setText("OK")
      if hasattr(self, "lbIcon"):
        self.lbIcon.setPixmap(QPixmap("assets/icon/critical.svg"))

    elif msg_type == self.WARNING:
      if hasattr(self, "btnCancel"):
        self.btnCancel.hide()
      if hasattr(self, "btnOk"):
        self.btnOk.setText("OK")
      if hasattr(self, "lbIcon"):
        self.lbIcon.setPixmap(
            QPixmap("assets/icon/triangle-exclamation-solid-full.svg")
        )

    elif msg_type == self.CONFIRM:
      if hasattr(self, "btnCancel"):
        self.btnCancel.show()
      if hasattr(self, "btnOk"):
        self.btnOk.setText("Ya / Setuju")
      if hasattr(self, "btnCancel"):
        self.btnCancel.setText("Batal")
      if hasattr(self, "lbIcon"):
        self.lbIcon.setPixmap(QPixmap("ui2/assets/icon_question.png"))

  # --- HELPER STATIC METHODS ---

  @staticmethod
  def show_info(parent, title, message):
    dialog = CustomMessageBox(
        parent, title, message, msg_type=CustomMessageBox.INFO
    )
    return dialog.exec_()

  @staticmethod
  def show_warning(parent, title, message):
    dialog = CustomMessageBox(
        parent, title, message, msg_type=CustomMessageBox.WARNING
    )
    return dialog.exec_()

  @staticmethod
  def show_confirm(parent, title, message):
    """Mengembalikan True jika user klik 'Ya', dan False jika 'Batal'."""
    dialog = CustomMessageBox(
        parent, title, message, msg_type=CustomMessageBox.CONFIRM
    )
    return dialog.exec_() == QDialog.Accepted