from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QIcon
from PyQt5.uic import loadUi
import geocoder
import requests, socket
from pulsing_widget import PulsingStatusBadge
from db_config import get_db_connection


DEVICE_PROFILES = {
    "GLOCK17": ["MAIN_CONTROLLER", "LOCKER_EXPANSION"],
    "AUGSTYER": ["AUG_CONTROLLER"],
}

class Saver(QMainWindow):
    go_to_login = pyqtSignal()
    
    def __init__(self, clock_helper, serial_handler=None):
        super().__init__()
        loadUi("ui2/saverr.ui", self)

        self.serial = serial_handler
        # Tracking status lampu (False = Mati, True = Menyala)
        self.is_lamp_on = True

        # Path Ikon (Sesuaikan lokasi/nama file ikon Anda)
        self.icon_lamp_on = QIcon("assets/icon/lightbulb-solid-full.svg")
        self.icon_lamp_off = QIcon("assets/icon/lightbulb-regular-full.svg")

        # Update jam dari helper pusat
        clock_helper.time_updated.connect(self.update_ui)
        self.btDown.clicked.connect(self.go_to_login.emit)

        # Connection event tombol btLamp (jika widget ada di .ui)
        if hasattr(self, "btLamp"):
            self.btLamp.setIconSize(QSize(40, 40))
            self.btLamp.setIcon(self.icon_lamp_on)
            self.btLamp.clicked.connect(self.toggle_lamp)

        # === API KEY  ===
        self.api_key = "58d5a389d75bd4647385189bc34c0580"  

        # === AMBIL LOKASI OTOMATIS ===
        self.location_data = self.get_location_from_ip()
        self.city = "Jakarta"

        # === UPDATE PERTAMA ===
        self.update_environment()
        self.update_notif_pending()

        # === TIMER UPDATE (10 MENIT) ===
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_environment)
        self.timer.start(600000)

        # === TIMER UPDATE DATA PENDING DATABASE (3 DETIK) ===
        self.timer_db = QTimer(self)
        self.timer_db.timeout.connect(self.update_notif_pending)
        self.timer_db.start(3000)

    def toggle_lamp(self):
        """Kirim command lampu ke semua controller yang terhubung secara dinamis."""
        self.is_lamp_on = not self.is_lamp_on
        command = "LAMP ON" if self.is_lamp_on else "LAMP OFF"

        if self.serial and hasattr(self.serial, 'threads'):
            sent = False
            # Loop semua thread serial yang sedang terhubung & punya role
            for thread in self.serial.threads:
                if getattr(thread, 'is_connected', False) and thread.role != 'UNKNOWN':
                    self.serial.send_command_to(thread.role, command)
                    print(f"Command Lampu Dikirim -> {thread.role}: {command}")
                    sent = True
            
            # Fallback jika belum ada thread yang teridentifikasi
            if not sent:
                print("[Saver] Tidak ada controller terhubung, menggunakan fallback MAIN_CONTROLLER")
                self.serial.send_command_to("MAIN_CONTROLLER", command)
        else:
            print("Serial handler tidak tersedia!")

        # Update UI Icon
        if hasattr(self, "btLamp"):
            if self.is_lamp_on:
                self.btLamp.setIcon(self.icon_lamp_on)
            else:
                self.btLamp.setStyleSheet("")
                self.btLamp.setIcon(self.icon_lamp_off)
        
    def update_ui(self, tgl, jam):
        self.lbDate.setText(tgl)
        self.lbTime.setText(jam)

    # ============================================================
    # FUNGSI CEK USER PENDING DARI DATABASE
    # ============================================================
    def get_pending_user(self):
        """Membaca jumlah user yang uid atau finger-nya masih NULL"""
        try:
            conn = get_db_connection()  # Membuka koneksi pakai fungsi dari db_config
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*) FROM tb_users WHERE status = 'USER' AND (uid IS NULL OR finger IS NULL)"
            cursor.execute(query)
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return result[0] if result else 0
        except Exception as e:
            print("Error get_pending_user:", e)
            return 0

    # ============================================================
    # UPDATE NOTIFIKASI DI UI (lbNotif)
    # ============================================================
    def update_notif_pending(self):
        count = self.get_pending_user()
        
        if hasattr(self, 'lbNotif'):
            self.lbNotif.setText(str(count))
            # print(str(count))
            
            # Highlight merah jika ada pending > 0
            # if count > 0:
            #     self.lbNotif.setStyleSheet("color: #FEF250; font-weight: bold;")
            # else:
            #     self.lbNotif.setStyleSheet("color: #FFFFFF; font-weight: normal;")

    def get_location_from_ip(self):
        try:
            response = requests.get("http://ip-api.com/json/", timeout=5)
            data = response.json()
            
            if data.get("status") == "success":
                return {
                    "city": data.get("city", "Unknown"),
                    "region": data.get("regionName", ""),
                    "country": data.get("country", ""),
                }
            else:
                return {"city": "Unknown", "region": "", "country": ""}
        except Exception as e:
            print("Location error:", e)
            return {"city": "Unknown", "region": "", "country": ""}

    # ============================================================
    # AMBIL CUACA DARI OPENWEATHERMAP
    # ============================================================
    def get_weather(self):
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric"
            response = requests.get(url, timeout=10)
            data = response.json()

            if data.get("cod") == 200 and data.get("main"):
                temp = data["main"]["temp"]
                humidity = data["main"]["humidity"]
                return round(temp, 1), humidity
            else:
                print("Weather error:", data.get("message", "Unknown"))
                return None, None
        except Exception as e:
            print("Weather error:", e)
            return None, None

    # ============================================================
    # UPDATE UI
    # ============================================================
    def update_environment(self):
        # Lokasi
        loc_str = f"{self.location_data['city']}, {self.location_data['region']}"
        if self.location_data['country']:
            loc_str += f" - {self.location_data['country']}"
        
        if hasattr(self, 'labelLocation'):
            self.labelLocation.setText(f"📍 {loc_str}")

        # Cuaca
        temp, hum = self.get_weather()

        if hasattr(self, 'labelTemp'):
            if temp is not None:
                self.labelTemp.setText(f"🌡️ {temp}°C")
            else:
                self.labelTemp.setText("🌡️ --°C")

        if hasattr(self, 'labelHumidity'):
            if hum is not None:
                self.labelHumidity.setText(f"💧 {hum}% RH")
            else:
                self.labelHumidity.setText("💧 --% RH")

        # Optional: print ke console biar tau udah jalan
        if temp and hum:
            print(f"✅ Weather updated: {temp}°C, {hum}% RH")