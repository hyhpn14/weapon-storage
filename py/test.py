import sys
import serial
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog
from PyQt5 import uic
from PyQt5.QtCore import QTimer

# Inisialisasi Serial
try:
    ser = serial.Serial('COM4', 115200, timeout=0.1)
except:
    ser = None

class SubDialog(QDialog):
    def __init__(self, ui_file):
        super().__init__()
        uic.loadUi(ui_file, self)
        
        # Timer untuk memantau data serial setiap 100ms
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(100)

    def update_status(self):
        if ser and ser.in_waiting > 0:
            # Membaca data dan membersihkannya
            raw_data = ser.readline()
            if not raw_data: return
            
            response = raw_data.decode('utf-8', errors='ignore').strip()
            print(f"Arduino says: {response}") 
            
            label = self.findChild(object, 'lbInfoF')
            if label:
                # Gunakan 'in' agar tidak peduli jika ada spasi/karakter tambahan
                if "SCAN1" in response:
                    label.setText("Please scan again")
                elif "SCAN2" in response:
                    label.setText("Verifikasi complete")
                elif "COMPLETE" in response:
                    label.setText("Enrollment Success!")
                elif "MATCH_OK" in response:
                    label.setText("Access Granted!")
                    label.setStyleSheet("color: green; font-weight: bold;")
                elif "MATCH_FAIL" in response:
                    label.setText("Access Denied!")
                    label.setStyleSheet("color: red; font-weight: bold;")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("ui/register.ui", self)

        # Menghubungkan tombol ke fungsi
        self.btRSFinger.clicked.connect(self.open_finger_dialog)
        self.btRSId.clicked.connect(self.open_rfid_dialog)

    def open_finger_dialog(self):
        # Kirim perintah e1 ke Arduino
        if ser:
            ser.write(b'e1\n')
            print("Command 'e1' sent")
        
        # Buka dialog fingerprint
        dialog = SubDialog("ui/regist_finger.ui")
        dialog.exec_()

    def open_rfid_dialog(self):

        if ser:
            ser.write(b'v\n')
            print("Perintah 'v' (Verifikasi Finger) dikirim ke Arduino")
        
        # 2. Buka dialog RFID
        # Dialog ini diasumsikan sebagai antarmuka untuk verifikasi kartu
        dialog = SubDialog("ui/regist_card.ui")
        dialog.exec_()

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())