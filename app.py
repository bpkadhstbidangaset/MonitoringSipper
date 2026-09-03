import io
import warnings
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="Dashboard Monitoring Persediaan SiPPER HST",
    page_icon="📦",
    layout="wide"
)

# 1. KREDENSIAL DARI SECRETS / DEFAULT
USERNAME = st.secrets.get("SIPPER_USERNAME", "Administrator")
PASSWORD = st.secrets.get("SIPPER_PASSWORD", "12345678")

BASE_URL = "http://sipper.hstkab.go.id"
LOGIN_URL = f"{BASE_URL}/login_.php?IncFile=login"

# 2. FUNGSI KONVERSI ANGKA RUPIAH
def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["-", "", "nan", "None", "null"]:
        return 0.0
    val_str = str(val).replace("Rp", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

# 3. FUNGSI PENARIKAN DATA
@st.cache_data(ttl=300)
def fetch_sipper_rekap(custom_report_url=None):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"{BASE_URL}/index.php?IncFile=bG9naW4=",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    try:
        # A. Login
        payload = {
            "fUsr": USERNAME,
            "fPas": PASSWORD
        }
        session.post(LOGIN_URL, data=payload, headers=headers, timeout=20, verify=False)
        
        # B. Akses URL Laporan / Request Data
        if not custom_report_url:
            report_url = f"{BASE_URL}/index.php?JdL=LAPORAN%20->%20REKAP%20DATA%20PER%20SEMESTER&IncFile=cmVrYXBfcGVyc2VkaWFhbl9zZW1lc3Rlcg==&IdL=VFhwck5VNTNQVDA9"
        else:
            report_url = custom_report_url
            
        resp_report = session.get(report_url, headers=headers, timeout=25, verify=False)
        
        if resp_report.status_code != 200:
            return None, f"HTTP Error {resp_report.status_code}"

        # C. Cari form data di dalam halaman dan coba kirim tombol Rekap jika ada
        soup = BeautifulSoup(resp_report.text, "html.parser")
        
        # Parsing semua tabel
        tables = pd.read_html(io.StringIO(resp_report.text))
        if not tables:
            return None, "Tidak ditemukan tabel pada respon server."

        # Filter tabel yang benar-benar berisi data (bukan header instansi)
        valid_tables = []
        for t in tables:
            # Lewati tabel header/banner yang hanya 1-2 baris atau berisi nama pemkab saja
            text_dump = " ".join([str(x) for x in t.values.flatten()]).lower()
            if "kode" in text_dump or "deskripsi" in text_dump or "saldo" in text_dump or "masuk" in text_dump:
                valid_tables.append(t)

        if valid_tables:
            # Ambil tabel data yang paling banyak kolom dan barisnya
            df_target = max(valid_tables, key=lambda t: t.shape[0] * t.shape[1])
            return df_target, "success"
        else:
            # Jika tidak ada yang cocok kata kuncinya, ambil tabel dengan baris terbanyak
            df_target = max(tables, key=lambda t: t.shape[0])
            return df_target, "warning_format"

    except Exception as e:
        return None, str(e)

# --- 4. TAMPILAN DASHBOARD ---
st.title("📦 Dashboard Monitoring Persediaan (SiPPER HST)")
st.caption("Data Terhubung Langsung ke Sistem Informasi Pencatatan Persediaan Kab. Hulu Sungai Tengah")

# Sidebar
st.sidebar.header("⚙️ Pengaturan & Filter")
if st.sidebar.button("🔄 Tarik Data Terbaru"):
    st.cache_data.clear()
    st.rerun()

custom_url = st.sidebar.text_input(
    "Custom URL / Endpoint Rekap (DevTools):", 
    value="",
    placeholder="Tempel URL request saat klik tombol 'Rekap'"
)

# Memuat Data
with st.spinner("Mengambil data dari SiPPER..."):
    df_raw, status = fetch_sipper_rekap(custom_url if custom_url else None)

if df_raw is not None:
    df = df_raw.copy()
    
    # Deteksi baris header kolom
    for i in range(min(6, len(df))):
        row_vals = [str(x).lower() for x in df.iloc[i].values]
        if any("deskripsi" in x or "kode" in x or "saldo" in x for x in row_vals):
            df.columns = df.iloc[i]
            df = df.iloc[i+1:].reset_index(drop=True)
            break

    # Standardisasi nama kolom
    col_mapping = {}
    for col in df.columns:
        c_str = str(col).lower()
        if "deskripsi" in c_str or "nama" in c_str:
            col_mapping[col] = "Deskripsi"
        elif "kode" in c_str:
            col_mapping[col] = "Kode"
        elif "masuk" in c_str and "nilai" in c_str:
            col_mapping[col] = "Nilai_Masuk"
        elif "keluar" in c_str and "nilai" in c_str:
            col_mapping[col] = "Nilai_Keluar"
        elif "saldo" in c_str and "nilai" in c_str:
            col_mapping[col] = "Nilai_Saldo"
        elif "saldo" in c_str and ("qty" in c_str or "jumlah" in c_str):
            col_mapping[col] = "Qty_Saldo"
            
    df = df.rename(columns=col_mapping)
    df = df.dropna(how='all')
    
    # Filter baris yang tidak valid
    if "Deskripsi" in df.columns:
        df = df[~df["Deskripsi"].astype(str).str.contains("Warning:|Kabupaten|KABUPATEN", na=False)]
    
    # Konversi kolom numerik
    for col_name in ["Nilai_Masuk", "Nilai_Keluar", "Nilai_Saldo", "Qty_Saldo"]:
        if col_name in df.columns:
            df[col_name] = df[col_name].apply(clean_currency)

    # KPI Metrik
    st.markdown("### 📊 Ringkasan Nilai Persediaan")
    k1, k2, k3, k4 = st.columns(4)
    
    total_saldo = df["Nilai_Saldo"].sum() if "Nilai_Saldo" in df.columns else 0.0
    total_masuk = df["Nilai_Masuk"].sum() if "Nilai_Masuk" in df.columns else 0.0
    total_keluar = df["Nilai_Keluar"].sum() if "Nilai_Keluar" in df.columns else 0.0
    total_item = len(df)

    k1.metric("Total Saldo Akhir", f"Rp {total_saldo:,.0f}".replace(",", "."))
    k2.metric("Total Pengadaan (Masuk)", f"Rp {total_masuk:,.0f}".replace(",", "."))
    k3.metric("Total Pengeluaran", f"Rp {total_keluar:,.0f}".replace(",", "."))
    k4.metric("Jumlah Rekening", f"{total_item} Baris")

    st.markdown("---")

    # Visualisasi
    if "Deskripsi" in df.columns and "Nilai_Saldo" in df.columns and df["Nilai_Saldo"].sum() > 0:
        c1, c2 = st.columns(2)
        with c1:
            top_saldo = df.nlargest(10, "Nilai_Saldo")
            fig1 = px.bar(
                top_saldo, 
                x="Nilai_Saldo", 
                y="Deskripsi",
                orientation="h", 
                title="Top 10 Rekening Saldo Terbesar",
                color="Nilai_Saldo", 
                color_continuous_scale="Blues"
            )
            fig1.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig1, use_container_width=True)
            
        with c2:
            if "Nilai_Keluar" in df.columns and df["Nilai_Keluar"].sum() > 0:
                top_keluar = df.nlargest(10, "Nilai_Keluar")
                fig2 = px.bar(
                    top_keluar, 
                    x="Nilai_Keluar", 
                    y="Deskripsi",
                    orientation="h", 
                    title="Top 10 Rekening Pengeluaran Terbesar",
                    color="Nilai_Keluar", 
                    color_continuous_scale="Reds"
                )
                fig2.update_layout(yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig2, use_container_width=True)

    # Tabel Rincian Data
    st.markdown("### 📋 Rincian Data Persediaan")
    st.dataframe(df, use_container_width=True)

else:
    st.error(f"Gagal mengambil data: {status}")
