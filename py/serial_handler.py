import time
import re
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, QTimer, pyqtSignal
from log_client import send_log

DEBUG_RAW_DATA = False

DEFAULT_GUDANG = "GLOCK17"


class SingleArduinoThread(QThread):
    """Thread khusus untuk menangani 1 port serial Arduino secara independen."""

    internal_data_received = pyqtSignal(str, str, str)
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

        # 1. Deteksi Handshake Resmi (IDENTITY:MAIN_CONTROLLER, IDENTITY:AUG_CONTROLLER, dll)
        if 'IDENTITY:' in line:
            self.role = line.split('IDENTITY:', 1)[1].strip()
            print(f"[Serial] Port {self.port} teridentifikasi via Handshake sebagai: {self.role}")
            self.connection_changed.emit(self.role, True)

            send_log(
                kategori="Sensor",
                aktivitas="serial_connected",
                detail=f"Arduino Port {self.port} berhasil Handshake sebagai [{self.role}]",
                metode="HANDSHAKE",
                status="success"
            )
            return

        # 2. Auto-Recovery: Identifikasi dari payload jika Handshake terlewat
        if self.role == 'UNKNOWN':
            if 'A1,' in line or 'B1,' in line or line.startswith('[RFID]') or 'RFID:' in line:
                self.role = 'MAIN_CONTROLLER'
                print(f"[Serial] Auto-assign Port {self.port} sebagai: MAIN_CONTROLLER")
                self.connection_changed.emit(self.role, True)
                send_log(
                    kategori="Sensor",
                    aktivitas="serial_auto_assigned",
                    detail=f"Port {self.port} auto-assigned sebagai MAIN_CONTROLLER",
                    metode="PAYLOAD",
                    status="warning"
                )
            elif 'C1,' in line or 'D1,' in line:
                self.role = 'LOCKER_EXPANSION'
                print(f"[Serial] Auto-assign Port {self.port} sebagai: LOCKER_EXPANSION")
                self.connection_changed.emit(self.role, True)
                send_log(
                    kategori="Sensor",
                    aktivitas="serial_auto_assigned",
                    detail=f"Port {self.port} auto-assigned sebagai LOCKER_EXPANSION",
                    metode="PAYLOAD",
                    status="warning"
                )
            elif 'E1,' in line or 'F1,' in line:
                self.role = 'AUG_CONTROLLER'
                print(f"[Serial] Auto-assign Port {self.port} sebagai: AUG_CONTROLLER")
                self.connection_changed.emit(self.role, True)
                send_log(
                    kategori="Sensor",
                    aktivitas="serial_auto_assigned",
                    detail=f"Port {self.port} auto-assigned sebagai AUG_CONTROLLER",
                    metode="PAYLOAD",
                    status="warning"
                )

        # 3. Handling Khusus Response RFID dari Arduino
        if line.startswith("RFID:"):
            raw_uid = line.split("RFID:", 1)[1].strip()
            clean_uid = raw_uid.replace(" ", "").upper()
            self.internal_data_received.emit(self.role, "RFID", clean_uid)
            return

        if line.startswith("[RFID]"):
            status_text = line.replace("[RFID]", "").strip()
            self.internal_data_received.emit(self.role, "RFID_STATUS", status_text)
            return

        # 4. Parsing Tag & Value Standar
        if ':' in line:
            tag, value = line.split(':', 1)
            tag = tag.strip()
            value = value.strip()

            if tag in ["ERROR", "FAULT", "ALERT"]:
                send_log(
                    kategori="Sensor",
                    aktivitas="serial_error",
                    detail=f"Alert dari [{self.role}]: {value}",
                    status="danger"
                )

        elif re.match(r'^[A-F]\d,', line):
            tag, value = 'LOCKER', line
        else:
            tag, value = 'INFO', line

        self.internal_data_received.emit(self.role, tag, value)

    def run(self):
        while self.running:
            if not self.ser or not self.ser.is_open:
                if self.is_connected:
                    was_role = self.role
                    self.is_connected = False
                    self.connection_changed.emit(was_role, False)

                try:
                    self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
                    time.sleep(2)
                    self.ser.reset_input_buffer()
                    self.is_connected = True
                    print(f"[Serial] Port {self.port} terbuka (belum handshake identitas).")

                except Exception as e:
                    self.is_connected = False
                    self.cleanup()

                if not self.is_connected:
                    time.sleep(3)
                    continue

            try:
                if self.ser and self.ser.in_waiting > 0:
                    raw = self.ser.readline().decode('utf-8', errors='ignore')
                    self.process_incoming_line(raw)

            except (serial.SerialException, OSError) as e:
                print(f'[{self.role}] Koneksi Terputus di {self.port}: {e}')
                was_role = self.role
                self.is_connected = False
                if was_role != 'UNKNOWN':
                    self.connection_changed.emit(was_role, False)

                send_log(
                    kategori="sensor",
                    aktivitas="serial_error",
                    detail=f"Koneksi Serial [{was_role}] di Port {self.port} terputus: {e}",
                    status="danger"
                )

                self.cleanup()
                time.sleep(1)

        self.cleanup()

    def request_identity(self):
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
    """Manager Class untuk mengatur seluruh Arduino (Glock / AUG)."""

    # ============================================================
    # PROFIL PER-DEVICE (PUSAT PEMETAAN CONTROLLER)
    # ============================================================
    # Role pertama di dalam daftar setiap gudang otomatis dianggap
    # sebagai Main Controller/Primary Unit untuk gudang tersebut.
    DEVICE_PROFILES = {
        "GLOCK17": {
            "MAIN_CONTROLLER": ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"],
            "LOCKER_EXPANSION": ["C1", "C2", "C3", "C4", "C5", "D1", "D2", "D3", "D4", "D5"],
        },
        "AUGSTYER": {
            "AUG_CONTROLLER": ["E1", "E2", "E3", "E4", "E5", "F1", "F2", "F3", "F4", "F5"],
        },
    }

    DEVICE_KEYWORDS = (
        'arduino', 'ch340', 'usb serial', 'usb-serial', 'usb', 'ftdi', 'cp210'
    )

    def __init__(self, baudrate=115200, gudang="GLOCK17"):
        self.baudrate = baudrate
        self.gudang = gudang
        self.threads = []
        self.on_data_received_callback = None
        self.on_connection_changed_callback = None
        self.hotplug_timer = None
        self.identity_gate_open = False

    def set_gudang(self, gudang):
        """Metode untuk memperbarui gudang aktif secara dinamis."""
        self.gudang = gudang

    def get_main_role_for_gudang(self):
        """Mendapatkan role utama berdasarkan gudang yang aktif."""
        profile = self.DEVICE_PROFILES.get(self.gudang, self.DEVICE_PROFILES[DEFAULT_GUDANG])
        return list(profile.keys())[0]

    def start(self, callback_func, callback_conn_func=None, hotplug_interval_ms=3000):
        self.on_data_received_callback = callback_func
        self.on_connection_changed_callback = callback_conn_func

        self._scan_and_attach_new_ports()

        self.hotplug_timer = QTimer()
        self.hotplug_timer.timeout.connect(self._scan_and_attach_new_ports)
        self.hotplug_timer.start(hotplug_interval_ms)

    def _scan_and_attach_new_ports(self):
        try:
            ports = serial.tools.list_ports.comports()
        except Exception as e:
            print(f"[SerialManager] Gagal scan port: {e}")
            return

        known_ports = {t.port for t in self.threads}
        detected_new = []

        for p in ports:
            if p.device in known_ports:
                continue

            if any(k in (p.description or '').lower() for k in self.DEVICE_KEYWORDS):
                detected_new.append(p.device)
                t = SingleArduinoThread(p.device, self.baudrate)
                t.internal_data_received.connect(self.on_data_received_callback)

                if self.on_connection_changed_callback:
                    t.connection_changed.connect(self.on_connection_changed_callback)

                self.threads.append(t)
                t.start()

                if self.identity_gate_open:
                    QTimer.singleShot(
                        2500,
                        lambda th=t: th.request_identity() if th.is_connected else None,
                    )

        if detected_new:
            print(f"[SerialManager] Perangkat baru terdeteksi & disambungkan: {', '.join(detected_new)}")

    def broadcast_identity_request(self):
        sent_any = False
        for t in self.threads:
            if t.is_connected:
                t.request_identity()
                sent_any = True
        return sent_any

    def send_command_to(self, target_role, command, data=None):
        """
        Mengirim perintah ke target_role.
        Jika target 'MAIN_CONTROLLER' dipanggil tetapi perangkat fisik tidak ada,
        otomatis mengalihkan perintah ke controller utama profil gudang aktif (misal: AUG_CONTROLLER).
        """
        actual_target = target_role
        
        # Jika UI meminta 'MAIN_CONTROLLER', dapatkan role controller utama sesuai profil gudang
        if target_role == "MAIN_CONTROLLER":
            actual_target = self.get_main_role_for_gudang()

        # 1. Pencarian Persis (Actual Target atau Target Role Asli)
        for t in self.threads:
            if (t.role == actual_target or t.role == target_role) and t.is_connected:
                t.send_command(command, data)
                return True

        # 2. Fallback: Jika target spesifik tidak ada, kirim ke controller manapun yang online
        for t in self.threads:
            if t.is_connected:
                print(f"[SerialManager] Target '{target_role}' tidak ditemukan. Fallback kirim '{command}' ke {t.role}")
                t.send_command(command, data)
                return True

        print(f'[SerialManager] Perangkat {target_role} ({actual_target}) tidak ditemukan/offline.')
        return False

    def stop(self):
        if self.hotplug_timer:
            self.hotplug_timer.stop()

        for t in self.threads:
            t.running = False
            t.wait()