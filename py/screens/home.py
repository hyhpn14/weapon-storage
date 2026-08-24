from db_config import get_db_connection
from dialogs import DbMessage
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QIcon
from PyQt5.uic import loadUi
from utils import LockerButton
from log_client import send_log

# ============================================================
# PROFIL PER-DEVICE
# ============================================================
# Satu app cuma jalanin SATU jenis storage dalam satu sesi, dipilih lewat
# config.json ("gudang"). Home() akan otomatis pakai profil yang sesuai.
#
# Kalau nanti ada device ketiga, tinggal tambah 1 entry baru di sini --
# TIDAK perlu bikin class Home baru atau duplikasi logic apa pun.
#
# locker_groups: role Arduino -> daftar locker_id yang dikontrolnya.
#   - Urutan list SENGAJA sama persis dengan urutan modul di firmware
#     Arduino masing-masing role (module[i].ilsd = i+1), karena dipakai
#     langsung buat hitung nomor modul (lihat get_module_id()).
#   - Tiap role = 1 Arduino fisik terpisah dengan role/identity sendiri.
DEVICE_PROFILES = {
    "GLOCK17": {
        "ui_file": "ui2/homee.ui",
        "storage_folder": "glock",   # -> assets/state/glock/...
        "storage_prefix": "gl",      # -> gl-full-lock.png, dst.
        "locker_groups": {
            "MAIN_CONTROLLER": ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"],
            "LOCKER_EXPANSION": ["C1", "C2", "C3", "C4", "C5", "D1", "D2", "D3", "D4", "D5"],
        },
    },
    "AUGSTYER": {
        # SESUAIKAN nama file ini kalau file UI AUG kamu namanya beda.
        "ui_file": "ui2/home_aug.ui",
        "storage_folder": "aug",     # -> assets/state/aug/...
        "storage_prefix": "aug",     # -> aug-full-lock.png, dst.
        "locker_groups": {
            # SESUAIKAN nama role ini dengan yang dikirim firmware AUG
            # lewat "IDENTITY:..." (WHO_ARE_YOU response).
            "AUG_CONTROLLER": ["E1", "E2", "E3", "E4", "E5", "F1", "F2", "F3", "F4", "F5"],
        },
    },
}

DEFAULT_PROFILE_KEY = "GLOCK17"


