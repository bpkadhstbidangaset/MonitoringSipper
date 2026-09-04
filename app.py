from io import BytesIO
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Dashboard Rekon SIPPER HST", page_icon="📦", layout="wide"
)

st.title("📦 Dashboard Monitoring & Rekonsiliasi SIPPER")
st.caption(
    "Monitoring Persediaan & Rekonsiliasi Data Internal vs Sistem SIPPER"
)

# --- SIDEBAR: KONFIGURASI KONEKSI SIPPER ---
st.sidebar.header("⚙️ Pengaturan Sumber Data SIPPER")

# Masukkan link AJAX dari tab Network
default_url = "https://sipper.hstkab.go.id/rekap_persemester_data.php"
endpoint_url = st.sidebar.text_input(
    "URL Endpoint SIPPER", value=default_url, help="Salin dari tab Network"
)

# Cookie sesi login (PHPSESSID)
session_cookie = st.sidebar.text_input(
    "Session Cookie (PHPSESSID)",
    type="password",
    help="Salin nilai cookie dari tab Headers browser",
)

col_fetch, col_info = st.sidebar.columns([1, 1])


# Fungsi Penarik Data SIPPER
@st.cache_data(ttl=300)
def fetch_sipper_data(url, cookie):
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      ),
      "Cookie": f"PHPSESSID={cookie}" if cookie else "",
  }
  try:
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
      tables = pd.read_html(response.text)
      if tables:
        df = tables[0]
        # Penyesuaian nama kolom bertingkat jika ada
        if isinstance(df.columns, pd.MultiIndex):
          df.columns = ["_".join(col).strip() for col in df.columns.values]
        return df, None
      return None, "Tabel data tidak ditemukan di halaman response."
    return None, f"Gagal mengakses web (HTTP Status: {response.status_code})"
  except Exception as e:
    return None, f"Error koneksi: {str(e)}"


# --- TABS UTAMA ---
tab_monitor, tab_rekon = st.tabs(
    ["📊 Data Live SIPPER", "⚖️ Rekonsiliasi Data"]
)

# TAB 1: MONITORING LIVE SIPPER
with tab_monitor:
  if st.button("🔄 Tarik / Refresh Data SIPPER"):
    st.session_state["refresh"] = True

  if endpoint_url:
    with st.spinner("Mengambil data dari SIPPER..."):
      df_sipper, err = fetch_sipper_data(endpoint_url, session_cookie)

    if err:
      st.warning(err)
      st.info(
          "Alternatif: Jika sesi login kedaluwarsa, Anda juga dapat mengunggah"
          " file ekspor HTML/Excel SIPPER secara manual di Tab Rekonsiliasi."
      )
    elif df_sipper is not None:
      st.success(
          f"Data berhasil dimuat! Total entri: {len(df_sipper)} baris barang."
      )

      # Metric Ringkas
      m1, m2 = st.columns(2)
      m1.metric("Total Jenis Barang", len(df_sipper))

      st.dataframe(df_sipper, use_container_width=True)

      # Tombol Download Data Bersih
      excel_buffer = BytesIO()
      df_sipper.to_excel(excel_buffer, index=False)
      st.download_button(
          label="📥 Unduh Data Ini ke Excel (.xlsx)",
          data=excel_buffer.getvalue(),
          file_name="data_sipper_terkini.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      )
  else:
    st.info("Masukkan Endpoint URL SIPPER pada panel samping.")

# TAB 2: PROSES REKONSILIASI
with tab_rekon:
  st.subheader("Bandingkan Data SIPPER vs Catatan Fisik / SPJ")

  col_up1, col_up2 = st.columns(2)
  with col_up1:
    file_internal = st.file_uploader(
        "1. Upload Data Internal / Fisik (Excel/CSV)", type=["xlsx", "csv"]
    )
  with col_up2:
    st.write("2. Sumber Data Pembanding:")
    use_live = st.checkbox(
        "Gunakan Data Live SIPPER dari Tab 1", value=True if endpoint_url else False
    )
    file_sipper_manual = None
    if not use_live:
      file_sipper_manual = st.file_uploader(
          "Upload File Cadangan SIPPER", type=["xlsx", "csv"]
      )

  if file_internal:
    # Membaca file internal
    df_in = (
        pd.read_excel(file_internal)
        if file_internal.name.endswith("xlsx")
        else pd.read_csv(file_internal)
    )

    # Menentukan sumber data SIPPER
    target_sipper_df = None
    if use_live and "df_sipper" in locals() and df_sipper is not None:
      target_sipper_df = df_sipper
    elif file_sipper_manual:
      target_sipper_df = (
          pd.read_excel(file_sipper_manual)
          if file_sipper_manual.name.endswith("xlsx")
          else pd.read_csv(file_sipper_manual)
      )

    if target_sipper_df is not None:
      st.markdown("---")
      st.subheader("Pemetaan Kolom Kunci Rekon")
      c_k1, c_k2, c_k3 = st.columns(3)

      # Pilih kolom penghubung (Key)
      key_in = c_k1.selectbox(
          "Kolom Kode di Data Internal", options=df_in.columns
      )
      key_sip = c_k2.selectbox(
          "Kolom Kode di Data SIPPER", options=target_sipper_df.columns
      )
      col_qty_sip = c_k3.selectbox(
          "Kolom Qty Saldo SIPPER", options=target_sipper_df.columns
      )

      # Penggabungan & Logika Deteksi Selisih
      df_merged = pd.merge(
          target_sipper_df,
          df_in,
          left_on=key_sip,
          right_on=key_in,
          how="outer",
          suffixes=("_SIPPER", "_INTERNAL"),
      )

      st.subheader("Hasil Rekonsiliasi")
      st.dataframe(df_merged, use_container_width=True)

      # Download Hasil Rekon
      out_rekon = BytesIO()
      df_merged.to_excel(out_rekon, index=False)
      st.download_button(
          label="📥 Unduh Hasil Rekonsiliasi (.xlsx)",
          data=out_rekon.getvalue(),
          file_name="hasil_rekon_persediaan.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      )
    else:
      st.warning(
          "Data SIPPER belum tersedia. Ambil data live di Tab 1 atau upload"
          " file cadangan."
      )
