import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
from db_config import get_db_connection

# Konfigurasi SMTP Email
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "joyichi98@gmail.com"
# PENTING: App Password LAMA yang sempat ke-paste di chat sudah dianggap
# bocor -- generate App Password BARU di https://myaccount.google.com/apppasswords
# dan isi di sini secara LANGSUNG DI FILE (jangan paste lewat chat lagi).
SENDER_PASSWORD = "mhwl lgnm iqfi yiky"


def get_admin_emails():
  """Mengambil daftar email user ber-status ADMIN dari database."""
  emails = []
  try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT email FROM tb_users WHERE status = 'ADMIN' AND email IS NOT"
        " NULL"
    )
    rows = cursor.fetchall()
    emails = [
        row["email"].strip()
        for row in rows
        if row.get("email") and row["email"].strip()
    ]
    cursor.close()
    conn.close()
    print(f"🔍 Email admin ditemukan: {emails}")
  except Exception as e:
    print(f"⚠️ Gagal mengambil email admin: {e}")
  return emails


def send_email_alert_async(gudang, auth_type, reason):
  """Mengirim email peringatan ke semua Admin di Background Thread."""

  def _send():
    try:
      admin_emails = get_admin_emails()
      print(f"🔍 Email penerima (ADMIN) ditemukan: {admin_emails}")

      if not admin_emails:
        print("⚠️ Tidak ada email admin terdaftar.")
        return

      subject = f"🚨 SECURITY WARNING: Akses Ilegal Dideteksi [{gudang}]"
      body = f"""
            <h2>⚠️ Peringatan Keamanan Sistem Loker</h2>
            <p>Telah terjadi indikasi akses tidak sah berulang kali pada lokasi berikut:</p>
            <ul>
                <li><b>Gudang / Storage:</b> {gudang}</li>
                <li><b>Metode Autentikasi:</b> {auth_type.upper()}</li>
                <li><b>Alasan:</b> {reason}</li>
                <li><b>Status:</b> 3x Percobaan Gagal (Capture Kamera)</li>
            </ul>
            <p>Silakan periksa <b>Web Dashboard</b> untuk melihat detail foto dan log kejadian.</p>
            """

      # Buka koneksi SMTP sekali untuk semua penerima
      server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
      server.starttls()
      server.login(SENDER_EMAIL, SENDER_PASSWORD)

      for recipient in admin_emails:
        try:
          msg = MIMEMultipart("alternative")
          msg["Subject"] = subject
          msg["From"] = f"Loker Security System <{SENDER_EMAIL}>"
          msg["To"] = recipient
          msg.attach(MIMEText(body, "html"))

          server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
          print(f"📧 Email alert berhasil dikirim ke: {recipient}")
        except Exception as err:
          print(f"❌ Gagal mengirim email ke {recipient}: {err}")

      server.quit()

    except Exception as global_err:
      print(f"❌ SMTP Authentication / Connection Error: {global_err}")

  # Jalankan di Thread terpisah agar GUI PyQt tidak macet
  threading.Thread(target=_send, daemon=True).start()


def push_dashboard_warning_async(gudang, auth_type, reason):
    """Mengirim Notifikasi Warning ke Web Dashboard (Webhooks + Database Notification)."""

    def _push():
        # 1. Simpan ke tabel tb_alerts untuk polling dashboard web
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                        INSERT INTO tb_alerts (gudang, auth_type, reason, is_read)
                        VALUES (%s, %s, %s, 0)
                    """,
                (gudang, auth_type, reason),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ Gagal insert tb_alerts: {e}")

        # 2. Kirim Webhook HTTP POST langsung ke Server Web Dashboard (Real-time Alert)
        try:
            webhook_url = "http://localhost/web-storage/dashboard.php"
            payload = {
                "gudang": gudang,
                "auth_type": auth_type,
                "reason": reason,
                "severity": "HIGH",
            }
            requests.post(webhook_url, json=payload, timeout=3)
            print("🔔 Warning pushed to Web Dashboard Server.")
        except Exception as e:
            print(f"⚠️ Gagal push ke Webhook Dashboard: {e}")

    threading.Thread(target=_push, daemon=True).start()


def trigger_security_alert(gudang, auth_type, reason):
    """Pintu masuk utama untuk memicu seluruh Notifikasi Bahaya."""
    send_email_alert_async(gudang, auth_type, reason)
    push_dashboard_warning_async(gudang, auth_type, reason)