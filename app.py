import streamlit as st
import pandas as pd
import plotly.express as px

# Konfigurasi Halaman
st.set_page_config(
    page_title="Dashboard Persediaan & Rekonsiliasi SiPPER",
    page_icon="📦",
    layout="wide"
)

# --- 1. FUNGSI PEMBUATAN DATA DUMMY (Jika belum ada upload file) ---
def load_dummy_data():
    data = {
        "kode_barang": ["BRG-001", "BRG-002", "BRG-003", "BRG-004", "BRG-005", "BRG-006"],
        "nama_barang": ["Kertas HVS A4 80gr", "Toner Printer Laser", "Map Folio Kertas", "Buku Agenda", "Pulpen Gel Hitam", "Baterai AA"],
        "kategori": ["ATK", "ATK", "ATK", "Barang Cetak", "ATK", "Perlengkapan"],
        "unit_skpd": ["Sekretariat", "Dinas Pendidikan", "Dinkes", "Sekretariat", "Dinas PUPR", "Dinas Pertanian"],
        "stok_buku": [150, 20, 300, 50, 400, 35],
        "stok_fisik": [150, 18, 310, 50, 390, 35],
        "min_stok": [50, 10, 50, 20, 100, 50],
        "harga_satuan": [55000, 850000, 2500, 35000, 4500, 12000],
        "status_rekon": ["Reconciled", "Discrepancy", "Discrepancy", "Reconciled", "Discrepancy", "Reconciled"]
    }
    return pd.DataFrame(data)

# --- 2. SIDEBAR (Pengaturan & Upload Data) ---
st.sidebar.title("📦 Kontrol Data")
uploaded_file = st.sidebar.file_uploader("Unggah File Data Persediaan (CSV)", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    st.sidebar.success("Data berhasil dimuat dari file upload!")
else:
    df = load_dummy_data()
    st.sidebar.info("Menggunakan Data Simulasi SiPPER.")

# Filter Kategori / Unit SKPD
skpd_list = ["Semua"] + sorted(df["unit_skpd"].unique().tolist())
selected_skpd = st.sidebar.selectbox("Filter Unit Kerja / SKPD:", skpd_list)

if selected_skpd != "Semua":
    df = df[df["unit_skpd"] == selected_skpd]

# --- 3. KALKULASI METRIK & FORMULA ---
df["nilai_buku"] = df["stok_buku"] * df["harga_satuan"]
df["nilai_fisik"] = df["stok_fisik"] * df["harga_satuan"]
df["selisih_qty"] = df["stok_fisik"] - df["stok_buku"]
df["selisih_nilai"] = df["selisih_qty"] * df["harga_satuan"]

total_nilai_buku = df["nilai_buku"].sum()
total_nilai_fisik = df["nilai_fisik"].sum()
total_item = len(df)
item_cocok = len(df[df["selisih_qty"] == 0])
ira_persen = (item_cocok / total_item * 100) if total_item > 0 else 0
net_selisih_nilai = df["selisih_nilai"].sum()

# --- 4. HEADER & KPI CARDS ---
st.title("📊 Monitoring Persediaan & Rekonsiliasi SiPPER")
st.caption("Dashboard Evaluasi Saldo Buku, Stock Opname Fisik, dan Verifikasi Transaksi")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Nilai Persediaan", f"Rp {total_nilai_buku:,.0f}".replace(",", "."))
col2.metric("Akurasi Stok (IRA)", f"{ira_persen:.1f}%")
col3.metric("Item Selisih Opname", f"{total_item - item_cocok} Item", delta=f"{total_item - item_cocok} periksa", delta_color="inverse")
col4.metric("Net Deviasi Nilai", f"Rp {net_selisih_nilai:,.0f}".replace(",", "."), delta=f"Rp {net_selisih_nilai:,.0f}".replace(",", "."))

st.markdown("---")

# --- 5. ALERT STOK KRITIS ---
st.subheader("⚠️ Peringatan Batas Stok Minimum (*Buffer Stock Alert*)")
stok_kritis = df[df["stok_fisik"] <= df["min_stok"]]

if not stok_kritis.empty:
    st.error(f"Ditemukan {len(stok_kritis)} barang dengan stok di bawah batas aman.")
    st.dataframe(
        stok_kritis[["kode_barang", "nama_barang", "stok_fisik", "min_stok", "unit_skpd"]],
        use_container_width=True
    )
else:
    st.success("Semua stok barang berada di atas batas minimum.")

# --- 6. GRAFIK & ANALISIS VISUAL ---
st.subheader("📈 Analisis Rekonsiliasi & Opname")
tab1, tab2 = st.tabs(["Perbandingan Fisik vs Buku", "Distribusi Nilai Persediaan"])

with tab1:
    fig_bar = px.bar(
        df,
        x="nama_barang",
        y=["stok_buku", "stok_fisik"],
        barmode="group",
        title="Perbandingan Kuantitas: Stok Buku SiPPER vs Stok Fisik",
        labels={"value": "Jumlah Unit", "nama_barang": "Nama Barang", "variable": "Jenis Stok"},
        color_discrete_map={"stok_buku": "#3366CC", "stok_fisik": "#109618"}
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with tab2:
    fig_pie = px.pie(
        df,
        names="kategori",
        values="nilai_buku",
        title="Komposisi Nilai Aset per Kategori",
        hole=0.4
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# --- 7. TABEL DETAIL & AUDIT TRAIL ---
st.subheader("📋 Rincian Audit Stok Opname")
st.dataframe(
    df[["kode_barang", "nama_barang", "kategori", "stok_buku", "stok_fisik", "selisih_qty", "selisih_nilai", "unit_skpd"]].style.map(
        lambda v: "background-color: #ffcccc" if isinstance(v, (int, float)) and v < 0 else ("background-color: #ccffcc" if isinstance(v, (int, float)) and v > 0 else ""),
        subset=["selisih_qty", "selisih_nilai"]
    ),
    use_container_width=True
)
