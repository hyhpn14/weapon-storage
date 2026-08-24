import mysql.connector.pooling
from log_client import send_log

# Konfigurasi Pool
db_config = {
    "host": "10.10.20.27",
    "user": "root",
    "password": "",
    "database": "db_storage"
}

connection_pool = None

def init_db_pool(gudang="GLOCK17"):
    """Inisialisasi Pool Database jika belum ada"""
    global connection_pool
    if connection_pool is None:
        try:
            connection_pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="mypool",
                pool_size=5,
                **db_config
            )
            print("Database Pool berhasil dibuat.")
            #record Log Sukses
            send_log(
                kategori="DATABASE",
                aktivitas="db_pool",
                detail="Database Pool berhasil dibuat & terhubung",
                gudang=gudang,
                status="success"
            )
        except mysql.connector.Error as err:
            print(f"Gagal membuat Database Pool: {err}")
            # Record Log Error
            send_log(
                kategori="DATABASE",
                aktivitas="db_pool_error",
                detail=f"Gagal membuat Database Pool: {str(err)}",
                gudang=gudang,
                status="danger"
            )
            connection_pool = None

# Inisialisasi percobaan pertama saat import
init_db_pool()

def get_db_connection(gudang="GLOCK17"):
    """Mengambil koneksi dari pool. Mengembalikan None jika DB mati/down."""
    global connection_pool
    if connection_pool is None:
        init_db_pool(gudang)
        
    if connection_pool:
        try:
            return connection_pool.get_connection()
        except mysql.connector.Error as err:
            print(f"Gagal mengambil koneksi dari pool: {err}")
            # Record Log Gagal Ambil Koneksi
            send_log(
                kategori="DATABASE",
                aktivitas="db_pool_error",
                detail=f"Gagal mengambil koneksi dari pool: {str(err)}",
                gudang=gudang,
                status="danger"
            )
            return None
    return None

def log_login_attempt(nrp, metode, berhasil, gudang, locker_id):
    """
    Catat SETIAP percobaan login ke tb_login_log — sukses maupun gagal.
    """
    try:
        conn = get_db_connection()
        if conn is None:
            print("Gagal simpan log login: Koneksi Database Tidak Tersedia")
            return

        cursor = conn.cursor()
        query = "INSERT INTO tb_login_log (nrp, metode, berhasil, gudang, locker_id) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(query, (nrp, metode, berhasil, gudang, locker_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Gagal simpan log login: {e}")