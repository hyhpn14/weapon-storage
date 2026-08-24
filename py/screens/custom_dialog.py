from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QWidget
from PyQt5.uic import loadUi


class CustomMessageBox(QDialog):
  INFO = "INFO"
  WARNING = "WARNING"
  CONFIRM = "CONFIRM"

  def __init__(
      self, parent=None, title="Pemberitahuan", message="", msg_type=INFO
  ):
    # Pass parent wajib ada
    super().__init__(parent)
    loadUi("ui2/dialogs/custom_msg.ui", self)

    # BUAT SEBAGAI WIDGET EMBEDDED (TANPA WINDOW OS BARU)
    if parent:
      self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
    else:
      self.setWindowFlags(
          Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
      )

    self.setAttribute(Qt.WA_TranslucentBackground)

    # Set Teks
    if hasattr(self, "lbTitle"):
      self.lbTitle.setText(title)
    if hasattr(self, "lbMessage"):
      self.lbMessage.setText(message)

    # Binding Tombol (Gunakan close/accept/reject biasa)
    if hasattr(self, "btnOk"):
      self.btnOk.clicked.connect(self.accept)
    if hasattr(self, "btnCancel"):
      self.btnCancel.clicked.connect(self.reject)
    if hasattr(self, "btn_close"):
      self.btn_close.clicked.connect(self.reject)

    self.setup_type(msg_type)

  def showEvent(self, event):
    super().showEvent(event)
    self.resize_and_center()
    self.raise_()

  def resize_and_center(self):
    """Menempatkan dialog tepat di tengah-tengah parent widget."""
    if self.parent():
      parent_rect = self.parent().rect()
      self.adjustSize()  # Sesuaikan ukuran UI
      geo = self.geometry()

      # Hitung koordinat lokal di dalam AuthPin
      x = (parent_rect.width() - geo.width()) // 2
      y = (parent_rect.height() - geo.height()) // 2
      self.move(x, y)

  def setup_type(self, msg_type):
    if msg_type == self.INFO:
      if hasattr(self, "btnCancel"):
        self.btnCancel.hide()
      if hasattr(self, "btnOk"):
        self.btnOk.setText("OK")
      if hasattr(self, "lbIcon"):
        self.lbIcon.setPixmap(QPixmap("assets/icon/critical.svg"))
        self.lbIcon.setStyleSheet(
            "background-color: #ffc107; border-radius: 25px;"
        )

    elif msg_type == self.WARNING:
      if hasattr(self, "btnCancel"):
        self.btnCancel.hide()
      if hasattr(self, "btnOk"):
        self.btnOk.setText("OK")
      if hasattr(self, "lbIcon"):
        self.lbIcon.setPixmap(
            QPixmap("assets/icon/triangle-exclamation-solid-full.svg")
        )
        self.lbIcon.setStyleSheet(
            "background-color: #dc3545; border-radius: 25px;"
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
        self.lbIcon.setStyleSheet(
            "background-color: #0d6efd; border-radius: 25px;"
        )
  # --- HELPER STATIC METHODS ---

  @staticmethod
  def _show_overlay(parent, title, message, msg_type):
    dialog = CustomMessageBox(
        parent, title, message, msg_type=msg_type
    )

    # Tampilkan overlay
    dialog.show()
    dialog.raise_()

    # Buat Event Loop lokal pengganti exec_() agar tombol berfungsi lancar
    from PyQt5.QtCore import QEventLoop

    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    loop.exec_()

    res = dialog.result()
    dialog.deleteLater()  # Bersihkan memori setelah ditutup
    return res

  @staticmethod
  def show_info(parent, title, message):
    res = CustomMessageBox._show_overlay(
        parent, title, message, CustomMessageBox.INFO
    )
    return res == QDialog.Accepted

  @staticmethod
  def show_warning(parent, title, message):
    res = CustomMessageBox._show_overlay(
        parent, title, message, CustomMessageBox.WARNING
    )
    return res == QDialog.Accepted

  @staticmethod
  def show_confirm(parent, title, message):
    res = CustomMessageBox._show_overlay(
        parent, title, message, CustomMessageBox.CONFIRM
    )
    return res == QDialog.Accepted