from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.uic import loadUi
from utils import LockerButton
from dialogs import DbMessage
from custom_dialog import CustomMessageBox
from db_config import get_db_connection

LOCKER_ORDER = ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5",
                "C1", "C2", "C3", "C4", "C5", "D1", "D2", "D3", "D4", "D5"]

class Home(QMainWindow):
    go_to_home2 = pyqtSignal()
    logout_signal = pyqtSignal()

    def __init__(self, serial_handler=None, gudang="GLOCK17"):
        super().__init__()
        loadUi("ui2/homee.ui", self)

        self.serial = serial_handler
        if self.serial:
            self.serial.data_received.connect(self.handle_locker_data)

        self.gudang = gudang
        self.current_nrp = None
        self.current_nama = None

        self.btRefresh.clicked.connect(self.load_data_from_db)
        self.btLogout.clicked.connect(self.handle_logout)

        self.locker_buttons = {
            "A1": self.btA1, "A2": self.btA2, "A3": self.btA3, "A4": self.btA4, "A5": self.btA5,
            "B1": self.btB1, "B2": self.btB2, "B3": self.btB3, "B4": self.btB4, "B5": self.btB5,
            "C1": self.btC1, "C2": self.btC2, "C3": self.btC3, "C4": self.btC4, "C5": self.btC5,
            "D1": self.btD1, "D2": self.btD2, "D3": self.btD3, "D4": self.btD4, "D5": self.btD5
        }

        for name, btn in self.locker_buttons.items():
            btn.locker_id = name
            btn.berat = "C"
            btn.relay = 0          # 0 = lock
            btn.limit_switch = 0   # 0 = pintu tertutup
            btn.is_warning = False
            btn.storage = "gl"

            btn.is_unlocking_grace = False  # Menandai apakah loker baru saja dipicu untuk dibuka

            # --- INIALISASI ATRIBUT GIF (Mencegah AttributeError) ---
            btn.movie = None
            btn.gif_timer = QTimer(btn)
            btn.gif_timer.setSingleShot(True)
            
            # Label untuk GIF jika belum ada di widget
            if not hasattr(btn, 'gif_label'):
                btn.gif_label = QLabel(btn)
                btn.gif_label.setAttribute(Qt.WA_TransparentForMouseEvents)
                btn.gif_label.setAlignment(Qt.AlignCenter)
                btn.gif_label.hide()

            # --- BINDING METHOD ---
            btn.update_icon = LockerButton.update_icon.__get__(btn, LockerButton)
            btn.toggle_relay = LockerButton.toggle_relay.__get__(btn, LockerButton)
            btn.show_warning_icon = LockerButton.show_warning_icon.__get__(btn, LockerButton)
            btn.play_gif = LockerButton.play_gif.__get__(btn, LockerButton)
            btn.stop_gif = LockerButton.stop_gif.__get__(btn, LockerButton)
            btn._on_gif_finished = LockerButton._on_gif_finished.__get__(btn, LockerButton)

            # Connect timeout timer ke callback stop gif
            btn.gif_timer.timeout.connect(btn._on_gif_finished)

            btn.clicked.connect(lambda _, b=btn: self.handle_locker_click(b))

    def set_user(self, nrp, nama):
        """Dipanggil dari main.py setelah login sukses / saat reset logout"""
        self.current_nrp = nrp
        self.current_nama = nama
        if hasattr(self, 'lbUser'):
            self.lbUser.setText(nama if nama else "")

    def showEvent(self, event):
        self.load_data_from_db()
        super().showEvent(event)

    def load_data_from_db(self):
        try:
            # 1. Reset state awal
            for btn in self.locker_buttons.values():
                btn.berat = "C"
                btn.relay = 0
                btn.limit_switch = 0

            # 2. Query dari Database
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id_locker, berat, limit_switch, relay FROM tb_data WHERE gudang=%s", (self.gudang,))
            rows = cursor.fetchall()

            # 3. Normalisasi & assign data dari DB ke button
            for row in rows:
                if row['id_locker'] in self.locker_buttons:
                    btn = self.locker_buttons[row['id_locker']]
                    
                    btn.berat = str(row['berat']).strip().upper() if row['berat'] else "C"
                    btn.limit_switch = int(row['limit_switch']) if row['limit_switch'] is not None else 0
                    btn.relay = int(row['relay']) if row['relay'] is not None else 0

            cursor.close()
            conn.close()

            # 4. Refresh icon visual semua tombol
            for btn in self.locker_buttons.values():
                btn.update_icon()

            # 5. Perbarui label statistik
            self.update_stats()

            print("Refresh/Load data dari Database berhasil.")

        except Exception as e:
            print(f"Gagal load data: {e}")

    def update_stats(self):
        """Kalkulasi data dari button state & tampilkan ke QLabels"""
        total = len(self.locker_buttons)  # 20
        filled = 0
        empty = 0
        alert = 0

        for btn in self.locker_buttons.values():
            if btn.berat in ["A", "B"]:
                filled += 1
            else:
                empty += 1

            if btn.relay == 1 or btn.limit_switch == 1:
                alert += 1

        percent = int((filled / total) * 100) if total > 0 else 0

        if hasattr(self, 'statTotal'):
            self.statTotal.setText(f"📦 Total: {total}")
        if hasattr(self, 'statFilled'):
            self.statFilled.setText(f"🔒 Terisi: {filled}")
        if hasattr(self, 'statEmpty'):
            self.statEmpty.setText(f"📥 Kosong: {empty}")
        if hasattr(self, 'statAlert'):
            self.statAlert.setText(f"⚠️ Alert: {alert}")
        if hasattr(self, 'statPercent'):
            self.statPercent.setText(f"{percent}% Terisi")

    def handle_locker_click(self, btn):
        """User klik tombol locker di UI -> toggle relay -> update DB"""
        
        # 1. Toggle relay state (1 = Terbuka, 0 = Tertutup)
        new_relay = btn.toggle_relay()
        
        # 2. Hentikan timer auto-close lama jika ada
        if hasattr(btn, 'auto_close_timer') and btn.auto_close_timer:
            btn.auto_close_timer.stop()

        if new_relay == 1:
            # --- LOKER DIBUKA ---
            # Aktifkan Grace Period agar sinyal ls=1 diabaikan sementara
            btn.is_unlocking_grace = True
            
            # Matikan grace period setelah 3 detik (3000 ms)
            QTimer.singleShot(10000, lambda b=btn: setattr(b, 'is_unlocking_grace', False))

            btn.play_gif("assets/state/open.gif", duration_ms=0)

            # Inisialisasi Timer Warning 1 Menit jika pintu tidak kunjung ditutup kembali
            if not hasattr(btn, 'auto_close_timer') or btn.auto_close_timer is None:
                btn.auto_close_timer = QTimer(self)
                btn.auto_close_timer.setSingleShot(True)

            try:
                btn.auto_close_timer.timeout.disconnect()
            except Exception:
                pass

            def on_1_minute_timeout(target_btn=btn):
                if target_btn.relay == 1:
                    print(f"⚠️ Warning 1 Menit: Loker {target_btn.locker_id} belum ditutup!")
                    target_btn.play_gif(
                        "assets/state/close.gif", 
                        duration_ms=0, 
                        bg_color="#991B1B", 
                        border_color="#EF4444"
                    )
                    if self.serial:
                        self.serial.send_command(f"WARN:{target_btn.locker_id}\n")

            btn.auto_close_timer.timeout.connect(on_1_minute_timeout)
            btn.auto_close_timer.start(60000)  # 1 Menit

        # 3. Update Database & Kirim Perintah ke Arduino
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = "UPDATE tb_data SET relay = %s WHERE id_locker = %s AND gudang=%s"
            cursor.execute(query, (new_relay, btn.locker_id, self.gudang))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Gagal update DB: {e}")

        self.log_locker_activity(btn.locker_id, btn.berat, btn.limit_switch, new_relay)
        self.update_stats()
        self.send_lock_command()

    def send_lock_command(self):
        """Kirim status relay seluruh loker sebagai string biner ke Arduino"""
        if not self.serial:
            return
        bits = "".join(str(self.locker_buttons[loc].relay) for loc in LOCKER_ORDER)
        self.serial.send_command(bits)
        print(f"Kirim status loker: L:{bits}")

    def handle_locker_data(self, tag, value):
        """Terima data dari Arduino: tag='LOCKER', value='A1,C,1,0,...'"""
        raw = value.strip()
        parts = raw.split(",")

        if len(parts) % 4 != 0:
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            relay_changed_to_lock = False

            for i in range(0, len(parts), 4):
                locker_id = parts[i]
                berat = parts[i + 1]
                limit_switch = int(parts[i + 2])  # 1 = Close, 0 = Open
                relay = int(parts[i + 3])         # 0 = Lock, 1 = Open

                if locker_id in self.locker_buttons:
                    btn = self.locker_buttons[locker_id]

                    # --- PROSES KUNCI ULANG HANYA JIKA GRACE PERIOD SUDAH SELESAI ---
                    if limit_switch == 1 and btn.relay == 1 and not getattr(btn, 'is_unlocking_grace', False):
                        print(f"🔒 Loker {locker_id} ditutup (LS=1) & Grace Period selesai. Mengunci relay...")

                        # 1. Matikan Timer Warning 1 menit
                        if hasattr(btn, 'auto_close_timer') and btn.auto_close_timer:
                            btn.auto_close_timer.stop()

                        # 2. Hentikan Animasi GIF
                        btn.stop_gif()

                        # 3. Reset relay ke 0 (Lock)
                        btn.relay = 0
                        relay_changed_to_lock = True

                    berubah = (btn.berat != berat or btn.limit_switch != limit_switch or btn.relay != relay)

                    btn.berat = berat
                    btn.limit_switch = limit_switch

                    if not getattr(btn, 'is_warning', False) and (not btn.movie or btn.movie.state() == 0):
                        btn.update_icon()

                    query = "UPDATE tb_data SET berat = %s, limit_switch = %s, relay = %s WHERE id_locker = %s AND gudang =%s"
                    cursor.execute(query, (berat, limit_switch, btn.relay, locker_id, self.gudang))

                    if berubah:
                        self.log_locker_activity(locker_id, berat, limit_switch, btn.relay)

            conn.commit()
            cursor.close()
            conn.close()

            # Send command relay = 0 ke Arduino
            if relay_changed_to_lock:
                self.send_lock_command()

            self.update_stats()

        except Exception as e:
            print(f"Gagal update data locker dari Arduino: {e}")
    
    def log_locker_activity(self, id_locker, berat, limit_switch, relay):
        """INSERT riwayat aktivitas loker ke tb_log_locker"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                INSERT INTO tb_log_locker (id_locker, nrp, nama, berat, limit_switch, relay, gudang)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (id_locker, self.current_nrp, self.current_nama, berat, limit_switch, relay, self.gudang))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"Log locker tersimpan: {id_locker} - berat={berat}, limit={limit_switch}, relay={relay}, gudang={self.gudang}")
        except Exception as e:
            print(f"Gagal simpan log locker: {e}")

    def handle_logout(self):
        """Validasi sebelum logout"""
        open_lockers = [btn for btn in self.locker_buttons.values() if btn.relay == 1]

        if open_lockers:
            list_ids = ", ".join([btn.locker_id for btn in open_lockers])
            CustomMessageBox.show_warning(self, "Logout Failed", f"Lockers {list_ids} are still open. Please close those lockers before logging out.")
            # msg = DbMessage(
            #     self,
            #     title="Logout Ditolak",
            #     message=f"Loker berikut masih terbuka secara fisik: {list_ids}. Silakan tutup loker tersebut!",
            #     success=False
            # )
            # msg.exec_()
            for btn in open_lockers:
                btn.show_warning_icon()
            return

        print("Logout berhasil...")
        self.logout_signal.emit()