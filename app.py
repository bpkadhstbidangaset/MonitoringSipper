import io
import re
import warnings
import pandas as pd
import pdfplumber
import plotly.express as px
import streamlit as st

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="Dashboard Monitoring Persediaan SiPPER HST",
    page_icon="📦",
    layout="wide"
)

# 1. FUNGSI MEMBERSIHKAN FORMAT RUPIAH KE ANGKA
def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["-", "", "nan", "None", "null"]:
        return 0.0
    val_str = str(val).replace("Rp", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

# 2. FUNGSI PARSER TABEL DARI PDF LAPORAN SIPPER
def parse_sipper_pdf(pdf_file):
    all_rows = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Filter baris yang tidak kosong sama sekali
                    clean_row = [cell.strip() if cell is not None else "" for cell in row]
                    if any(clean_row):
                        all_rows.append(clean_row)
                        
    if not all_rows:
        return None, "Tidak ditemukan tabel pada file PDF."

    # Cari panjang kolom terbanyak untuk menyelaraskan dataframe
    max_cols = max(len(r) for r in all_rows)
    standardized_rows = [r + [""] * (max_cols - len(r)) for r in all_rows]
    
    df_raw = pd.DataFrame(standardized_rows)
    
    # Deteksi baris header (mencari kata Deskripsi, Rekening, Saldo, Nama Barang, dll)
    header_idx = -1
    for i in range(min(10, len(df_raw))):
        row_str = " ".join([str(x).lower() for x in df_raw.iloc[i].values])
        if any(k in row_str for k in ["deskripsi", "nama barang", "kode", "uraian", "saldo"]):
            header_idx = i
            break
            
    if header_idx != -1:
        df_raw.columns = df_raw.iloc[header_idx]
        df_data = df_raw.iloc[header_idx + 1:].reset_index(drop=True)
    else:
        df_data = df_raw

    # Standardisasi Nama Kolom
    col_mapping = {}
    for col in df_data.columns:
        c_str = str(col).lower()
        if any(k in c_str for k in ["deskripsi", "nama barang", "uraian", "nama rekening"]):
            col_mapping[col] = "Deskripsi"
        elif "kode" in c_str:
            col_mapping[col] = "Kode"
        elif "masuk" in c_str and ("nilai" in c_str or "rupiah" in c_str or "rp" in c_str or "harga" in c_str):
            col_mapping[col] = "Nilai_Masuk"
        elif "keluar" in c_str and ("nilai" in c_str or "rupiah" in c_str or "rp" in c_str or "harga" in c_str):
            col_mapping[col] = "Nilai_Keluar"
        elif "saldo" in c_str and ("nilai" in c_str or "rupiah" in c_str or "rp" in c_str or "harga" in c_str):
            col_mapping[col] = "Nilai_Saldo"
        elif "saldo" in c_str and ("qty" in c_str or "jumlah" in c_str or "kuantitas" in c_str):
            col_mapping[col] = "Qty_Saldo"
        elif "satuan" in c_str:
            col_mapping[col] = "Satuan"

    df_data = df_data.rename(columns=col_mapping)
    
    # Hapus baris total summary atau judul banner di tengah halaman
    if "Deskripsi" in df_data.columns:
        df_data = df_data[~df_data["Deskripsi"].astype(str).str.contains("JUMLAH|TOTAL|Kabupaten|KABUPATEN|Hulu Sungai Tengah|None|^$", regex=True, na=False)]
    
    # Konversi Nilai Rupiah
    for col_val in ["Nilai_Masuk", "Nilai_Keluar", "Nilai_Saldo", "Qty_Saldo"]:
        if col_val in df_data.columns:
            df_data[col_val] = df_data[col_val].apply(clean_currency)
            
    return df_data, "success"

# --- 3. TAMPILAN DASHBOARD STREAMLIT ---
st.title("📦 Dashboard Monitoring Persediaan (SiPPER HST)")
st.caption("Pemerintah Kabupaten Hulu Sungai Tengah — Parser Otomatis Laporan PDF")

# Sidebar Upload
st.sidebar.header("📁 Unggah Laporan PDF")
uploaded_pdf = st.sidebar.file_uploader(
    "Pilih file PDF Rekap / Mutasi SiPPER:",
    type=["pdf"],
    help="Upload file laporan berformat PDF hasil cetak dari menu SiPPER HST."
)

if uploaded_pdf is not None:
    with st.spinner("Membaca dan mengekstrak tabel dari PDF..."):
        df, status = parse_sipper_pdf(uploaded_pdf)

    if df is not None and not df.empty:
        st.success(f"✅ Berhasil memproses data dari file **{uploaded_pdf.name}**")

        # --- KARTU METRIK UTAMA (KPI) ---
        st.markdown("### 📊 Ringkasan Nilai Persediaan")
        k1, k2, k3, k4 = st.columns(4)

        total_saldo = df["Nilai_Saldo"].sum() if "Nilai_Saldo" in df.columns else 0.0
        total_masuk = df["Nilai_Masuk"].sum() if "Nilai_Masuk" in df.columns else 0.0
        total_keluar = df["Nilai_Keluar"].sum() if "Nilai_Keluar" in df.columns else 0.0
        total_item = len(df)

        k1.metric("Total Saldo Akhir", f"Rp {total_saldo:,.0f}".replace(",", "."))
        k2.metric("Total Pengadaan (Masuk)", f"Rp {total_masuk:,.0f}".replace(",", "."))
        k3.metric("Total Pengeluaran", f"Rp {total_keluar:,.0f}".replace(",", "."))
        k4.metric("Jumlah Item / Rekening", f"{total_item} Item")

        st.markdown("---")

        # --- GRAFIK VISUALISASI ---
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

        # --- TABEL DETAIL RINCIAN & DOWNLOAD EXCEL ---
        st.markdown("### 📋 Rincian Data Barang Persediaan")
        
        # Fitur Pencarian Barang
        search_query = st.text_input("🔍 Cari Nama / Kode Barang:", "")
        if search_query:
            df_filtered = df[df.apply(lambda row: search_query.lower() in row.astype(str).str.lower().values, axis=1)]
        else:
            df_filtered = df

        st.dataframe(df_filtered, use_container_width=True)

        # Tombol Download ke Format Excel Bersih
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="Data_Persediaan")
            
        st.download_button(
            label="📥 Download Hasil Ekstraksi ke Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"Rekap_Persediaan_{uploaded_pdf.name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error(f"Gagal memproses file PDF: {status}")
else:
    # Tampilan saat belum ada file yang diupload
    st.info("👈 Silakan unggah file PDF Laporan Rekap/Mutasi dari SiPPER melalui panel di sebelah kiri.")
    st.markdown("""
    #### 💡 Panduan Cepat:
    1. Buka SiPPER HST $\rightarrow$ Pilih Menu **Laporan** (Rekap Semester / Mutasi).
    2. Klik tombol **Cetak / Simpan sebagai PDF**.
    3. Unggah file PDF tersebut ke sidebar dashboard ini.
    4. Dashboard akan secara otomatis memproses tabel, menghitung saldo, membuat grafik, dan menyediakan tombol unduh ke Excel.
    """)
