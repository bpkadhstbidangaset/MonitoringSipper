import streamlit as st
import pandas as pd
import requests
import io
import plotly.express as px
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="Dashboard Monitoring Persediaan SiPPER HST",
    page_icon="📦",
    layout="wide"
)

# 1. KREDENSIAL DARI SECRETS / INPUT
USERNAME = st.secrets.get("SIPPER_USERNAME", "Administrator")
PASSWORD = st.secrets.get("SIPPER_PASSWORD", "12345678")

BASE_URL = "https://sipper.hstkab.go.id"
LOGIN_URL = f"{BASE_URL}/login_.php?IncFile=login"

# 2. FUNGSI KONVERSI NILAI RUPIAH
def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["-", "", "nan"]:
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
        "Referer": f"{BASE_URL}/index.php?IncFile=bG9naW4="
    }
    
    try:
        # A. Proses Login
        payload = {
            "fUsr": USERNAME,
            "fPas": PASSWORD
        }
        resp_login = session.post(LOGIN_URL, data=payload, headers=headers, timeout=15)
        
        # B. URL Target Halaman Laporan
        if not custom_report_url:
            report_url = f"{BASE_URL}/index.php?JdL=LAPORAN%20->%20REKAP%20DATA%20PER%20SEMESTER&IncFile=cmVrYXBfcGVyc2VkaWFhbl9zZW1lc3Rlcg==&IdL=VFhwck5VNTNQVDA9"
        else:
            report_url = custom_report_url
            
        resp_report = session.get(report_url, headers=headers, timeout=20)
        
        if resp_report.status_code != 200:
            return None, f"Gagal memuat halaman laporan (HTTP {resp_report.status_code})", resp_report.text

        # C. Cek apakah di dalam halaman terdapat tag <iframe> yang memuat tabel data sebenarnya
        soup = BeautifulSoup(resp_report.text, "html.parser")
        iframes = soup.find_all("iframe")
        
        # Jika ada iframe data, akses URL di dalam iframe tersebut
        if iframes and not custom_report_url:
            for iframe in iframes:
                src = iframe.get("src", "")
                if src and ("rekap" in src.lower() or "data" in src.lower() or "laporan" in src.lower()):
                    iframe_url = src if src.startswith("http") else f"{BASE_URL}/{src.lstrip('/')}"
                    resp_iframe = session.get(iframe_url, headers=headers, timeout=20)
                    if resp_iframe.status_code == 200:
                        tables = pd.read_html(io.StringIO(resp_iframe.text))
                        if tables:
                            df_target = max(tables, key=lambda t: t.shape[1] * t.shape[0])
                            return df_target, "success", resp_iframe.text

        # D. Ekstrak Tabel Langsung dari Halaman Utama
        tables = pd.read_html(io.StringIO(resp_report.text))
        if not tables:
            return None, "Tabel data laporan belum ditemukan pada URL ini. Silakan periksa apakah data dimuat via iframe/AJAX.", resp_report.text

        # Ambil tabel dengan kolom terbanyak
        df_target = max(tables, key=lambda t: t.shape[1] * t.shape[0])
        
        # Flatten MultiIndex jika header tabel bertingkat
        if isinstance(df_target.columns, pd.MultiIndex):
            df_target.columns = ['_'.join(str(c) for c in col).strip() for col in df_target.columns.values]

        return df_target, "success", resp_report.text

    except Exception as e:
        return None, str(e), ""

# --- 4. TAMPILAN DASHBOARD ---
st.title("📦 Dashboard Monitoring Persediaan (SiPPER HST)")
st.caption("Monitoring Persediaan Real-Time Pemerintah Kabupaten Hulu Sungai Tengah")

# Sidebar
st.sidebar.header("⚙️ Pengaturan & Filter")
if st.sidebar.button("🔄 Tarik Data Terbaru"):
    st.cache_data.clear()
    st.rerun()

custom_url = st.sidebar.text_input(
    "Custom URL Laporan (Opsional):", 
    value="",
    help="Jika tabel dimuat di URL/iframe spesifik, tempelkan URL lengkapnya di sini."
)

with st.spinner("Mengautentikasi dan menarik data dari SiPPER..."):
    df_raw, status, html_response = fetch_sipper_rekap(custom_url if custom_url else None)

if df_raw is not None:
    st.success("✅ Data berhasil diambil dari server SiPPER.")

    df = df_raw.copy()
    
    # Pemetaan kolom otomatis
    col_mapping = {}
    for col in df.columns:
        c_low = str(col).lower()
        if "deskripsi" in c_low or "nama" in c_low:
            col_mapping[col] = "Deskripsi"
        elif "kode" in c_low:
            col_mapping[col] = "Kode"
        elif "masuk" in c_low and "nilai" in c_low:
            col_mapping[col] = "Nilai_Masuk"
        elif "keluar" in c_low and "nilai" in c_low:
            col_mapping[col] = "Nilai_Keluar"
        elif "saldo" in c_low and "nilai" in c_low:
            col_mapping[col] = "Nilai_Saldo"
            
    df = df.rename(columns=col_mapping)
    
    for numeric_col in ["Nilai_Masuk", "Nilai_Keluar", "Nilai_Saldo"]:
        if numeric_col in df.columns:
            df[numeric_col] = df[numeric_col].apply(clean_currency)

    # KPI Summary Cards
    st.markdown("### 📊 Ringkasan Nilai Persediaan")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    total_masuk = df["Nilai_Masuk"].sum() if "Nilai_Masuk" in df.columns else 0.0
    total_keluar = df["Nilai_Keluar"].sum() if "Nilai_Keluar" in df.columns else 0.0
    total_saldo = df["Nilai_Saldo"].sum() if "Nilai_Saldo" in df.columns else 0.0

    kpi1.metric("Total Saldo Akhir", f"Rp {total_saldo:,.0f}".replace(",", "."))
    kpi2.metric("Total Pengadaan / Masuk", f"Rp {total_masuk:,.0f}".replace(",", "."))
    kpi3.metric("Total Pengeluaran", f"Rp {total_keluar:,.0f}".replace(",", "."))
    kpi4.metric("Jumlah Rekening", f"{len(df)} Baris")

    st.markdown("---")

    # Visualisasi
    if "Deskripsi" in df.columns and "Nilai_Saldo" in df.columns:
        top_saldo = df.nlargest(10, "Nilai_Saldo")
        fig_bar = px.bar(
            top_saldo,
            x="Nilai_Saldo",
            y="Deskripsi",
            orientation="h",
            title="Top 10 Barang Saldo Terbesar",
            color="Nilai_Saldo",
            color_continuous_scale="Blues"
        )
        fig_bar.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_bar, use_container_width=True)

    # Tabel Data
    st.markdown("### 📋 Rincian Data Persediaan")
    st.dataframe(df, use_container_width=True)

else:
    st.error(f"Status: {status}")
    
    # Fitur Inspeksi Debug HTML
    with st.expander("🔍 Lihat Hasil Respon Halaman (Debug)", expanded=False):
        st.text_area("Source Code HTML yang diterima:", value=html_response[:3000] if html_response else "Kosong", height=250)
