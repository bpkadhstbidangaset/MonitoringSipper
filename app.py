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

# 1. KREDENSIAL DARI SECRETS
USERNAME = st.secrets.get("SIPPER_USERNAME", "Administrator")
PASSWORD = st.secrets.get("SIPPER_PASSWORD", "12345678")

BASE_URL = "https://sipper.hstkab.go.id"
LOGIN_URL = f"{BASE_URL}/login_.php?IncFile=login"

# 2. FUNGSI KONVERSI NILAI RUPIAH
def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["-", "", "nan", "None"]:
        return 0.0
    val_str = str(val).replace("Rp", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

# 3. FUNGSI PENARIKAN DATA LANGSUNG
@st.cache_data(ttl=300)
def fetch_sipper_rekap(custom_report_url=None):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"{BASE_URL}/index.php?IncFile=bG9naW4="
    }
    
    try:
        # A. Login
        payload = {
            "fUsr": USERNAME,
            "fPas": PASSWORD
        }
        resp_login = session.post(LOGIN_URL, data=payload, headers=headers, timeout=15)
        
        # B. URL Target Laporan
        if not custom_report_url:
            # Gunakan URL persis seperti yang terekam di DevTools Anda
            report_url = f"{BASE_URL}/index.php?JdL=LAPORAN%20->%20REKAP%20DATA%20PER%20SEMESTER&IncFile=cmVrYXBfcGVyc2VkaWFhbl9zZW1lc3Rlcg==&IdL=VFhwck5VNTNQVDA9"
        else:
            report_url = custom_report_url
            
        resp_report = session.get(report_url, headers=headers, timeout=20)
        
        # C. Cari form atau iframe jika data dimuat di sub-request
        soup = BeautifulSoup(resp_report.text, "html.parser")
        
        # Ekstrak semua tabel
        tables = pd.read_html(io.StringIO(resp_report.text))
        
        # Cari tabel yang memiliki data barang (biasanya yang punya kolom Deskripsi / Kode / Qty)
        candidate_tables = []
        for t in tables:
            # Lewati tabel header/navigasi yang isinya cuma teks judul
            if t.shape[1] >= 4 and t.shape[0] > 1:
                candidate_tables.append(t)
                
        if candidate_tables:
            df_target = max(candidate_tables, key=lambda t: t.shape[0] * t.shape[1])
            return df_target, "success", resp_report.text
        elif tables:
            # Jika hanya ada tabel kecil, kembalikan tabel terbesar
            df_target = max(tables, key=lambda t: t.shape[0] * t.shape[1])
            return df_target, "warning_format", resp_report.text
        else:
            return None, "Tabel tidak ditemukan.", resp_report.text

    except Exception as e:
        return None, str(e), ""

# --- 4. TAMPILAN DASHBOARD ---
st.title("📦 Dashboard Monitoring Persediaan (SiPPER HST)")
st.caption("Data Terhubung Otomatis ke Sistem Persediaan Kab. Hulu Sungai Tengah")

# Sidebar
st.sidebar.header("⚙️ Pengaturan & Filter")
if st.sidebar.button("🔄 Tarik Data Terbaru"):
    st.cache_data.clear()
    st.rerun()

custom_url = st.sidebar.text_input(
    "Custom URL / Endpoint Tabel:", 
    value="",
    placeholder="Tempel URL jika data ada di file terpisah"
)

with st.spinner("Mengambil data langsung dari SiPPER..."):
    df_raw, status, html_res = fetch_sipper_rekap(custom_url if custom_url else None)

if df_raw is not None:
    # Bersihkan tabel jika baris pertama adalah header bertingkat
    df = df_raw.copy()
    
    # Cek apakah baris 0 adalah nama kolom (Kode, Deskripsi, Masuk, Keluar, Saldo)
    header_found = False
    for i in range(min(5, len(df))):
        row_vals = [str(x).lower() for x in df.iloc[i].values]
        if any("deskripsi" in x or "kode" in x for x in row_vals):
            df.columns = df.iloc[i]
            df = df.iloc[i+1:].reset_index(drop=True)
            header_found = True
            break
            
    # Standardisasi nama kolom
    col_mapping = {}
    for idx, col in enumerate(df.columns):
        c_str = str(col).lower()
        if "deskripsi" in c_str or "nama" in c_str:
            col_mapping[col] = "Deskripsi"
        elif "kode" in c_str:
            col_mapping[col] = "Kode"
        elif "masuk" in c_str:
            col_mapping[col] = "Nilai_Masuk"
        elif "keluar" in c_str:
            col_mapping[col] = "Nilai_Keluar"
        elif "saldo" in c_str:
            col_mapping[col] = "Nilai_Saldo"
            
    df = df.rename(columns=col_mapping)
    
    # Hapus baris kosong / warning
    df = df.dropna(how='all')
    if "Deskripsi" in df.columns:
        df = df[~df["Deskripsi"].astype(str).str.contains("Warning:", na=False)]
    
    # Konversi kolom nilai
    for col_name in ["Nilai_Masuk", "Nilai_Keluar", "Nilai_Saldo"]:
        if col_name in df.columns:
            df[col_name] = df[col_name].apply(clean_currency)

    # --- KPI CARDS ---
    st.markdown("### 📊 Ringkasan Nilai Persediaan")
    k1, k2, k3, k4 = st.columns(4)
    
    total_saldo = df["Nilai_Saldo"].sum() if "Nilai_Saldo" in df.columns else 0.0
    total_masuk = df["Nilai_Masuk"].sum() if "Nilai_Masuk" in df.columns else 0.0
    total_keluar = df["Nilai_Keluar"].sum() if "Nilai_Keluar" in df.columns else 0.0
    total_item = len(df)

    k1.metric("Total Saldo Akhir", f"Rp {total_saldo:,.0f}".replace(",", "."))
    k2.metric("Total Pengadaan (Masuk)", f"Rp {total_masuk:,.0f}".replace(",", "."))
    k3.metric("Total Pengeluaran", f"Rp {total_keluar:,.0f}".replace(",", "."))
    k4.metric("Jumlah Item / Rekening", f"{total_item} Baris")

    st.markdown("---")

    # --- GRAFIK VISUALISASI ---
    if "Deskripsi" in df.columns and "Nilai_Saldo" in df.columns and df["Nilai_Saldo"].sum() > 0:
        c1, c2 = st.columns(2)
        with c1:
            top_saldo = df.nlargest(10, "Nilai_Saldo")
            fig1 = px.bar(
                top_saldo, x="Nilai_Saldo", y="Deskripsi",
                orientation="h", title="Top 10 Barang Nilai Saldo Terbesar",
                color="Nilai_Saldo", color_continuous_scale="Blues"
            )
            fig1.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig1, use_container_width=True)
            
        with c2:
            if "Nilai_Keluar" in df.columns and df["Nilai_Keluar"].sum() > 0:
                top_keluar = df.nlargest(10, "Nilai_Keluar")
                fig2 = px.bar(
                    top_keluar, x="Nilai_Keluar", y="Deskripsi",
                    orientation="h", title="Top 10 Barang Nilai Pengeluaran Terbesar",
                    color="Nilai_Keluar", color_continuous_scale="Reds"
                )
                fig2.update_layout(yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig2, use_container_width=True)

    # --- TABEL DATA RINCIAN ---
    st.markdown("### 📋 Rincian Data Persediaan")
    st.dataframe(df, use_container_width=True)

else:
    st.error(f"Gagal mengambil data: {status}")
