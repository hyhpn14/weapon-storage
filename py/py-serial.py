import sys
import time
import threading
import serial
import serial.tools.list_ports

class StandaloneSerialTester:
    SCAN_TIMEOUT_SEC = 10
    MAX_ATTEMPTS = 3

    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = True
        self.is_finished = False
        self.mode = None

        # RFID State
        self.scan_attempts = 0
        self.last_attempt_time = 0

    def find_arduino_port(self):
        """Mencari port serial USB yang terhubung secara otomatis."""
        ports = serial.tools.list_ports.comports()
        for p in ports:
            # Mencari devicename khas Arduino / FTDI / CH340 / USB Serial
            desc = (p.description or '').lower()
            if any(k in desc for k in ['arduino', 'ch340', 'usb serial', 'usb-serial', 'usb', 'ftdi', 'cp210']) or 'ttyusb' in p.device.lower() or 'ttyacm' in p.device.lower():
                print(f"[SYSTEM] Port terdeteksi otomatis: {p.device}")
                return p.device
        return None

    def connect(self):
        """Membuka koneksi serial murni."""
        if not self.port:
            self.port = self.find_arduino_port()

        if not self.port:
            print("[ERROR] Port serial tidak ditemukan! Pastikan Arduino terhubung.")
            return False

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Delay reset serial Arduino
            self.ser.reset_input_buffer()
            print(f"[SYSTEM] Terhubung ke {self.port} pada baudrate {self.baudrate}")
            return True
        except Exception as e:
            print(f"[ERROR] Gagal membuka port {self.port}: {e}")
            return False

    def send_cmd(self, command):
        """Mengirim string perintah langsung ke serial Arduino (TX)."""
        if self.ser and self.ser.is_open:
            try:
                payload = f"{command}\n"
                self.ser.write(payload.encode('utf-8'))
                print(f"[TX]: {command}")
            except Exception as e:
                print(f"[ERROR TX]: {e}")

    def read_serial_loop(self):
        """Thread latar belakang untuk membaca data serial secara berlanjut (RX)."""
        while self.running and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting > 0:
                    raw_line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if raw_line:
                        self.handle_incoming_line(raw_line)
            except Exception as e:
                print(f"[ERROR RX]: {e}")
                break
            time.sleep(0.01)

    def handle_incoming_line(self, line):
        """Memproses parsing string mentah yang diterima dari Arduino."""
        print(f"\n[RX Mentah]: {line}")

        # Parsing format standar Tag:Value atau Format RFID/Fingerprint
        tag, value = "INFO", line
        if ":" in line:
            parts = line.split(":", 1)
            tag, value = parts[0].strip(), parts[1].strip()

        # Processing Fingerprint
        if self.mode == "finger":
            if tag in ("FP", "FINGER") or "MATCH" in line:
                if "MATCH" in line:
                    print(f"[RESULT] ✅ Fingerprint Cocok! Detail: {line}")
                    self.send_cmd("beeptrue")
                    self.stop_scanning()
                    self.is_finished = True
                elif "NOMATCH" in line:
                    print("[RESULT] ❌ Fingerprint tidak cocok!")
                    self.send_cmd("beepfail")

        # Processing RFID
        elif self.mode == "rfid":
            if line.startswith("RFID:") or tag == "RFID":
                uid = value.replace(" ", "").upper()
                print(f"[RESULT] ✅ RFID Card Scanned! UID: {uid}")
                self.send_cmd("beeptrue")
                self.stop_scanning()
                self.is_finished = True

    def start(self, mode="finger"):
        """Memulai sesi uji coba CLI."""
        self.mode = mode.lower()
        self.is_finished = False
        self.scan_attempts = 0

        print(f"\n==================================================")
        print(f"  PURE SERIAL CLI TEST: {self.mode.upper()}")
        print(f"==================================================")

        if self.mode == "finger":
            self.send_cmd("v")
            self.send_cmd("beep")
            print("[INFO] Perintah 'v' & 'beep' terkirim. Tempelkan jari...")

        elif self.mode == "rfid":
            self.send_cmd("beep")
            self._start_rfid_attempt()

        elif self.mode == "pin":
            self.send_cmd("beep")
            print("[INFO] Masukkan PIN di terminal untuk simulasi respon ke Arduino...")

    def _terminal_input_loop(self):
        """Menangkap input perintah manual dari pengguna melalui terminal."""
        while not self.is_finished and self.running:
            try:
                prompt = "[PIN Test]: " if self.mode == "pin" else "[Kirim Custom TX]: "
                cmd = input(prompt).strip()

                if not cmd:
                    continue

                if cmd.lower() in ("exit", "quit", "q"):
                    print("[INFO] Dihentikan oleh pengguna.")
                    self.stop_scanning()
                    self.is_finished = True
                    break

                if self.mode == "pin":
                    print(f"[SIMULASI] PIN '{cmd}' dimasukkan -> Kirim 'beeptrue'")
                    self.send_cmd("beeptrue")
                    self.is_finished = True
                else:
                    self.send_cmd(cmd)

            except (EOFError, KeyboardInterrupt):
                self.is_finished = True
                break

    def _start_rfid_attempt(self):
        self.scan_attempts += 1
        if self.scan_attempts == 1:
            print("[INFO] Tempelkan kartu RFID...")
        else:
            print(f"[INFO] Kartu tidak terdeteksi, mencoba lagi... ({self.scan_attempts}/{self.MAX_ATTEMPTS})")

        self.send_cmd("r")
        self.last_attempt_time = time.time()

    def update_timeout(self):
        if self.mode == "rfid" and not self.is_finished:
            if time.time() - self.last_attempt_time > self.SCAN_TIMEOUT_SEC:
                if self.scan_attempts < self.MAX_ATTEMPTS:
                    self._start_rfid_attempt()
                else:
                    print(f"\n[RESULT] ❌ Timeout RFID tercapai.")
                    self.stop_scanning()
                    self.is_finished = True

    def stop_scanning(self):
        if self.mode in ("finger", "rfid"):
            self.send_cmd("s")

    def close(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[SYSTEM] Port Serial ditutup.")


if __name__ == "__main__":
    # Tentukan port spesifik jika auto-detect tidak digunakan, contoh: "/dev/ttyUSB0" atau "COM3"
    PORT_TARGET = "/dev/ttyUSB0" 
    TEST_MODE = "finger" # Opsi: "finger", "rfid", "pin"

    tester = StandaloneSerialTester(port=PORT_TARGET, baudrate=115200)

    if tester.connect():
        # Menjalankan thread pembacaan RX serial secara independen
        rx_thread = threading.Thread(target=tester.read_serial_loop, daemon=True)
        rx_thread.start()

        # Jalankan logika alur tes
        tester.start(mode=TEST_MODE)

        # Menjalankan thread untuk menangkap input ketikan terminal
        tx_thread = threading.Thread(target=tester._terminal_input_loop, daemon=True)
        tx_thread.start()

        # Loop pengunci utama
        try:
            while not tester.is_finished:
                tester.update_timeout()
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[INFO] Dihentikan paksa via Ctrl+C")
        finally:
            tester.stop_scanning()
            tester.close()