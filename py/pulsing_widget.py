from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QBrush

class PulseDot(QWidget):
    """Widget lingkaran dengan animasi denyut (pulse) halus"""
    def __init__(self, parent=None, dot_color="#10B981", ring_color="#6EE7B7"):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.dot_color = QColor(dot_color)
        self.ring_color = QColor(ring_color)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(1200)
        self.anim.setStartValue(0.3)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.anim.finished.connect(self.reverse_anim)
        self.anim.start()

    def reverse_anim(self):
        start = self.anim.startValue()
        end = self.anim.endValue()
        self.anim.setStartValue(end)
        self.anim.setEndValue(start)
        self.anim.start()

    def set_colors(self, dot_color, ring_color):
        self.dot_color = QColor(dot_color)
        self.ring_color = QColor(ring_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Ring Luar
        ring_bg = QColor(self.ring_color)
        ring_bg.setAlpha(80)
        painter.setBrush(QBrush(ring_bg))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 28, 28)
        
        # Titik Dalam
        painter.setBrush(QBrush(self.dot_color))
        painter.drawEllipse(7, 7, 14, 14)


class PulsingStatusBadge(QFrame):
    """Widget kapsul status dengan pilihan warna preset (Active, Warning, Error)"""
    STATUS_PRESETS = {
        "active": {
            "dot": "#10B981", "ring": "#6EE7B7", "text": "#10B981", 
            "bg": "rgba(16, 185, 129, 0.12)", "border": "rgba(16, 185, 129, 0.25)"
        },
        "warning": {
            "dot": "#F59E0B", "ring": "#FDE68A", "text": "#F59E0B", 
            "bg": "rgba(245, 158, 11, 0.12)", "border": "rgba(245, 158, 11, 0.25)"
        },
        "error": {
            "dot": "#EF4444", "ring": "#FCA5A5", "text": "#EF4444", 
            "bg": "rgba(239, 68, 68, 0.12)", "border": "rgba(239, 68, 68, 0.25)"
        }
    }

    def __init__(self, parent=None, text="System Active", state="active"):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 16, 3)
        layout.setSpacing(8)
        
        self.pulse_dot = PulseDot(self)
        self.lbl_text = QLabel(text)
        
        layout.addWidget(self.pulse_dot)
        layout.addWidget(self.lbl_text)

        self.set_status(state, text)

    def set_status(self, state="active", custom_text=None):
        """Satu fungsi untuk mengubah tampilan berdasarkan nama state ('active'|'warning'|'error')"""
        preset = self.STATUS_PRESETS.get(state, self.STATUS_PRESETS["active"])
        # self.setStyleSheet(f"""
        #     QFrame {{
        #         background-color: {preset['bg']};
        #         border: 1px solid {preset['border']};
        #         border-radius: 18px;
        #     }}
        # """)
        self.lbl_text.setStyleSheet(f"""
            color: {preset['text']};
            font-family: 'Inter', 'Plus Jakarta Sans', sans-serif;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        self.pulse_dot.set_colors(preset["dot"], preset["ring"])
        if custom_text:
            self.lbl_text.setText(custom_text)