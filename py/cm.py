# camera_simple.py
import cv2
import os
from datetime import datetime

def capture_photo(camera_id=0, save_dir="captures"):
    """
    Buka kamera, preview, capture dengan spasi, keluar dengan ESC.
    
    Args:
        camera_id (int): ID kamera (default 0)
        save_dir (str): Folder penyimpanan gambar
    
    Returns:
        str: Path file gambar jika berhasil, None jika dibatalkan
    """
    # Buat folder jika belum ada
    os.makedirs(save_dir, exist_ok=True)

    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print("❌ Gagal membuka kamera!")
        return None

    print("📸 Tekan [SPASI] untuk capture, [ESC] untuk batal")
    print("📁 Gambar akan disimpan di folder:", save_dir)

    captured_image = None
    captured_path = None

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Gagal membaca frame")
            break

        # Tampilkan info di frame
        h, w = frame.shape[:2]
        cv2.putText(frame, "Tekan SPASI utk capture, ESC utk batal", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"Folder: {save_dir}", 
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        cv2.imshow("📸 Capture - Weapon Storage", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            print("❌ Capture dibatalkan")
            break
        elif key == 32:  # SPASI
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp}.jpg"
            filepath = os.path.join(save_dir, filename)
            cv2.imwrite(filepath, frame)
            captured_path = filepath
            captured_image = frame
            print(f"✅ Gambar tersimpan: {filepath}")
            break

    cap.release()
    cv2.destroyAllWindows()
    return captured_path


if __name__ == "__main__":
    # Contoh penggunaan langsung
    result = capture_photo()
    if result:
        print(f"📸 Hasil capture: {result}")
    else:
        print("❌ Tidak ada gambar yang di-capture")