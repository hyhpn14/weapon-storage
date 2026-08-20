import json
import os
import sys
from db_config import get_db_connection
from pulsing_widget import PulsingStatusBadge
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.uic import loadUi
from PyQt5.QtWidgets import *
from screens import Home, Login, Register, Saver
from serial_handler import SerialHandler
from utils import ClockHelper, SystemStatusHelper, center_on_screen
from log_client import send_log


def load_gudang_config():
    # PERBAIKAN: pakai path ABSOLUT relatif ke lokasi main.py sendiri
    # (bukan working directory saat command dijalankan). Sebelumnya
    # "config.json" dicari relatif ke cwd -- kalau app dijalankan dari
    # folder lain (mis. `python3 py/main.py` dari satu folder di atasnya),
    # file tidak pernah ketemu dan diam-diam fallback ke GLOCK17 tanpa
    # error apa pun.
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
 
    # Cek apakah file config.json ada
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                data = json.load(f)
                return data.get("gudang", "GLOCK17")
        except Exception as e:
            print(f"⚠️ Gagal membaca config.json: {e}")
    else:
        print(f"⚠️ config.json tidak ditemukan di: {config_file}")
 
    return "GLOCK17"


# Ambil konfigurasi gudang yang aktif
GUDANG = load_gudang_config()
print(f"Storage Mode Aktif: [{GUDANG}]")


class MainApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(1024, 600)

        if hasattr(self, "titlebar"):
            self.titlebar.mousePressEvent = self.mousePressEvent
            self.titlebar.mouseMoveEvent = self.mouseMoveEvent

        self.oldPos = QPoint()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.clock_helper = ClockHelper()
        self.status_helper = SystemStatusHelper()
        self.history = []

        # FLAG GERBANG LOGIN: locker data HANYA boleh diproses kalau True.
        # Diset True saat login sukses, direset False saat logout.
        self.is_authenticated = False

        # SATU SerialHandler untuk seluruh aplikasi
        self.serial_handler = SerialHandler()

        # PENTING: self.screens harus SUDAH ada sebelum serial_handler.start()
        # dipanggil, karena begitu port kebuka, thread bisa langsung emit
        # data dan handle_data() butuh self.screens untuk routing.
        # (Sebelumnya start() dipanggil duluan -> berpotensi race condition/
        # AttributeError kalau data masuk sangat cepat setelah port terbuka.)
        self.sizes = {
            "saver": (1024, 600),
            "login": (1024, 600),
            "register": (1024, 600),
            "home": (1024, 600),
        }

        self.screens = {
            "saver": Saver(self.clock_helper),
            "login": Login( self.clock_helper, serial_handler=self.serial_handler, gudang=GUDANG,),
            "register": Register(
                self.clock_helper,
                serial_handler=self.serial_handler,
                gudang=GUDANG,
            ),
            "home": Home(serial_handler=self.serial_handler, gudang=GUDANG),
        }

        for widget in self.screens.values():
            self.stack.addWidget(widget)

        # Baru sekarang aman untuk mulai membuka port & menerima data.
        # start() TIDAK lagi otomatis mengirim WHO_ARE_YOU (lihat
        # serial_handler.py) -> saat MainApp pertama jalan, ini betul-betul
        # cuma "cek koneksi port" (physical open), belum ada command apa pun
        # yang dikirim ke Arduino.
        self.serial_handler.start(
            callback_func=self.handle_data,
            callback_conn_func=self.on_serial_connection_changed
        )

        # Hubungkan sinyal/event perubahan koneksi ke SystemStatusHelper jika tersedia
        if hasattr(self.serial_handler, "connection_changed"):
            self.serial_handler.connection_changed.connect(self.on_serial_connection_changed)

        # Injeksi badge status dan hubungkan ke status_helper
        self.attach_and_connect_status_badges()

        # TIMER CHECK HEALTH BERKALA (Pasif / RAM Only, tidak kirim command ke Arduino)
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self.check_system_health)
        self.health_timer.start(3000)  # Jalankan pengecekan tiap 3 detik

        # Jalankan sekali saat startup
        QTimer.singleShot(500, self.check_system_health)

        # Navigasi (Sinyal -> Fungsi)
        self.screens["saver"].go_to_login.connect(lambda: self.navigate_to("login"))
        self.screens["login"].btCls_login.clicked.connect(lambda: self.navigate_to("saver"))

        self.screens["register"].go_back.connect(lambda: self.navigate_to("login"))
        self.screens["login"].btRegis.clicked.connect(lambda: self.navigate_to("register"))

        # Login sukses -> bawa nrp & nama, baru pindah ke Home
        self.screens["login"].login_success.connect(self.handle_login_success)

        # Logout
        self.screens["home"].logout_signal.connect(self.reset_system)

        center_on_screen(self)

        send_log(
            kategori="system",
            aktivitas="system_start",
            detail=f"Storage Mode: {GUDANG}",
            metode="startup",
            status="success"
        )

    def handle_data(self, role, tag, value):
        """
        SATU-SATUNYA gerbang routing data serial di seluruh aplikasi.
        Semua screen/dialog yang butuh data serial (Home, AuthFinger,
        AuthRFID, AuthPin) WAJIB menerima data lewat jalur ini -> lewat
        active_screen.handle_serial_data(). JANGAN ada widget yang connect
        langsung ke thread.internal_data_received, supaya gerbang login di
        bawah ini tidak bisa dilewati/di-bypass.
        """
        active_screen = self.stack.currentWidget()

        # ISOLASI DATA LOCKER: locker HANYA diproses kalau (1) user sudah
        # login DAN (2) layar Home yang sedang aktif. Kalau salah satu
        # syarat tidak terpenuhi, data locker langsung dibuang -> tidak
        # akan pernah "nyasar" tampil di layar Login/Saver/Register.
        if tag == "LOCKER":
            if self.is_authenticated and active_screen == self.screens["home"]:
                self.screens["home"].handle_serial_data(role, tag, value)
            return

        # Data non-LOCKER (mis. RFID/FINGER/PIN untuk proses login) tetap
        # diteruskan ke layar aktif yang punya handler, TIDAK digerbang
        # oleh is_authenticated karena data ini justru dipakai UNTUK login.
        if hasattr(active_screen, "handle_serial_data"):
            active_screen.handle_serial_data(role, tag, value)

    def attach_and_connect_status_badges(self):
        """Memasang PulsingStatusBadge di tiap layar dan menyambungkannya ke status_helper."""
        for name, screen in self.screens.items():
            if hasattr(screen, "statusLabel"):
                screen.statusLabel.hide()

                badge = PulsingStatusBadge(parent=screen.frame_status if hasattr(screen, "frame_status") else screen )

                if hasattr(screen, "horizontalLayout_status"):
                    screen.horizontalLayout_status.insertWidget(0, badge)
                elif hasattr(screen, "layoutStatus"):
                    screen.layoutStatus.insertWidget(0, badge)

                # Hubungkan sinyal pembaharuan status
                self.status_helper.status_changed.connect(badge.set_status)

                # Set nilai awal badge saat pertama di-attach
                badge.set_status(
                    self.status_helper.current_state,
                    self.status_helper.current_text,
                )

    def on_serial_connection_changed(self, role, is_connected):
        """Callback otomatis ketika status fisik kabel Arduino berubah."""
        if is_connected:
            print(f"[Serial Status] Arduino [{role}] BERHASIL TERHUBUNG.")
        else:
            print(f"[Serial Status] Arduino [{role}] TERPUTUS.")

        self.check_system_health()

    def check_system_health(self):
        """Pengecekan Kesehatan DB dan Status Koneksi Arduino yang Sebenarnya.
        Murni membaca status (db_ok, controller_ok) -> TIDAK mengirim command
        apa pun ke Arduino."""
        db_ok = True
        controller_ok = False  # Default-kan ke False (Offline) dulu!

        # 1. Cek Koneksi Database
        try:
            conn = get_db_connection()
            if conn and conn.is_connected():
                conn.close()
            else:
                db_ok = False
        except Exception:
            db_ok = False

        # 2. Cek Koneksi Arduino Sebenarnya (cuma baca flag is_connected,
        # TIDAK mengirim apa pun ke port)
        if hasattr(self, 'serial_handler') and self.serial_handler.threads:
            for thread in self.serial_handler.threads:
                if thread.is_connected:
                    controller_ok = True
                    break

        # 3. Broadcast ke status_helper
        self.status_helper.update_status(db_connected=db_ok, controller_connected=controller_ok)

    def handle_login_success(self, nrp, nama, id_locker=None, status=None):
        self.is_authenticated = True
        self.screens["home"].set_user(nrp, nama, id_locker, status)
        self.navigate_to("home")

    def navigate_to(self, page_name):
        self.history.append(self.stack.currentIndex())
        index = list(self.screens.keys()).index(page_name)
        self.stack.setCurrentIndex(index)

        if page_name in self.sizes:
            width, height = self.sizes[page_name]
            self.setFixedSize(width, height)
            center_on_screen(self)

        # Baru di sini, saat user BENAR-BENAR masuk layar Login, kita buka
        # gerbang identitas dan minta Arduino yang sudah tersambung untuk
        # kenalan (WHO_ARE_YOU). Sebelum ini (layar Saver / awal aplikasi
        # jalan), tidak ada command apa pun yang dikirim ke Arduino manapun
        # -> port cuma dicek terbuka/tidak.
        # Aman dipanggil berulang (setiap kali kembali ke Login) -- device
        # yang sudah kenalan cukup balas IDENTITY lagi, tidak masalah.
        if page_name == "login":
            self.serial_handler.identity_gate_open = True
            self.serial_handler.broadcast_identity_request()

    def reset_system(self):
        print("Sistem di-reset...")
        self.is_authenticated = False
        self.force_lock_all_lockers()

        # Bersihkan info user yang login
        self.screens["home"].set_user(None, None)

        self.stack.setCurrentIndex(0)

        for name, screen in self.screens.items():
            if hasattr(screen, "stop_scanning"):
                print(f"Menghentikan proses pada layar: {name}")
                screen.stop_scanning()

            if hasattr(screen, "load_data_from_db"):
                screen.load_data_from_db()

    def force_lock_all_lockers(self):
        """Memaksa semua loker kembali ke kondisi terkunci di database."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE tb_data SET relay = 0")  # 0 = lock
            conn.commit()
            cursor.close()
            conn.close()
            print("Semua relay di-reset ke Lock (0).")
        except Exception as e:
            print(f"Gagal reset relay: {e}")

    def closeEvent(self, event):
        self.serial_handler.stop()
        event.accept()

    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()

    def mouseMoveEvent(self, event):
        delta = QPoint(event.globalPos() - self.oldPos)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPos = event.globalPos()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec_())