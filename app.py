import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.express as px

st.set_page_config(page_title="Monitoring Real-Time SiPPER HST", layout="wide")

# 1. AMBIL KREDENSIAL DARI SECRETS (Bukan hardcode di file publik)
# Pada local: .streamlit/secrets.toml
# Pada Streamlit Cloud: Pengaturan App -> Secrets
USERNAME = st.secrets.get("SIPPER_USERNAME", "username_anda")
PASSWORD = st.secrets.get("SIPPER_PASSWORD", "password_anda")

BASE_URL = "https://sipper.hstkab.go.id"
LOGIN_URL = f"{BASE_URL}/login"  # Sesuaikan dengan endpoint form login SiPPER
DATA_URL = f"{BASE_URL}/laporan/rekap-data"  # Endpoint halaman tabel/data laporan

# 2. FUNGSI PENARIKAN DATA OTOMATIS (DENGAN CACHE WAKTU TERTENTU)
@st.cache_data(ttl=600)  # Data otomatis di-refresh tiap 10 menit
def fetch_sipper_data():
    session = requests.Session()
    
    # Header simulasi browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        # A. Request halaman login awal (ambil token CSRF jika ada)
        resp_login_page = session.get(LOGIN_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(resp_login_page.text, "html.parser")
        
        # Contoh ekstraksi token CSRF (sesuaikan name input jika ada)
        csrf_input = soup.find("input", {"name": "_token"})
        csrf_token = csrf_input["value"] if csrf_input else ""

        # B. Kirim Payload Login
        payload = {
            "username": USERNAME,
            "password": PASSWORD,
            "_token": csrf_token
        }
        post_login = session.post(LOGIN_URL, data=payload, headers=headers, timeout=10)
        
        # C. Ambil halaman data tabel setelah berhasil login
        resp_data = session.get(DATA_URL, headers=headers, timeout=15)
        
        # D. Parsing tabel HTML ke DataFrame Pandas
        # (Atau parsing respon JSON jika endpoint mengembalikan JSON)
        tables = pd.read_html(resp_data.text)
        if tables:
            df = tables[0]  # Ambil tabel pertama
            return df, "success"
        else:
            return None, "Tabel data tidak ditemukan pada halaman."
            
    except Exception as e:
        return None, str(e)

# 3. TAMPILAN DASHBOARD
st.title("📦 Dashboard Live Monitoring - SiPPER HST")

# Tombol Sinkronisasi Manual
if st.sidebar.button("🔄 Sinkronisasi Data Sekarang"):
    st.cache_data.clear()
    st.rerun()

# Memuat Data
with st.spinner("Menghubungkan ke https://sipper.hstkab.go.id/ ..."):
    df_raw, status = fetch_sipper_data()

if df_raw is not None:
    st.success("✅ Terhubung secara langsung ke server SiPPER.")
    
    # Tampilkan Data & Visualisasi
    st.dataframe(df_raw, use_container_width=True)
    
    # Tambahkan visualisasi sesuai kolom data tabel SiPPER
    # st.plotly_chart(...)
else:
    st.error(f"Gagal mengambil data otomatis: {status}")
    st.info("Catatan: Pastikan URL form login, payload parameter, dan kredensial di secrets sudah sesuai dengan rute internal aplikasi SiPPER.")
