import asyncio
import io
import os
import re
import warnings
import pandas as pd
import plotly.express as px
import streamlit as st
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="Dashboard Live Monitoring Persediaan SiPPER HST",
    page_icon="📦",
    layout="wide"
)

# 1. KREDENSIAL DARI SECRETS STREAMLIT
USERNAME = st.secrets.get("SIPPER_USERNAME", "Administrator")
PASSWORD = st.secrets.get("SIPPER_PASSWORD", "12345678")
BASE_URL = "http://sipper.hstkab.go.id"

# 2. FUNGSI KONVERSI NILAI RUPIAH KE ANGKA
def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["-", "", "nan", "None", "null"]:
        return 0.0
    val_str = str(val).replace("Rp", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

# 3. FUNGSI OTOMASI BROWSER MENGAMBIL DATA LANGSUNG (HEADLESS)
async def scrape_sipper_auto():
    # Pastikan browser binaries terpasang jika di environment cloud
    try:
        os.system("playwright install chromium")
    except:
        pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Step A: Buka Halaman Utama SiPPER
            await page.goto(f"{BASE_URL}/", timeout=30000)

            # Step B: Login Otomatis
            # Mengisi form fUsr dan fPas
            await page.fill('input[name="fUsr"]', USERNAME)
            await page.fill('input[name="fPas"]', PASSWORD)
            await page.click('input[type="submit"], button[type="submit"], #login, input[value="Login"], input[value="Masuk"]')
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Step C: Buka Menu Laporan -> Rekap Semester
            target_report_url = f"{BASE_URL}/index.php?JdL=LAPORAN%20->%20REKAP%20DATA%20PER%20SEMESTER&IncFile=cmVrYXBfcGVyc2VkaWFhbl9zZW1lc3Rlcg==&IdL=VFhwck5VNTNQVDA9"
            await page.goto(target_report_url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=10000)

            # Step D: Klik Tombol "Rekap" di dalam Website
            # Coba cari tombol Rekap / Preview
            rekap_btn = page.locator('input[value="Rekap"], button:has-text("Rekap"), input[value="Preview"]')
            if await rekap_btn.count() > 0:
                await rekap_btn.first.click()
                await page.wait_for_timeout(3000)  # Tunggu AJAX memuat tabel

            # Step E: Ambil Isi HTML yang sudah lengkap dengan tabel data
            html_content = await page.content()
            await browser.close()

            # Parsing tabel
            tables = pd.read_html(io.StringIO(html_content))
            if not tables:
                return None, "Tabel data belum ditemukan pada halaman."

            # Pilih tabel yang memiliki kolom data barang (Kode / Deskripsi / Nilai)
            for t in tables:
                flat_text = " ".join([str(x) for x in t.values.flatten()]).lower()
                if "deskripsi" in flat_text or "saldo" in flat_text or "masuk" in flat_text or "bahan" in flat_text:
                    return t, "success"

            # Fallback ambil tabel terbesar
            df_max = max(tables, key=lambda t: t.shape[0] * t.shape[1])
            return df_max, "success"

        except Exception as e:
            await browser.close()
            return None, str(e)

@st.cache_data(ttl=600)  # Cache 10 menit agar tidak memberatkan server
def load_data():
    return asyncio.run(scrape_sipper_auto())

# --- 4. TAMPILAN DASHBOARD ---
st.title("📦 Dashboard Live Monitoring Persediaan (SiPPER HST)")
st.caption("Pemerintah Kabupaten Hulu Sungai Tengah — Data Disinkronkan Otomatis Secara Real-Time")

# Sidebar
st.sidebar.header("⚙️ Kontrol Sistem")
if st.sidebar.button("🔄 Sinkronisasi Ulang Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.info("Dashboard ini menarik data persediaan secara langsung dari sistem SiPPER tanpa perlu upload manual.")

# Load Data
with st.spinner("Mengakses sistem SiPPER HST dan menarik laporan semester..."):
    df_raw, status = load_data()

if df_raw is not None:
    df = df_raw.copy()

    # Bersihkan Header Bertingkat
    for i in range(min(5, len(df))):
        row_vals = [str(x).lower() for x in df.iloc[i].values]
        if any("deskripsi" in x or "kode" in x or "saldo" in x for x in row_vals):
            df.columns = df.iloc[i]
            df = df.iloc[i+1:].reset_index(drop=True)
            break

    # Standardisasi Nama Kolom
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

    if "Deskripsi" in df.columns:
        df = df[~df["Deskripsi"].astype(str).str.contains("Warning:|Kabupaten|KABUPATEN|None", na=False)]

    # Konversi Format Rupiah ke Numerik
    for c in ["Nilai_Masuk", "Nilai_Keluar", "Nilai_Saldo", "Qty_Saldo"]:
        if c in df.columns:
            df[c] = df[c].apply(clean_currency)

    # --- KARTU RINGKASAN METRIK ---
    st.markdown("### 📊 Ringkasan Nilai Persediaan")
    k1, k2, k3, k4 = st.columns(4)

    total_saldo = df["Nilai_Saldo"].sum() if "Nilai_Saldo" in df.columns else 0.0
    total_masuk = df["Nilai_Masuk"].sum() if "Nilai_Masuk" in df.columns else 0.0
    total_keluar = df["Nilai_Keluar"].sum() if "Nilai_Keluar" in df.columns else 0.0
    total_item = len(df)

    k1.metric("Total Saldo Akhir", f"Rp {total_saldo:,.0f}".replace(",", "."))
    k2.metric("Total Barang Masuk", f"Rp {total_masuk:,.0f}".replace(",", "."))
    k3.metric("Total Barang Keluar", f"Rp {total_keluar:,.0f}".replace(",", "."))
    k4.metric("Jumlah Item / Rekening", f"{total_item} Baris")

    st.markdown("---")

    # --- GRAFIK VISUALISASI ---
    c1, c2 = st.columns(2)
    if "Deskripsi" in df.columns and "Nilai_Saldo" in df.columns and df["Nilai_Saldo"].sum() > 0:
        with c1:
            top_saldo = df.nlargest(10, "Nilai_Saldo")
            fig1 = px.bar(
                top_saldo, x="Nilai_Saldo", y="Deskripsi",
                orientation="h", title="Top 10 Barang dengan Nilai Saldo Tertinggi",
                color="Nilai_Saldo", color_continuous_scale="Blues"
            )
            fig1.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig1, use_container_width=True)

    if "Deskripsi" in df.columns and "Nilai_Keluar" in df.columns and df["Nilai_Keluar"].sum() > 0:
        with c2:
            top_keluar = df.nlargest(10, "Nilai_Keluar")
            fig2 = px.bar(
                top_keluar, x="Nilai_Keluar", y="Deskripsi",
                orientation="h", title="Top 10 Barang dengan Pemakaian/Pengeluaran Terbesar",
                color="Nilai_Keluar", color_continuous_scale="Reds"
            )
            fig2.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig2, use_container_width=True)

    # --- TABEL DETAIL BARANG ---
    st.markdown("### 📋 Rincian Lengkap Data Barang")
    st.dataframe(df, use_container_width=True)

else:
    st.error(f"Gagal memuat data otomatis: {status}")
