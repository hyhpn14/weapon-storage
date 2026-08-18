import time
import re
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, QTimer, pyqtSignal

# Saklar debug: set True kalau butuh lihat lagi data mentah tiap baris
# yang masuk dari Arduino (berguna saat troubleshooting hardware).
# Default False supaya terminal tidak penuh log saat pemakaian normal.
DEBUG_RAW_DATA = False


class SingleArduinoThread(QThread):
    """Thread khusus untuk menangani 1 port serial Arduino secara independen."""

    internal_data_received = pyqtSignal(str, str, str)
    # Sinyal tambahan HANYA untuk memberi tahu status koneksi ke UI
    connection_changed = pyqtSignal(str, bool)

    def __init__(self, port, baudrate=115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.role = 'UNKNOWN'  # Default sebelum teridentifikasi
        self.ser = None
        self.running = True
        self.is_connected = False

    def process_incoming_line(self, raw_line):
        """Memproses string yang diterima dari serial dan memperbarui identitas."""
        line = raw_line.strip()
        if not line:
            return

        if DEBUG_RAW_DATA:
            print(f"[{self.role}] Data Mentah Arduino: {line}")

        # 1. Deteksi Handshake Resmi (IDENTITY:MAIN_CONTROLLER atau IDENTITY:LOCKER_EXPANSION)
        if 'IDENTITY:' in line:
            self.role = line.split('IDENTITY:', 1)[1].strip()
            print(f"[Serial] Port {self.port} teridentifikasi via Handshake sebagai: {self.role}")
            self.connection_changed.emit(self.role, True)
            return

        # 2. Auto-Recovery: Identifikasi dari payload jika Handshake terlewat
        if self.role == 'UNKNOWN':
            if 'A1,' in line or 'B1,' in line or line.startswith('[RFID]') or 'RFID:' in line:
                self.role = 'MAIN_CONTROLLER'
                print(f"[Serial] Auto-assign Port {self.port} sebagai: MAIN_CONTROLLER")
                self.connection_changed.emit(self.role, True)
            elif 'C1,' in line or 'D1,' in line:
                self.role = 'LOCKER_EXPANSION'
                print(f"[Serial] Auto-assign Port {self.port} sebagai: LOCKER_EXPANSION")
                self.connection_changed.emit(self.role, True)

        # 3. Handling Khusus Response RFID dari Arduino
        if line.startswith("RFID:"):
            # Membersihkan spasi pada format "RFID: 0A 1B 2C 3D 4E" -> "0A1B2C3D4E"
            raw_uid = line.split("RFID:", 1)[1].strip()
            clean_uid = raw_uid.replace(" ", "").upper()
            self.internal_data_received.emit(self.role, "RFID", clean_uid)
            return

        if line.startswith("[RFID]"):
            # Menangkap log status seperti "[RFID] SCAN" atau "[RFID] Timeout..."
            status_text = line.replace("[RFID]", "").strip()
            self.internal_data_received.emit(self.role, "RFID_STATUS", status_text)
            return

        # 4. Parsing Tag & Value Standar
        if ':' in line:
            tag, value = line.split(':', 1)
            tag = tag.strip()
            value = value.strip()
        elif re.match(r'^[A-D]\d,', line):
            # Data locker dari Arduino TIDAK punya prefix "TAG:", cuma CSV
            # mentah seperti "A1,C,00,0,B1,A,17,1,0,...". Tanpa deteksi ini,
            # baris ini jatuh ke tag='INFO' di bawah dan tidak akan pernah
            # sampai ke Home.handle_serial_data() yang cuma terima
            # tag=="LOCKER".
            tag, value = 'LOCKER', line
        else:
            tag, value = 'INFO', line

        # Emit data bersama role yang sudah ter-update
        self.internal_data_received.emit(self.role, tag, value)

    def run(self):
        while self.running:
            # 1. Buka Port SAJA (cek koneksi fisik). TIDAK ada command apa pun
            # yang dikirim ke Arduino di sini -> identitas (WHO_ARE_YOU) baru
            # diminta belakangan lewat request_identity(), dipicu MainApp
            # saat user masuk layar Login.
            if not self.ser or not self.ser.is_open:
                if self.is_connected:
                    was_role = self.role
                    self.is_connected = False
                    self.connection_changed.emit(was_role, False)

                try:
                    self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
                    time.sleep(2)  # Tunggu Arduino auto-reset selesai

                    # Bersihkan buffer sisa booting
                    self.ser.reset_input_buffer()

                    # Port berhasil dibuka = "koneksi port" terdeteksi.
                    # Ini SENGAJA tidak lagi mengirim WHO_ARE_YOU di sini.
                    self.is_connected = True
                    print(f"[Serial] Port {self.port} terbuka (belum handshake identitas).")

                except Exception as e:
                    self.is_connected = False
                    self.cleanup()

                if not self.is_connected:
                    time.sleep(3)
                    continue

            # 2. Baca Stream Data Rutin
            try:
                if self.ser and self.ser.in_waiting > 0:
                    raw = self.ser.readline().decode('utf-8', errors='ignore')
                    self.process_incoming_line(raw)

            except (serial.SerialException, OSError) as e:
                print(f'[{self.role}] Koneksi Terputus di {self.port}: {e}')

                # JIKA KABEL DICABUT -> BERI TAHU UI BAHWA CONTROLLER DISCONNECTED!
                was_role = self.role
                self.is_connected = False
                if was_role != 'UNKNOWN':
                    self.connection_changed.emit(was_role, False)

                self.cleanup()
                time.sleep(1)

        self.cleanup()

    def request_identity(self):
        """Kirim WHO_ARE_YOU on-demand. Dipanggil MainApp saat user masuk
        layar Login -> ini satu-satunya command yang dikirim SEBELUM login."""
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b'WHO_ARE_YOU\n')
                print(f'[{self.port}] Mengirim WHO_ARE_YOU (identity request)')
            except Exception as e:
                print(f'[{self.port}] Gagal kirim WHO_ARE_YOU: {e}')

    def send_command(self, command, data=None):
        if self.ser and self.ser.is_open:
            try:
                payload = f'{command}{data}\n' if data else f'{command}\n'
                self.ser.write(payload.encode())
                print(f'[{self.role}] Kirim Command -> {payload.strip()}')
            except Exception as e:
                print(f'[{self.role}] Gagal kirim command: {e}')

    def cleanup(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass


class SerialHandler:
    """Manager Class untuk mengatur Arduino Utama & Arduino Ekspansi Locker.
    Mendukung hot-plug: port baru yang dicolok SETELAH app jalan akan
    otomatis terdeteksi lewat scan berkala, tanpa perlu restart aplikasi."""

    # Kata kunci description port yang dianggap perangkat Arduino/serial kita.
    DEVICE_KEYWORDS = (
        'arduino', 'ch340', 'usb serial', 'usb-serial', 'usb', 'ftdi', 'cp210'
    )

    def __init__(self, baudrate=115200):
        self.baudrate = baudrate
        self.threads = []
        self.on_data_received_callback = None
        self.on_connection_changed_callback = None
        self.hotplug_timer = None

        # False = belum boleh kirim command apa pun ke Arduino manapun,
        # termasuk yang baru dicolok (state sebelum user sampai Login).
        # Diset True oleh MainApp begitu user pertama kali masuk Login,
        # dan sejak itu SELALU True (device baru yang dicolok setelahnya
        # boleh langsung di-identify otomatis).
        self.identity_gate_open = False

    def start(self, callback_func, callback_conn_func=None, hotplug_interval_ms=3000):
        self.on_data_received_callback = callback_func
        self.on_connection_changed_callback = callback_conn_func

        # Scan awal (perangkat yang sudah tercolok sebelum app dibuka)
        self._scan_and_attach_new_ports()

        # Scan berkala -> ini yang bikin hot-plug bekerja. Kalau Arduino
        # dicolok belakangan (port baru muncul), akan otomatis kedeteksi
        # dan langsung disambungkan di scan berikutnya (maks. delay
        # sebesar hotplug_interval_ms).
        self.hotplug_timer = QTimer()
        self.hotplug_timer.timeout.connect(self._scan_and_attach_new_ports)
        self.hotplug_timer.start(hotplug_interval_ms)

    def _scan_and_attach_new_ports(self):
        """Cek port yang tersedia sekarang, bandingkan dengan yang sudah
        kita punya thread-nya, lalu sambungkan yang benar-benar baru."""
        try:
            ports = serial.tools.list_ports.comports()
        except Exception as e:
            print(f"[SerialManager] Gagal scan port: {e}")
            return

        known_ports = {t.port for t in self.threads}
        detected_new = []

        for p in ports:
            if p.device in known_ports:
                continue  # port ini sudah punya thread (baik masih hidup atau lagi retry-connect)

            if any(k in (p.description or '').lower() for k in self.DEVICE_KEYWORDS):
                detected_new.append(p.device)
                t = SingleArduinoThread(p.device, self.baudrate)
                t.internal_data_received.connect(self.on_data_received_callback)

                if self.on_connection_changed_callback:
                    t.connection_changed.connect(self.on_connection_changed_callback)

                self.threads.append(t)
                t.start()

                # Kalau gerbang login SUDAH pernah dibuka (user sudah pernah
                # sampai Login sebelumnya), device yang baru dicolok ini
                # boleh langsung di-identify otomatis begitu portnya kebuka
                # (beri jeda supaya thread sempat selesai buka port).
                # Kalau gerbang BELUM dibuka, device ini cuma disambungkan
                # secara pasif -- tidak ada command terkirim, sampai user
                # nanti masuk Login dan broadcast_identity_request() jalan.
                if self.identity_gate_open:
                    QTimer.singleShot(
                        2500,
                        lambda th=t: th.request_identity() if th.is_connected else None,
                    )

        if detected_new:
            print(f"[SerialManager] Perangkat baru terdeteksi & disambungkan: {', '.join(detected_new)}")

    def broadcast_identity_request(self):
        """Minta semua Arduino yang portnya sudah terbuka untuk kenalan
        (WHO_ARE_YOU). Dipanggil sekali oleh MainApp saat user pertama kali
        masuk layar Login. Return True kalau minimal 1 request terkirim."""
        sent_any = False
        for t in self.threads:
            if t.is_connected:
                t.request_identity()
                sent_any = True
        return sent_any

    def send_command_to(self, target_role, command, data=None):
        """Mengirim perintah berdasarkan peran: 'MAIN_CONTROLLER' atau 'LOCKER_EXPANSION'"""
        for t in self.threads:
            if t.role == target_role and t.is_connected:
                t.send_command(command, data)
                return True
        print(f'[SerialManager] Perangkat {target_role} tidak ditemukan/offline.')
        return False

    def stop(self):
        if self.hotplug_timer:
            self.hotplug_timer.stop()

        for t in self.threads:
            t.running = False
            t.wait()