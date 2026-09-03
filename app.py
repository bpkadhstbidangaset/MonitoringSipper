import io
import warnings
import urllib3
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

# Nonaktifkan peringatan SSL
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

# 2. KONVERSI NILAI RUPIAH KE ANGKA
def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["-", "", "nan", "None", "null"]:
        return 0.0
    val_str = str(val).replace("Rp", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

# 3. PENARIKAN DATA OTOMATIS LANGSUNG DARI IFRAME LAPORAN
@st.cache_data(ttl=300)
def fetch_sipper_auto(unit_kode="1.02.01.01", tahun="2026", semester="1"):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"{BASE_URL}/index.php?IncFile=bG9naW4=",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    try:
        # A. Otentikasi Login
        payload = {
            "fUsr": USERNAME,
            "fPas": PASSWORD
        }
        session.post(LOGIN_URL, data=payload, headers=headers, timeout=15, verify=False)
        
        # B. Tembak Langsung Endpoint Iframe Laporan
        report_url = f"{BASE_URL}/rekap_persediaan_semester.php?fKdU={unit_kode}&fThn={tahun}&fSmt={semester}&IdL=VFhwck5VNTNQVDA9"
        
        resp = session.get(report_url, headers=headers, timeout=25, verify=False)
        
        if resp.status_code != 200:
            return None, f"HTTP Error {resp.status_code}"

        # C. Ekstrak Tabel Data Barang
        tables = pd.read_html(io.StringIO(resp.text))
        if not tables:
            return None, "Tabel data laporan tidak ditemukan."

        # Ambil tabel dengan sel terbanyak
        df_target = max(tables, key=lambda t: t.shape[0] * t.shape[1])
        return df_target, "success"

    except Exception as e:
        return None, str(e)

# --- 4. TAMPILAN DASHBOARD ---
st.title("📦 Dashboard Live Monitoring Persediaan (SiPPER HST)")
st.caption("Pemerintah Kabupaten Hulu Sungai Tengah — Data Disinkronkan Otomatis Secara Real-Time")

# Sidebar Filter
st.sidebar.header("⚙️ Filter Data SiPPER")
if st.sidebar.button("🔄 Sinkronkan Data Terbaru"):
    st.cache_data.clear()
    st.rerun()

sel_unit = st.sidebar.text_input("Kode Sub Unit / SKPD", value="1.02.01.01")
sel_tahun = st.sidebar.selectbox("Tahun Anggaran", ["2026", "2025", "2024"], index=0)
sel_smt = st.sidebar.selectbox("Semester", ["Semester 1", "Semester 2"], index=0)
smt_val = "1" if sel_smt == "Semester 1" else "2"

# Eksekusi Pengambilan Data
with st.spinner("Menghubungi server SiPPER HST dan mengambil data..."):
    df_raw, status = fetch_sipper_auto(unit_kode=sel_unit, tahun=sel_tahun, semester=smt_val)

if df_raw is not None:
    df = df_raw.copy()

    # 1. Cari Baris Header Nama Kolom yang Sebenarnya
    for i in range(min(6, len(df))):
        row_vals = [str(x).lower() for x in df.iloc[i].values]
        if any("deskripsi" in x or "kode" in x or "saldo" in x for x in row_vals):
            df.columns = df.iloc[i]
            df = df.iloc[i+1:].reset_index(drop=True)
            break

    # 2. Standardisasi Nama Kolom
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

    # Filter baris sampah/header banner
    if "Deskripsi" in df.columns:
        df = df[~df["Deskripsi"].astype(str).str.contains("Warning:|Kabupaten|KABUPATEN|None|JUMLAH", na=False)]

    # Konversi Kolom Angka
    for c in ["Nilai_Masuk", "Nilai_Keluar", "Nilai_Saldo", "Qty_Saldo"]:
        if c in df.columns:
            df[c] = df[c].apply(clean_currency)

    # 3. KARTU METRIK UTAMA (KPI)
    st.markdown("### 📊 Ringkasan Nilai Persediaan")
    k1, k2, k3, k4 = st.columns(4)

    total_saldo = df["Nilai_Saldo"].sum() if "Nilai_Saldo" in df.columns else 0.0
    total_masuk = df["Nilai_Masuk"].sum() if "Nilai_Masuk" in df.columns else 0.0
    total_keluar = df["Nilai_Keluar"].sum() if "Nilai_Keluar" in df.columns else 0.0
    total_item = len(df)

    k1.metric("Total Saldo Akhir", f"Rp {total_saldo:,.0f}".replace(",", "."))
    k2.metric("Total Pengadaan (Masuk)", f"Rp {total_masuk:,.0f}".replace(",", "."))
    k3.metric("Total Pengeluaran", f"Rp {total_keluar:,.0f}".replace(",", "."))
    k4.metric("Jumlah Item Rekening", f"{total_item} Baris")

    st.markdown("---")

    # 4. GRAFIK VISUALISASI
    c1, c2 = st.columns(2)
    if "Deskripsi" in df.columns and "Nilai_Saldo" in df.columns and df["Nilai_Saldo"].sum() > 0:
        with c1:
            top_saldo = df.nlargest(10, "Nilai_Saldo")
            fig1 = px.bar(
                top_saldo, 
                x="Nilai_Saldo", 
                y="Deskripsi",
                orientation="h", 
                title="Top 10 Barang/Rekening Saldo Terbesar",
                color="Nilai_Saldo", 
                color_continuous_scale="Blues"
            )
            fig1.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig1, use_container_width=True)

    if "Deskripsi" in df.columns and "Nilai_Keluar" in df.columns and df["Nilai_Keluar"].sum() > 0:
        with c2:
            top_keluar = df.nlargest(10, "Nilai_Keluar")
            fig2 = px.bar(
                top_keluar, 
                x="Nilai_Keluar", 
                y="Deskripsi",
                orientation="h", 
                title="Top 10 Barang/Rekening Pemakaian Terbesar",
                color="Nilai_Keluar", 
                color_continuous_scale="Reds"
            )
            fig2.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig2, use_container_width=True)

    # 5. TABEL RINCIAN LENGKAP
    st.markdown("### 📋 Rincian Lengkap Data Barang Persediaan")
    st.dataframe(df, use_container_width=True)

else:
    st.error(f"Gagal memuat data: {status}")
