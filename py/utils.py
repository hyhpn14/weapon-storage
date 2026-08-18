# utils.py
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtWidgets import QPushButton, QVBoxLayout
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import *
import os
import requests

def center_on_screen(widget):
    """Memposisikan widget (window atau dialog) di tengah layar desktop"""
    frameGm = widget.frameGeometry()
    screen_center = QDesktopWidget().availableGeometry().center()
    frameGm.moveCenter(screen_center)
    widget.move(frameGm.topLeft())

class ClockHelper(QObject):
    # Membuat signal yang mengirim string waktu
    time_updated = pyqtSignal(str, str, str) # Mengirim (tanggal_str, jam_str)

    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.timeout.connect(self.emit_time)
        self.timer.start(1000)

    def emit_time(self):
        now = QDateTime.currentDateTime()
        tanggal = now.toString("dddd, dd MMMM yyyy")
        jam1 = now.toString("HH:mm")
        jam2 = now.toString("HH:mm:ss")
        self.time_updated.emit(tanggal, jam1, jam2)

class LockerButton(QPushButton):
    def __init__(self, locker_id=None, parent=None):
        super().__init__(parent)
        self.locker_id = locker_id
        self.setStyleSheet("border: none;")

        # State default
        self.berat = "C"        # A, B, C
        self.relay = 0          # 0 = Lock, 1 = Open
        self.jumlah_peluru = 0  # <--- VARIABEL BARU
        self.is_warning = False
        self.storage = "gl"

        # Label internal untuk menampilkan GIF
        self.gif_label = QLabel(self)
        self.gif_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # Klik tembus ke tombol
        self.gif_label.setAlignment(Qt.AlignCenter)
        self.gif_label.hide()
        
        # --- LABEL OVERLAY UNTUK JUMLAH PELURU (KANAN BAWAH) ---
        self.lbl_peluru = QLabel(self)
        self.lbl_peluru.setAttribute(Qt.WA_TransparentForMouseEvents)  # Klik tembus ke tombol
        self.lbl_peluru.setAlignment(Qt.AlignRight | Qt.AlignVCenter)   # Rata kanan & tengah vertikal
        self.lbl_peluru.setStyleSheet("""
            QLabel {
                color: #FFFF00;
                font-family: 'Inter', sans-serif;
                font-size: 14px;
                font-weight: bold;
                background-color: transparent;
                border: none;
                padding-right: 2px;
            }
        """)
        self.lbl_peluru.hide()

        self.movie = None
        self.gif_timer = QTimer(self)
        self.gif_timer.setSingleShot(True)
        self.gif_timer.timeout.connect(self._on_gif_finished)

        if self.locker_id:
            self.setText(str(self.locker_id))

        self.update_icon()

    def update_peluru_geometry(self):
        """Helper method khusus untuk menghitung posisi kanan bawah secara dinamis."""
        if hasattr(self, 'lbl_peluru') and self.lbl_peluru:
            padding_right = 15   # Jarak dari pinggir kanan
            padding_bottom = 5  # Jarak dari pinggir bawah
            lbl_w = 70           # Lebar area teks
            lbl_h = 24           # Tinggi area teks

            # Hitung posisi X dan Y kanan bawah
            pos_x = max(0, self.width() - lbl_w - padding_right)
            pos_y = max(0, self.height() - lbl_h - padding_bottom)

            self.lbl_peluru.setGeometry(pos_x, pos_y, lbl_w, lbl_h)

    def resizeEvent(self, event):
        """Menjaga posisi GIF dan Label Peluru tetap presisi saat tombol di-resize."""
        super().resizeEvent(event)
        
        # 1. Posisikan GIF di tengah
        if hasattr(self, 'gif_label') and self.gif_label:
            gif_w, gif_h = 100, 100
            pos_x = (self.width() - gif_w) // 2
            pos_y = max(30, (self.height() - gif_h) // 2)
            self.gif_label.setGeometry(pos_x, pos_y, gif_w, gif_h)

        # 2. Posisikan Label Peluru di kanan bawah
        self.update_peluru_geometry()

    def set_jumlah_peluru(self, count):
        """Method untuk mengupdate nilai jumlah peluru dan posisi UI."""
        try:
            self.jumlah_peluru = int(count)
        except (ValueError, TypeError):
            self.jumlah_peluru = 0

        if hasattr(self, 'lbl_peluru'):
            # Tampilkan hanya jika ada muatan (A / B) dan peluru > 0
            if self.berat in ["A", "B"] and self.jumlah_peluru > 0:
                self.lbl_peluru.setText(f"{self.jumlah_peluru} Rds")
                
                # Paksa update koordinat & ukuran sebelum di-show
                self.update_peluru_geometry()
                
                self.lbl_peluru.show()
                self.lbl_peluru.raise_()
            else:
                self.lbl_peluru.setText("")
                self.lbl_peluru.hide()

    def stop_gif(self):
        """Menghentikan animasi GIF, timer, dan membersihkan memori."""
        if hasattr(self, 'gif_timer') and self.gif_timer:
            self.gif_timer.stop()
        
        if getattr(self, 'movie', None):
            self.movie.stop()
            self.movie = None
            
        if hasattr(self, 'gif_label') and self.gif_label:
            self.gif_label.hide()
            
        self.is_warning = False

    def play_gif(self, gif_path, duration_ms=0, bg_color="rgba(16, 185, 129, 0.25)", border_color="rgba(16, 185, 129, 0.70)"):
        """Memutar file GIF dan mereset total Style Sheet tombol."""
        print(f"DEBUG: Membuka GIF dari path -> {gif_path} | BG Color -> {bg_color}")
        
        self.stop_gif()

        abs_path = os.path.abspath(gif_path)
        if not os.path.exists(abs_path):
            print(f"❌ ERROR: File GIF TIDAK DITEMUKAN di path: {abs_path}")
            return

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("")

        new_style = f"""
            QPushButton {{
                text-align: left top;
                padding-left: 15px;
                padding-top: 8px;
                font-family: 'Inter', sans-serif;
                font-size: 16px;
                font-weight: bold;
                color: #FFFFFF;
                background-image: none;
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {bg_color};
                border: 2px solid {border_color};
            }}
        """
        self.setStyleSheet(new_style)

        gif_w, gif_h = 100, 100
        pos_x = (self.width() - gif_w) // 2
        pos_y = max(30, (self.height() - gif_h) // 2)

        self.gif_label.setGeometry(pos_x, pos_y, gif_w, gif_h)
        self.gif_label.setStyleSheet("background-color: transparent; border: none;")

        self.movie = QMovie(abs_path)
        if not self.movie.isValid():
            print(f"❌ ERROR: File GIF tidak valid: {abs_path}")
            return

        self.movie.setScaledSize(QSize(gif_w, gif_h))
        self.gif_label.setMovie(self.movie)
        self.gif_label.show()
        self.gif_label.raise_()
        
        # Jaga agar label peluru tetap di depan/atas layer
        if hasattr(self, 'lbl_peluru'):
            self.lbl_peluru.raise_()

        self.movie.start()

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        if duration_ms > 0:
            self.gif_timer.start(duration_ms)

    def _on_gif_finished(self):
        """Callback otomatis saat durasi GIF timer selesai diputar."""
        self.stop_gif()
        self.update_icon()

    def play_open_gif(self, duration_ms=0):
        """Memutar GIF status open sesuai folder dan prefix senjata."""
        storage_folder = getattr(self, "storage_folder", "glock")
        file_name = f"{self.storage}-open.gif"
        path = os.path.join("assets", "state", storage_folder, file_name)
        self.play_gif(path, duration_ms=duration_ms)

    def play_close_gif(self, duration_ms=0, bg_color="#991B1B", border_color="#EF4444"):
        """Memutar GIF status close/warning sesuai folder dan prefix senjata."""
        storage_folder = getattr(self, "storage_folder", "glock")
        file_name = f"{self.storage}-close.gif"
        path = os.path.join("assets", "state", storage_folder, file_name)
        self.play_gif(path, duration_ms=duration_ms, bg_color=bg_color, border_color=border_color)

    def show_warning_icon(self):
        """Menampilkan animasi GIF warning."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 1. Ambil folder dinamis, default ke "glock" jika tidak ditemukan
        storage_folder = getattr(self, "storage_folder", "glock")
        file_name = f"{self.storage}-warning.gif"
        path = os.path.join(base_dir, "assets", "state", storage_folder, file_name)

        if os.path.exists(path):
            self.stop_gif()
            self.is_warning = True

            if self.locker_id:
                self.setText(str(self.locker_id))

            self.setStyleSheet("""
                QPushButton {
                    text-align: left top;
                    padding-left: 12px;
                    padding-top: 8px;
                    font-family: 'Inter', sans-serif;
                    font-size: 16px;
                    font-weight: bold;
                    color: rgba(255, 255, 255, 0.9);
                    background-image: none;
                    background-color: rgba(239, 68, 68, 0.40);
                    border: 2px solid rgba(239, 68, 68, 0.90);
                    border-radius: 12px;
                }
            """)

            gif_w, gif_h = 100, 100
            pos_x = (self.width() - gif_w) // 2
            pos_y = max(30, (self.height() - gif_h) // 2)

            self.gif_label.setGeometry(pos_x, pos_y, gif_w, gif_h)
            self.gif_label.setStyleSheet("background: transparent; border: none;")

            self.movie = QMovie(path)
            self.movie.setScaledSize(QSize(gif_w, gif_h))
            self.gif_label.setMovie(self.movie)
            self.gif_label.show()
            self.gif_label.raise_()
            
            if hasattr(self, 'lbl_peluru'):
                self.lbl_peluru.raise_()

            self.movie.start()
        else:
            print(f"[LockerButton] GIF Warning tidak ditemukan: {path}")

    def update_icon(self):
        """Set tampilan tombol berdasarkan status berat (A/B/C) dan relay (open/lock).

        CATATAN: relay sekarang bisa mati murni karena pulsa waktu (5 detik,
        lihat home.py end_unlock_pulse()) sementara locker secara logis
        masih dianggap terbuka (is_open_pending=True, menunggu limit_switch
        fisik konfirmasi tertutup). Karena itu, status VISUAL yang
        ditampilkan tidak lagi murni ikut self.relay -- kalau
        is_open_pending masih True, tetap tampilkan status 'open'."""
        self.stop_gif()

        if self.locker_id:
            self.setText(str(self.locker_id))

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        berat_map = {"A": "full", "B": "half", "C": "empty"}
        relay_map = {1: "open", 0: "lock"}

        # is_open_pending (kalau ada, ditempel dari home.py) menang atas
        # self.relay untuk urusan tampilan open/lock.
        display_open = bool(getattr(self, "is_open_pending", False)) or self.relay == 1
        relay_for_display = 1 if display_open else 0

        berat_str = berat_map.get(self.berat, "empty")
        relay_str = relay_map.get(relay_for_display, "lock")

        # storage_folder (kalau ada, ditempel dari home.py sesuai profil
        # device -- "glock" atau "aug") menentukan folder asset yang
        # dipakai. Default "glock" untuk kompatibilitas kalau atribut ini
        # belum ditempel (mis. dipakai di tempat lain di luar Home).
        storage_folder = getattr(self, "storage_folder", "glock")

        file_name = f"{self.storage}-{berat_str}-{relay_str}.png"
        path = os.path.join(base_dir, "assets", "state", storage_folder, relay_str, file_name)
        formatted_path = path.replace("\\", "/")

        color_config = {
            "A": {
                "active_bg": "rgba(16, 185, 129, 0.25)",
                "active_border": "rgba(16, 185, 129, 0.70)",
                "hover_bg": "rgba(16, 185, 129, 0.15)",
                "hover_border": "rgba(16, 185, 129, 0.40)",
                "pressed_bg": "rgba(16, 185, 129, 0.30)",
            },
            "B": {
                "active_bg": "rgba(248, 214, 19, 0.25)",
                "active_border": "rgba(248, 214, 19, 0.70)",
                "hover_bg": "rgba(248, 214, 19, 0.15)",
                "hover_border": "rgba(248, 214, 19, 0.40)",
                "pressed_bg": "rgba(248, 214, 19, 0.30)",
            },
            "C": {
                "active_bg": "rgba(239, 68, 68, 0.25)",
                "active_border": "rgba(239, 68, 68, 0.70)",
                "hover_bg": "rgba(239, 68, 68, 0.15)",
                "hover_border": "rgba(239, 68, 68, 0.40)",
                "pressed_bg": "rgba(239, 68, 68, 0.30)",
            }
        }

        colors = color_config.get(self.berat, color_config["C"])

        if os.path.exists(path):
            if display_open:
                self.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left top;
                        padding-left: 15px;
                        padding-top: 8px;
                        font-family: 'Inter', sans-serif;
                        font-size: 16px;
                        font-weight: bold;
                        color: rgba(255, 255, 255, 0.9);
                        background-image: url('{formatted_path}');
                        background-position: center;
                        background-repeat: no-repeat;
                        background-color: {colors['active_bg']};
                        border: 2px solid {colors['active_border']};
                        border-radius: 12px;
                    }}
                    QPushButton:hover {{
                        background-color: {colors['active_bg']};
                        border: 2px solid {colors['active_border']};
                    }}
                    QPushButton:pressed {{
                        background-color: {colors['pressed_bg']};
                        border: 2px solid {colors['active_border']};
                    }}
                """)
            else:
                self.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left top;
                        padding-left: 15px;
                        padding-top: 8px;
                        font-family: 'Inter', sans-serif;
                        font-size: 16px;
                        font-weight: bold;
                        color: rgba(255, 255, 255, 0.5);
                        background-image: url('{formatted_path}');
                        background-position: center;
                        background-repeat: no-repeat;
                        background-color: rgba(255, 255, 255, 0.03);
                        border: 2px solid rgba(255, 255, 255, 0.06);
                        border-radius: 12px;
                    }}
                    QPushButton:hover {{
                        background-color: {colors['hover_bg']};
                        border: 2px solid {colors['hover_border']};
                    }}
                    QPushButton:pressed {{
                        background-color: {colors['pressed_bg']};
                        border: 2px solid {colors['active_border']};
                    }}
                """)
        else:
            print(f"[LockerButton] Path tidak ditemukan: {path}")

        # Update teks peluru saat icon di-refresh
        self.set_jumlah_peluru(self.jumlah_peluru)

        # Update badge status berat (FULL/HALF/EMPTY) kalau ada -- ini
        # murni ikut self.berat, TIDAK ikut display_open/relay, karena
        # badge ini soal isi loker (senjata+amunisi), bukan status
        # terkunci/terbuka.
        badge = getattr(self, "status_badge", None)
        if badge is not None:
            badge_config = {
                "A": ("FULL", "rgba(16, 185, 129, 0.30)", "rgba(16, 185, 129, 0.30)"),
                "B": ("HALF", "rgba(248, 214, 19, 0.20)", "rgba(248, 214, 19, 0.40)"),
                "C": ("EMPTY", "rgba(220, 53, 69, 0.20)", "rgba(220, 53, 69, 0.50)"),
            }
            text, bg, border = badge_config.get(self.berat, badge_config["C"])
            badge.setText(text)
            badge.setStyleSheet(f"""
                color: rgba(255,255,255,0.60);
                font-size: 13px;
                font-weight: 600;
                font-family: Inter;
                background: {bg};
                border: 2px solid {border};
                border-radius: 10px;
            """)

    def toggle_relay(self):
        self.relay = 1 if self.relay == 0 else 0
        return self.relay

    def set_berat(self, new_berat):
        if new_berat in ["A", "B", "C"]:
            self.berat = new_berat
            self.update_icon()

class SystemStatusHelper(QObject):
    status_changed = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.current_state = "active"
        self.current_text = "System Active"
        self._toggle_flag = False  # Flag untuk mengganti-ganti tampilan saat multiple error

    def update_status(self, db_connected=True, controller_connected=True):
        """
        Mengevaluasi status koneksi. 
        Jika kedua koneksi bermasalah, pesan status akan bergantian (rotasi).
        """
        # Kasus 1: Kedua-duanya Mati -> Rotasi/Bertukar Tampilan
        if not db_connected and not controller_connected:
            self._toggle_flag = not self._toggle_flag
            if self._toggle_flag:
                state, text = "warning", "Waiting For Database"
            else:
                state, text = "error", "Check your Controller Connector"

        # Kasus 2: Hanya Database Mati
        elif not db_connected:
            state, text = "warning", "Waiting For Database"

        # Kasus 3: Hanya Controller/Arduino Mati
        elif not controller_connected:
            state, text = "error", "Check your Controller Connector"

        # Kasus 4: Semuanya Normal
        else:
            state, text = "active", "System Active"

        self.current_state = state
        self.current_text = text
        
        # Transmisikan sinyal pembaruan
        self.status_changed.emit(state, text)