class Home(QMainWindow):
    go_to_home2 = pyqtSignal()
    logout_signal = pyqtSignal()

    def __init__(self, serial_handler=None, gudang="GLOCK17"):
        super().__init__()

        # Pilih profil sesuai gudang. Fallback ke Glock kalau gudang tidak
        # dikenali (mis. salah ketik di config.json) supaya app tetap bisa
        # jalan, bukan crash.
        self.gudang = gudang
        self.profile = DEVICE_PROFILES.get(gudang, DEVICE_PROFILES[DEFAULT_PROFILE_KEY])
        if gudang not in DEVICE_PROFILES:
            print(f"⚠️ Gudang '{gudang}' tidak dikenali di DEVICE_PROFILES, fallback ke {DEFAULT_PROFILE_KEY}.")

        loadUi(self.profile["ui_file"], self)

        self.serial = serial_handler
        self.current_nrp = None
        self.current_nama = None

        # role -> [locker_id, ...], sesuai profil aktif
        self.locker_groups = self.profile["locker_groups"]
        self.storage_folder = self.profile["storage_folder"]
        self.storage_prefix = self.profile["storage_prefix"]

        self.btRefresh.clicked.connect(self.load_data_from_db)
        self.btLogout.clicked.connect(self.handle_logout)

        # Dictionary tombol loker -- dibangun otomatis dari locker_groups,
        # jadi tidak perlu tulis manual btA1..btD5 / btE1..btF5 di sini.
        # Nama widget di .ui HARUS "bt" + locker_id (mis. btA1, btE3).
        self.locker_buttons = {}
        for role, locker_ids in self.locker_groups.items():
            for loc in locker_ids:
                widget_name = f"bt{loc}"
                if not hasattr(self, widget_name):
                    raise AttributeError(
                        f"Widget '{widget_name}' tidak ditemukan di {self.profile['ui_file']}."
                        f"Pastikan nama tombol di .ui persis 'bt{loc}'."
                    )
                self.locker_buttons[loc] = getattr(self, widget_name)

        # Inisialisasi properti & event pada setiap tombol loker
        for name, btn in self.locker_buttons.items():
            btn.locker_id = name
            btn.berat = "C"
            btn.jumlah_peluru = 0
            btn.relay = 0  # 0 = solenoid mati, 1 = solenoid aktif (SINYAL LISTRIK)
            btn.limit_switch = 0  # 0 = tertutup, 1 = terbuka
            btn.is_warning = False
            btn.storage = self.storage_prefix        # mis. "gl" / "aug"
            btn.storage_folder = self.storage_folder  # mis. "glock" / "aug"
            btn.is_unlocking_grace = False
            btn.is_open_pending = False
            btn.auto_close_timer = None

            # Bersihkan icon statis dari Qt Designer (kalau ada) -- semua
            # device dirender lewat stylesheet background-image supaya
            # konsisten, tidak dobel sama property "icon" bawaan .ui.
            btn.setIcon(QIcon())

            # Inisialisasi Animasi GIF & Label Peluru
            btn.movie = None
            btn.gif_timer = QTimer(btn)
            btn.gif_timer.setSingleShot(True)

            if not hasattr(btn, "gif_label"):
                btn.gif_label = QLabel(btn)
                btn.gif_label.setAttribute(Qt.WA_TransparentForMouseEvents)
                btn.gif_label.setAlignment(Qt.AlignCenter)
                btn.gif_label.hide()

            if not hasattr(btn, "lbl_peluru"):
                btn.lbl_peluru = QLabel(btn)
                btn.lbl_peluru.setAttribute(Qt.WA_TransparentForMouseEvents)
                btn.lbl_peluru.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                btn.lbl_peluru.setStyleSheet("""
                            QLabel {
                                color: #FFFFFF;
                                font-family: 'Inter', sans-serif;
                                font-size: 13px;
                                font-weight: bold;
                                background-color: transparent;
                                border: none;
                                padding-right: 2px;
                            }
                        """)
                btn.lbl_peluru.hide()

            # Badge status berat live (FULL/HALF/EMPTY) -- cuma ada di
            # profil yang punya widget "label{locker_id}" di .ui-nya
            # (mis. AUG: labelE1, labelF3, dst). Glock tidak punya widget
            # ini sama sekali, jadi otomatis dilewati (hasattr False),
            # tidak perlu flag konfigurasi tambahan di DEVICE_PROFILES.
            badge_widget_name = f"label{name}"
            if hasattr(self, badge_widget_name):
                btn.status_badge = getattr(self, badge_widget_name)

            # Binding Method dari LockerButton (di DALAM loop -> berlaku
            # untuk semua tombol, bukan cuma yang terakhir)
            btn.update_icon = LockerButton.update_icon.__get__(btn, LockerButton)
            btn.toggle_relay = LockerButton.toggle_relay.__get__(btn, LockerButton)
            btn.show_warning_icon = LockerButton.show_warning_icon.__get__(btn, LockerButton)
            btn.play_gif = LockerButton.play_gif.__get__(btn, LockerButton)

            # --- TAMBAHKAN 2 BARIS INI ---
            btn.play_open_gif = LockerButton.play_open_gif.__get__(btn, LockerButton)
            btn.play_close_gif = LockerButton.play_close_gif.__get__(btn, LockerButton)

            btn.stop_gif = LockerButton.stop_gif.__get__(btn, LockerButton)
            btn._on_gif_finished = LockerButton._on_gif_finished.__get__(btn, LockerButton)
            btn.set_jumlah_peluru = LockerButton.set_jumlah_peluru.__get__(btn, LockerButton)
            btn.update_peluru_geometry = LockerButton.update_peluru_geometry.__get__(btn, LockerButton)

            btn.gif_timer.timeout.connect(btn._on_gif_finished)
            btn.clicked.connect(lambda _, b=btn: self.handle_locker_click(b))

    # ------------------------------------------------------------
    # Helper lookup berbasis locker_groups (menggantikan MAIN_LOCKERS/
    # EXPANSION_LOCKERS + get_module_id() global yang lama -- sekarang
    # generik untuk profil device manapun)
    # ------------------------------------------------------------
    def get_role_for_locker(self, locker_id):
        """Cari role Arduino (mis. 'MAIN_CONTROLLER', 'AUG_CONTROLLER')
        yang mengontrol locker_id tertentu, sesuai profil aktif."""
        for role, ids in self.locker_groups.items():
            if locker_id in ids:
                return role
        return None

    def get_module_id(self, locker_id):
        """Konversi locker_id ke nomor modul 1-N sesuai urutan di
        locker_groups[role] -- ini HARUS sama persis dengan urutan modul
        di firmware Arduino (module[i].ilsd = i+1) untuk role tsb."""
        role = self.get_role_for_locker(locker_id)
        if role is None:
            return None
        return self.locker_groups[role].index(locker_id) + 1

    def set_user(self, nrp, nama, id_locker=None, status=None):
        """Dipanggil saat login atau reset logout."""
        self.current_nrp = nrp
        self.current_nama = nama
        self.current_locker = id_locker
        self.current_status = status
        if hasattr(self, "lbUser"):
            self.lbUser.setText(nama if nama else "")

        self.locker_permissions()  # Update akses loker sesuai user baru

    def locker_permissions(self):
        """Mengaktifkan tombol loker khusus milik user, dan men-disable loker lainnya."""
        is_admin = self.current_status == "ADMIN"

        for loc, btn in self.locker_buttons.items():
            # Jika ADMIN, aktifkan semua tombol
            if is_admin:
                btn.setEnabled(True)
            # Jika USER biasa punya id_locker (misal: "A3"), CUMA aktifkan tombol A3
            elif self.current_locker:
                if loc == self.current_locker:
                    btn.setEnabled(True)
                else:
                    btn.setEnabled(False)
            # Jika user tidak login / tidak punya id_locker (NULL), aktifkan semua / sesuaikan kebutuhan
            else:
                btn.setEnabled(True)

    def showEvent(self, event):
        self.load_data_from_db()
        super().showEvent(event)

    def load_data_from_db(self):
        """Membaca data kondisi awal loker dari database MySQL."""
        try:
            # Reset state awal. SENGAJA TIDAK reset is_open_pending di sini
            # -- itu status logis in-memory (tidak disimpan di tb_data).
            for btn in self.locker_buttons.values():
                btn.berat = "C"
                btn.jumlah_peluru = 0
                btn.relay = 0
                btn.limit_switch = 0

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id_locker, berat, jumlah_peluru, limit_switch, relay FROM"
                " tb_data WHERE gudang=%s",
                (self.gudang,),
            )
            rows = cursor.fetchall()

            for row in rows:
                if row["id_locker"] in self.locker_buttons:
                    btn = self.locker_buttons[row["id_locker"]]
                    btn.berat = (str(row["berat"]).strip().upper() if row["berat"] else "C")
                    peluru_val = (int(row["jumlah_peluru"]) if row["jumlah_peluru"] is not None else 0)
                    btn.limit_switch = (int(row["limit_switch"]) if row["limit_switch"] is not None else 0)
                    btn.relay = int(row["relay"]) if row["relay"] is not None else 0
                    btn.set_jumlah_peluru(peluru_val)

            cursor.close()
            conn.close()

            for btn in self.locker_buttons.values():
                btn.update_icon()

            self.update_stats()
            print(f"Load data loker dari Database berhasil. (gudang={self.gudang})")

        except Exception as e:
            print(f"Gagal load data loker dari DB: {e}")

    def update_stats(self):
        """Menghitung ringkasan statistik dan memperbarui tampilan UI."""
        total = len(self.locker_buttons)
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

        if hasattr(self, "statTotal"):
            self.statTotal.setText(f"📦 Total: {total}")
        if hasattr(self, "statFilled"):
            self.statFilled.setText(f"🔒 Terisi: {filled}")
        if hasattr(self, "statEmpty"):
            self.statEmpty.setText(f"📥 Kosong: {empty}")
        if hasattr(self, "statAlert"):
            self.statAlert.setText(f"⚠️ Alert: {alert}")
        if hasattr(self, "statPercent"):
            self.statPercent.setText(f"{percent}% Terisi")

    def handle_locker_click(self, btn):
        """Event klik tombol loker: toggle relay, update DB, dan kirim perintah serial."""
        new_relay = btn.toggle_relay()

        if hasattr(btn, "auto_close_timer") and btn.auto_close_timer:
            btn.auto_close_timer.stop()

        if new_relay == 1:
            btn.is_open_pending = True
            btn.is_unlocking_grace = True
            QTimer.singleShot(5000, lambda b=btn: self.end_unlock_pulse(b))

            send_log(
                kategori="LOCKER",
                aktivitas="locker_open",
                detail=f"Locker {btn.locker_id} opened",
                locker_id=btn.locker_id,
                nrp=self.current_nrp,
                nama=self.current_nama,
                gudang=self.gudang,
                metode="manual"
            )

            # btn.play_gif("assets/state/open.gif", duration_ms=0)
            btn.play_open_gif(duration_ms=0)

            if not hasattr(btn, "auto_close_timer") or btn.auto_close_timer is None:
                btn.auto_close_timer = QTimer(self)
                btn.auto_close_timer.setSingleShot(True)

            try:
                btn.auto_close_timer.timeout.disconnect()
            except Exception:
                pass

            def on_10_second_timeout(target_btn=btn):
                if target_btn.is_open_pending:
                    print(f"⚠️ Warning 10 Detik: Loker {target_btn.locker_id} belum ditutup!")
                    target_btn.play_close_gif(  duration_ms=0, bg_color="#991B1B", border_color="#EF4444",  )

                    send_log(
                        kategori="LOCKER",
                        aktivitas="locker_warning",
                        detail=f"Locker {target_btn.locker_id} warning: not closed within 10 seconds",
                        locker_id=target_btn.locker_id,
                        nrp=self.current_nrp,
                        nama=self.current_nama,
                        gudang=self.gudang,
                        metode="manual"
                    )
                    
                    if self.serial:
                        role = self.get_role_for_locker(target_btn.locker_id)
                        module_id = self.get_module_id(target_btn.locker_id)
                        if role and module_id is not None:
                            self.serial.send_command_to(role, f"WARN:{module_id}")

            btn.auto_close_timer.timeout.connect(on_10_second_timeout)
            btn.auto_close_timer.start(10000)
        else:
            btn.is_open_pending = False
            btn.is_unlocking_grace = False
            btn.stop_gif()
            btn.update_icon()

        # Update Database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = ("UPDATE tb_data SET relay = %s WHERE id_locker = %s AND gudang=%s")
            cursor.execute(query, (new_relay, btn.locker_id, self.gudang))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Gagal update DB: {e}")

        self.log_locker_activity(btn.locker_id, btn.berat, btn.limit_switch, new_relay)
        self.update_stats()
        self.send_lock_command()

    def end_unlock_pulse(self, btn):
        """Dipanggil otomatis 5 detik setelah locker diklik-buka. Mematikan
        SINYAL LISTRIK relay/solenoid (pulse, bukan sustained). TIDAK
        mengubah status logis is_open_pending / ikon / animasi."""
        btn.is_unlocking_grace = False

        if btn.relay != 1:
            return

        btn.relay = 0

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tb_data SET relay = %s WHERE id_locker = %s AND gudang=%s",
                (0, btn.locker_id, self.gudang),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Gagal update DB (auto pulse-off relay): {e}")

        self.log_locker_activity(btn.locker_id, btn.berat, btn.limit_switch, 0)
        self.send_lock_command()

    def send_lock_command(self):
        """Kirim bit relay biner ke SETIAP role Arduino sesuai locker_groups
        pada profil aktif -- generik untuk berapa pun jumlah controller."""
        if not self.serial:
            return

        for role, locker_ids in self.locker_groups.items():
            bits = "".join(str(self.locker_buttons[loc].relay) for loc in locker_ids)
            self.serial.send_command_to(role, bits)
            print(f"Command -> {role}: {bits}")

    def handle_serial_data(self, role, tag, value):
        """Router terpusat untuk memproses data sensor loker."""
        # FILTER KETAT: Abaikan jika bukan tag LOCKER atau role tidak
        # dikenal di profil aktif.
        if tag != "LOCKER" or role not in self.locker_groups:
            return

        raw = value.strip()
        if not raw:
            return

        parts = [p.strip() for p in raw.split(",") if p.strip() != ""]

        if len(parts) % 5 != 0:
            print(f"⚠️ Format data locker dari {role} tidak valid: {raw} (Total elemen: {len(parts)})")
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            relay_changed_to_lock = False

            for i in range(0, len(parts), 5):
                locker_id = parts[i]
                berat = parts[i + 1]

                val_peluru = parts[i + 2]
                jumlah_peluru = (int(val_peluru) if val_peluru.lstrip("-").isdigit() else 0)

                limit_switch = (int(parts[i + 3]) if parts[i + 3].isdigit() else 0)
                relay = (int(parts[i + 4]) if parts[i + 4].isdigit() else 0)

                if locker_id in self.locker_buttons:
                    btn = self.locker_buttons[locker_id]

                    berubah = (
                        btn.berat != berat
                        or btn.jumlah_peluru != jumlah_peluru
                        or btn.limit_switch != limit_switch
                        or btn.relay != relay
                    )

                    btn.set_jumlah_peluru(jumlah_peluru)

                    if (
                        limit_switch == 1
                        and getattr(btn, "is_open_pending", False)
                        and not getattr(btn, "is_unlocking_grace", False)
                    ):
                        if hasattr(btn, "auto_close_timer") and btn.auto_close_timer:
                            btn.auto_close_timer.stop()
                        btn.stop_gif()
                        btn.relay = 0
                        btn.is_open_pending = False
                        relay_changed_to_lock = True

                    btn.berat = berat
                    btn.limit_switch = limit_switch

                    if not getattr(btn, "is_warning", False) and (
                        not btn.movie or btn.movie.state() == 0
                    ):
                        btn.update_icon()

                    query = (
                        "UPDATE tb_data SET berat = %s, limit_switch = %s, relay = %s,"
                        " jumlah_peluru = %s WHERE id_locker = %s AND gudang =%s"
                    )
                    cursor.execute(query, (berat, limit_switch, btn.relay, btn.jumlah_peluru, locker_id, self.gudang,),)

                if berubah:
                    self.log_locker_activity(locker_id, berat, limit_switch, btn.relay)

            conn.commit()
            cursor.close()
            conn.close()

            if relay_changed_to_lock:
                self.send_lock_command()

            self.update_stats()

        except Exception as e:
            print(f"Gagal update data locker dari {role}: {e}")

    def log_locker_activity(self, id_locker, berat, limit_switch, relay):
        """Menyimpan riwayat perubahan status loker ke tabel tb_log_locker."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                        INSERT INTO tb_log_locker (id_locker, nrp, nama, berat, limit_switch, relay, gudang)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
            cursor.execute(query, (id_locker, self.current_nrp, self.current_nama, berat, limit_switch, relay, self.gudang,),)
            conn.commit()
            cursor.close()
            conn.close()
            print(f"Log saved: {id_locker} -> berat={berat}, limit={limit_switch}, relay={relay}")
        except Exception as e:
            print(f"Gagal simpan log locker: {e}")

    def handle_logout(self):
        """Validasi agar semua loker sudah tertutup rapat sebelum logout."""
        open_lockers = [
            btn for btn in self.locker_buttons.values() if getattr(btn, "is_open_pending", False)
        ]

        if open_lockers:
            list_ids = ", ".join([btn.locker_id for btn in open_lockers])
            msg = DbMessage(
                self,
                title="Logout Ditolak",
                message=(
                    "Loker berikut masih terbuka secara fisik: "
                    f"{list_ids}. Silakan tutup loker tersebut!"
                ),
                success=False,
            )
            msg.exec_()
            for btn in open_lockers:
                btn.show_warning_icon()
            return

        print("Logout berhasil...")
        send_log(
            kategori="user_auth",
            aktivitas="system_shutdown",
            detail=f"User {self.current_nrp} ({self.current_nama}) logged out",
            locker_id=None,
            nrp=self.current_nrp,
            nama=self.current_nama,
            gudang=self.gudang,
            metode="manual"
        )
        if self.serial and hasattr(self.serial, 'get_main_role_for_gudang'):
            target_role = self.serial.get_main_role_for_gudang()
        else:
            target_role = "MAIN_CONTROLLER"

        if self.serial:
            self.serial.send_command_to(target_role, "beeptrue")
        self.logout_signal.emit()