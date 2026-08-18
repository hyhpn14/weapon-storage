import serial

# Sesuaikan 'COM4' dengan port Arduino Anda
ser = serial.Serial('COM4', 9600, timeout=1)

print("Ketik 'e1' untuk nyalakan LED, 'e0' untuk matikan LED.")

while True:
    perintah = input("Masukkan perintah: ")
    ser.write(perintah.encode()) # Mengirim ke Arduino