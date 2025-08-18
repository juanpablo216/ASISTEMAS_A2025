# app.py
import streamlit as st
import pandas as pd
import numpy as np
import io, csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Pt
from datetime import datetime

# ------------------- Apariencia global -------------------
st.set_page_config(page_title="CAAT – Auditoría Automatizada", layout="wide")

st.markdown("""
<style>
/* Contenedor más ancho y con aire */
.main .block-container {max-width: 1250px; padding-top: 0.5rem; padding-bottom: 2.2rem;}
/* Título principal */
h1 { font-size: 34px !important; margin-bottom: .4rem !important; }
/* Tabs grandes y visibles */
.stTabs [data-baseweb="tab-list"] { gap: 10px; }
.stTabs [data-baseweb="tab"] {
  height: 60px; border-radius: 12px !important; padding: 14px 22px !important;
  background: #f6f7fb; border: 1px solid rgba(47,58,178,.15);
  font-size: 18px !important; font-weight: 700;
}
.stTabs [aria-selected="true"] {
  background: #eef2ff !important; color: #2f3ab2 !important;
  border: 2px solid #2f3ab2 !important;
}
/* Tarjetas y acordeones */
.section-card {
  border: 1px solid rgba(125,125,125,.22);
  border-radius: 16px; padding: 18px 20px; margin: 16px 0 24px 0;
  background: #ffffff;
  box-shadow: 0 1px 0 rgba(0,0,0,0.04);
}
.section-title { font-size: 26px; font-weight: 800; margin-bottom: 6px; }
.section-desc  { font-size: 17px; color:#374151; }
/* File uploader más alto */
[data-testid="stFileUploader"] {border-radius: 12px; border: 1px dashed rgba(125,125,125,.35); padding: 18px;}
/* Botones redondeados */
.stButton>button { border-radius: 999px !important; padding: .6rem 1.1rem; font-weight: 700; }
.big-warning { font-size: 16px; line-height: 1.35; }
</style>
""", unsafe_allow_html=True)

st.title("🧪 Herramienta CAAT – Auditoría Automatizada")
st.caption("Sube archivos y ejecuta las pruebas. Soporta **CSV/XLSX/XLS/TXT**. Descargas en **XLSX/DOCX**.")

# ============================ Utilidades comunes ============================
SINONIMOS_ID = ["idfactura","id_factura","numero","número","numerofactura","numero_factura",
    "serie","serie_comprobante","clave_acceso","idtransaccion","id_transaccion","referencia","doc","documento","id","idcliente","idproveedor"]
SINONIMOS_MONTO = ["total","monto","importe","valor","monto_total","total_ingresado",
    "importe_total","importe neto","subtotal+iva","total factura","totalfactura","amount","total_amount"]
SINONIMOS_FECHA = ["fecha","fecha_emision","fecha emisión","f_emision","fecha documento",
    "fecha_doc","fechadoc","fecha fact","fecha factura","emision","date","fecha_registro"]

def sniff_delimiter(sample_bytes: bytes):
    try:
        sample = sample_bytes.decode('utf-8', errors='ignore')
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        return dialect.delimiter
    except Exception:
        return None

def try_read_csv(file_obj):
    data = file_obj.read()
    if isinstance(data, bytes):
        delim = sniff_delimiter(data[:4096])
        bio = io.BytesIO(data)
        if delim:
            try: return pd.read_csv(bio, sep=delim, engine="python")
            except Exception: pass
        bio.seek(0)
        try: return pd.read_csv(bio, sep=None, engine="python")
        except Exception:
            bio.seek(0); return pd.read_csv(bio, sep=None, engine="python", encoding="latin-1")
    else:
        return pd.read_csv(io.StringIO(data))

def try_read_excel(file_obj, widget_key="sheet"):
    xls = pd.ExcelFile(file_obj)
    sheet = st.selectbox("📄 Hoja de Excel", xls.sheet_names, key=widget_key)
    return pd.read_excel(xls, sheet_name=sheet)

def load_any(file, widget_key="sheet"):
    name = file.name.lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        return try_read_csv(file)
    if name.endswith((".xlsx",".xls")):
        return try_read_excel(file, widget_key=widget_key)
    raise ValueError("Formato no soportado")

def normalize_headers(df): df.columns = [str(c).strip() for c in df.columns]; return df
def col_auto(df, candidatos):
    cols_norm = {c.lower().strip(): c for c in df.columns}
    for alias in candidatos:
        if alias in cols_norm: return cols_norm[alias]
    for c in df.columns:
        if any(alias in c.lower() for alias in candidatos): return c
    return None
def coerce_amount(series):
    s = series.astype(str).str.replace(r"\.", "", regex=True).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")
def coerce_date(series): return pd.to_datetime(series, errors="coerce", dayfirst=True)

def to_xlsx_bytes(df, sheet_name="Hoja1"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w: df.to_excel(w, index=False, sheet_name=sheet_name[:31])
    return buf.getvalue()

def to_multi_xlsx_bytes(sheets: dict):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            nm = str(name)[:31]
            if isinstance(df, pd.DataFrame): df.to_excel(w, index=False, sheet_name=nm)
            else: pd.DataFrame({"valor":[df]}).to_excel(w, index=False, sheet_name=nm)
    return buf.getvalue()

def docx_from_sections(title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    d = Document(); d.add_heading(title, level=1)
    for heading, bullets in sections:
        d.add_heading(heading, level=2)
        for item in bullets:
            p = d.add_paragraph(item, style="List Bullet"); p.style.font.size = Pt(11)
    bio = io.BytesIO(); d.save(bio); return bio.getvalue()

# ============================ MÓDULO 1: Montos Inusuales ============================
def ui_montos_inusuales():
    st.markdown('<div class="section-card"><div class="section-title">2️⃣ Detección de Montos Inusuales</div><div class="section-desc">Encuentra transacciones que superan un umbral (fijo o estadístico) y descarga hallazgos en XLSX y un reporte detallado en DOCX.</div></div>', unsafe_allow_html=True)

    file_unusual = st.file_uploader("📁 Subir archivo (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="unusual")
    if not file_unusual: return

    dfm = load_any(file_unusual, widget_key="sheet_unusual"); dfm = normalize_headers(dfm)
    st.success(f"✅ Archivo cargado. Filas: {len(dfm)}")
    with st.expander("Vista previa (primeras filas)", expanded=False): st.dataframe(dfm.head())

    sug_monto = col_auto(dfm, SINONIMOS_MONTO) or (dfm.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
    col_monto = st.selectbox("💰 Columna de monto", dfm.columns.tolist(),
                             index=(dfm.columns.tolist().index(sug_monto) if sug_monto in dfm.columns else 0))
    col_id = st.selectbox("🔑 Columna identificadora (opcional)", ["(ninguna)"] + dfm.columns.tolist(), index=0)
    col_fecha_opt = st.selectbox("📅 Columna de fecha (opcional)", ["(ninguna)"] + dfm.columns.tolist(), index=0)

    metodo = st.radio("Método", ["Umbral fijo", "Umbral estadístico (media + k·σ)"], horizontal=True)
    if metodo.startswith("Umbral fijo"):
        umbral = st.number_input("💵 Umbral fijo ($):", min_value=0.0, value=10000.0)
        ejecutar = st.button("🔍 Ejecutar (fijo)")
    else:
        k = st.slider("🔬 k (media + k·σ)", min_value=1, max_value=5, value=2)
        ejecutar = st.button("🔍 Ejecutar (estadístico)")

    if not ejecutar: return

    serie_monto = dfm[col_monto]
    if serie_monto.dtype == object: serie_monto = coerce_amount(serie_monto)
    dfm["_MONTO_"] = pd.to_numeric(serie_monto, errors="coerce")
    base = dfm.dropna(subset=["_MONTO_"]).copy()

    if col_fecha_opt != "(ninguna)": base["_FECHA_"] = coerce_date(base[col_fecha_opt])

    if metodo.startswith("Umbral fijo"):
        limite = umbral; criterio_txt = f"Umbral fijo = {umbral:,.2f}"
    else:
        media = base["_MONTO_"].mean(); std = base["_MONTO_"].std(ddof=0); limite = media + k*std
        criterio_txt = f"Umbral estadístico = media {media:,.2f} + {k}·σ {std:,.2f} → {limite:,.2f}"

    hall = base[base["_MONTO_"] > limite].copy()
    total_tx, total_h = len(base), len(hall)
    prop_h = (total_h/total_tx) if total_tx else 0.0
    suma_total, suma_h = base["_MONTO_"].sum(), hall["_MONTO_"].sum()

    st.subheader("📊 Resultados")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Analizadas", total_tx); c2.metric("Hallazgos", total_h)
    c3.metric("% hallazgos", f"{prop_h*100:.2f}%"); c4.metric("Suma hallazgos", f"{suma_h:,.2f}")
    st.caption(f"**Criterio aplicado:** {criterio_txt}")

    if total_h == 0:
        st.success("✅ No se encontraron montos inusuales.")
        return

    mu = base["_MONTO_"].mean(); sd = base["_MONTO_"].std(ddof=0) or 1.0
    hall["_zscore_"] = (hall["_MONTO_"] - mu) / sd
    top_monto = hall.sort_values("_MONTO_", ascending=False).head(20)
    top_z = hall.sort_values("_zscore_", ascending=False).head(20)

    grp = pd.DataFrame()
    if col_id != "(ninguna)" and col_id in hall.columns:
        grp = (hall.groupby(col_id, dropna=False).agg(N=("_MONTO_","count"), Suma=("_MONTO_","sum"), Max=("_MONTO_","max"))
                     .sort_values("Suma", ascending=False).head(20))

    # XLSX multi-hojas
    sheets = {"Hallazgos": hall,
              "ResumenEstadistico": pd.DataFrame({
                  "Métrica":["Transacciones","Hallazgos","% hallazgos","Suma total","Suma hallazgos","Criterio"],
                  "Valor":[total_tx, total_h, f"{prop_h*100:.2f}%", f"{suma_total:,.2f}", f"{suma_h:,.2f}", criterio_txt]
              }),
              "TopPorMonto": top_monto, "TopPorZscore": top_z}
    if not grp.empty: sheets["GrupoPorID"] = grp.reset_index()

    st.download_button("⬇️ Descargar hallazgos (XLSX)",
                       to_multi_xlsx_bytes(sheets), "montos_inusuales.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with st.expander("Ver tabla de hallazgos", expanded=False): st.dataframe(hall.head(1000))

    # DOCX detallado
    fecha_rango = "Sin fecha" if "_FECHA_" not in base.columns else f"{base['_FECHA_'].min()} → {base['_FECHA_'].max()}"
    bullets_resumen = [
        f"Archivo: {file_unusual.name}", f"Válidas: {total_tx}",
        f"Hallazgos: {total_h} ({prop_h*100:.2f}%)", f"Suma hallazgos: {suma_h:,.2f} (vs total {suma_total:,.2f})",
        f"Criterio: {criterio_txt}", f"Rango de fechas: {fecha_rango}"
    ]
    detalle = []
    if total_h>0:
        detalle += [f"Mayor hallazgo: {hall['_MONTO_'].max():,.2f}",
                    f"Promedio hallazgos: {hall['_MONTO_'].mean():,.2f}"]
        if col_id != "(ninguna)" and col_id in hall.columns:
            top_id = hall.groupby(col_id)["_MONTO_"].sum().sort_values(ascending=False).head(5)
            detalle.append("Top 5 por suma (ID): " + ", ".join([f"{i}: {v:,.2f}" for i,v in top_id.items()]))

    recomendaciones = [
        "Solicitar respaldo documental (OC, contratos, aprobaciones) y verificar trazabilidad en el ERP.",
        "Ejecutar revisiones dirigidas sobre los 20 mayores importes y 20 mayores z-scores.",
        "Validar límites de aprobación/segregación; comparar con el flujo de autorizaciones efectivas.",
        "Analizar concentración por ID, centro de costo y periodo; buscar patrones a fin de mes/cierre.",
        "Cruzar con políticas de precios/ descuentos, impuestos y redondeos.",
        "Si el % supera materialidad, ampliar muestra y aplicar pruebas sustantivas adicionales."
    ]
    sections = [("RESUMEN", [f"• {x}" for x in bullets_resumen]),
                ("DETALLE PRINCIPAL", [f"• {x}" for x in detalle] if detalle else ["• Sin detalles adicionales."]),
                ("RECOMENDACIONES", [f"• {x}" for x in recomendaciones]),
                ("REFERENCIA XLSX", ["• Ver 'montos_inusuales.xlsx' (Hoja Hallazgos, ResumenEstadistico, TopPorMonto, TopPorZscore, GrupoPorID si aplica)."])]
    st.download_button("⬇️ Descargar reporte (DOCX)",
                       docx_from_sections("Montos Inusuales – Reporte de Auditoría", sections),
                       "reporte_montos_inusuales.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# ============================ MÓDULO 2: Conciliación ============================
def ui_conciliacion():
    st.markdown('<div class="section-card"><div class="section-title">3️⃣ Conciliación de Reportes (A vs. B)</div><div class="section-desc">Compara dos fuentes (p. ej., Facturación vs. Contabilidad). Descarga un XLSX con hallazgos y un reporte DOCX detallado.</div></div>', unsafe_allow_html=True)

    colA, colB = st.columns(2)
    with colA: file_A = st.file_uploader("📁 Archivo A", type=["csv","xlsx","xls","txt"], key="conc_a")
    with colB: file_B = st.file_uploader("📁 Archivo B", type=["csv","xlsx","xls","txt"], key="conc_b")
    if not (file_A and file_B): return

    A = load_any(file_A, widget_key="sheet_A"); A = normalize_headers(A)
    B = load_any(file_B, widget_key="sheet_B"); B = normalize_headers(B)
    st.success(f"✅ Cargados A={len(A)} filas, B={len(B)} filas")
    with st.expander("Vista previa", expanded=False):
        st.write("A"); st.dataframe(A.head()); st.write("B"); st.dataframe(B.head())

    comunes = [c for c in A.columns if c in set(B.columns)]
    if not comunes: st.error("No hay columnas en común."); return

    clave_sug = col_auto(A, SINONIMOS_ID) if col_auto(A, SINONIMOS_ID) in comunes else comunes[0]
    montoA_sug = col_auto(A, SINONIMOS_MONTO) or (A.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
    montoB_sug = col_auto(B, SINONIMOS_MONTO) or (B.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
    fechaA_sug = col_auto(A, SINONIMOS_FECHA); fechaB_sug = col_auto(B, SINONIMOS_FECHA)

    st.subheader("🔧 Configuración")
    clave = st.selectbox("🔑 Clave común", comunes, index=(comunes.index(clave_sug) if clave_sug in comunes else 0))
    monto_A = st.selectbox("💰 Monto en A", A.columns.tolist(), index=(A.columns.tolist().index(montoA_sug) if (montoA_sug in A.columns) else 0))
    monto_B = st.selectbox("💰 Monto en B", B.columns.tolist(), index=(B.columns.tolist().index(montoB_sug) if (montoB_sug in B.columns) else 0))
    fecha_A_opt = st.selectbox("📅 Fecha en A (opcional)", ["(ninguna)"] + A.columns.tolist(),
                               index=(["(ninguna)"] + A.columns.tolist()).index(fechaA_sug) if (fechaA_sug in A.columns) else 0)
    fecha_B_opt = st.selectbox("📅 Fecha en B (opcional)", ["(ninguna)"] + B.columns.tolist(),
                               index=(["(ninguna)"] + B.columns.tolist()).index(fechaB_sug) if (fechaB_sug in B.columns) else 0)
    tolerancia = st.number_input("🎯 Tolerancia de monto", min_value=0.0, value=0.0)

    if not st.button("🔍 Ejecutar conciliación"): return

    A["_CLAVE_"] = A[clave].astype(str).str.strip().str.upper()
    B["_CLAVE_"] = B[clave].astype(str).str.strip().str.upper()
    A["_MONTO_"] = coerce_amount(A[monto_A]) if A[monto_A].dtype == object else pd.to_numeric(A[monto_A], errors="coerce")
    B["_MONTO_"] = coerce_amount(B[monto_B]) if B[monto_B].dtype == object else pd.to_numeric(B[monto_B], errors="coerce")
    if fecha_A_opt != "(ninguna)": A["_FECHA_"] = coerce_date(A[fecha_A_opt])
    if fecha_B_opt != "(ninguna)": B["_FECHA_"] = coerce_date(B[fecha_B_opt])

    merged = A.merge(B, on="_CLAVE_", how="outer", suffixes=("_A","_B"), indicator=True)
    solo_A = merged[merged["_merge"]=="left_only"].copy()
    solo_B = merged[merged["_merge"]=="right_only"].copy()
    coinc   = merged[merged["_merge"]=="both"].copy()
    coinc["_diff_monto"] = (coinc["_MONTO__A"] - coinc["_MONTO__B"])
    coinc["_diff_monto_abs"] = coinc["_diff_monto"].abs()
    diff_monto = coinc[coinc["_diff_monto_abs"] > tolerancia].copy()

    diff_fecha = pd.DataFrame()
    if "_FECHA__A" in coinc.columns and "_FECHA__B" in coinc.columns:
        diff_fecha = coinc[(~coinc["_FECHA__A"].isna()) & (~coinc["_FECHA__B"].isna()) & (coinc["_FECHA__A"] != coinc["_FECHA__B"])][["_CLAVE_","_FECHA__A","_FECHA__B"]].copy()

    total_A, total_B = A["_MONTO_"].sum(skipna=True), B["_MONTO_"].sum(skipna=True)
    delta_total = total_A - total_B
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Solo en A", len(solo_A)); c2.metric("Solo en B", len(solo_B))
    c3.metric("Dif. monto", len(diff_monto)); c4.metric("Δ A-B", f"{delta_total:,.2f}")

    # XLSX consolidado
    sheets = {
        "Resumen": pd.DataFrame({
            "Métrica":["Total A","Total B","Δ A-B","Solo en A (n)","Solo en B (n)","Dif. monto (n)","Dif. fecha (n)","Tolerancia"],
            "Valor":[f"{total_A:,.2f}", f"{total_B:,.2f}", f"{delta_total:,.2f}", len(solo_A), len(solo_B), len(diff_monto), len(diff_fecha), f"{tolerancia:,.2f}"]
        }),
        "Solo_en_A": solo_A, "Solo_en_B": solo_B,
        "Diferencias_Monto": diff_monto[["_CLAVE_","_MONTO__A","_MONTO__B","_diff_monto","_diff_monto_abs"]],
        "Diferencias_Fecha": diff_fecha if not diff_fecha.empty else pd.DataFrame(columns=["_CLAVE_","_FECHA__A","_FECHA__B"])
    }
    st.download_button("⬇️ Descargar hallazgos (XLSX)",
                       to_multi_xlsx_bytes(sheets), "hallazgos_conciliacion.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("Ver tablas resumidas", expanded=False):
        st.write("🟦 Solo en A"); st.dataframe(solo_A.head(1000))
        st.write("🟧 Solo en B"); st.dataframe(solo_B.head(1000))
        st.write("🟥 Diferencias de monto"); st.dataframe(diff_monto[["_CLAVE_","_MONTO__A","_MONTO__B","_diff_monto","_diff_monto_abs"]].head(1000))
        if not diff_fecha.empty:
            st.write("🟨 Diferencias de fecha"); st.dataframe(diff_fecha.head(1000))

    # DOCX detallado
    top_dif = diff_monto.sort_values("_diff_monto_abs", ascending=False).head(10)
    pos = diff_monto[diff_monto["_diff_monto"] > 0]["_diff_monto"].sum()
    neg = diff_monto[diff_monto["_diff_monto"] < 0]["_diff_monto"].sum()
    bullets = [
        f"Archivo A: {file_A.name} | Archivo B: {file_B.name}",
        f"Total A: {total_A:,.2f} | Total B: {total_B:,.2f} | Δ A-B: {delta_total:,.2f}",
        f"Solo en A: {len(solo_A)} | Solo en B: {len(solo_B)}",
        f"Dif. monto (> tol.): {len(diff_monto)} | Suma Δ+ {pos:,.2f} | Δ- {neg:,.2f}",
        f"Dif. fecha: {len(diff_fecha)}", f"Tolerancia aplicada: {tolerancia:,.2f}"
    ]
    det = [f"{r.get('_CLAVE_','s/clave')}: A={r.get('_MONTO__A',np.nan):,.2f} | B={r.get('_MONTO__B',np.nan):,.2f} | Δ={r.get('_diff_monto',np.nan):,.2f} (|Δ|={r.get('_diff_monto_abs',np.nan):,.2f})"
           for _,r in top_dif.iterrows()] or ["No hay diferencias de monto sobre la tolerancia."]
    rec = [
        "Revisar interfaz/logs, horarios de corte y reprocesos entre A y B.",
        "En diferencias de monto: confirmar TC, descuentos, impuestos, notas de crédito, redondeos.",
        "Descartar asientos manuales fuera del flujo; revisar bitácoras y perfiles.",
        "Establecer conciliaciones automáticas periódicas con umbrales por tipo de transacción.",
        "Investigar Solo en A/B: reprocesar interfaz y validar dependencia temporal (cierres)."
    ]
    sections = [("RESUMEN", [f"• {x}" for x in bullets]),
                ("TOP 10 DIFERENCIAS", [f"• {x}" for x in det]),
                ("RECOMENDACIONES", [f"• {x}" for x in rec]),
                ("REFERENCIA XLSX", ["• Ver 'hallazgos_conciliacion.xlsx' (Resumen, Solo_en_A, Solo_en_B, Diferencias_Monto, Diferencias_Fecha)."])]
    st.download_button("⬇️ Descargar reporte (DOCX)",
                       docx_from_sections("Conciliación A vs. B – Reporte de Auditoría", sections),
                       "reporte_conciliacion.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# ============================ MÓDULO 3: Benford ============================
def first_digit_series(series: pd.Series) -> pd.Series:
    if series.dtype == object: x = coerce_amount(series)
    else: x = pd.to_numeric(series, errors="coerce")
    x = x.abs(); x = x[x > 0].dropna()
    s = x.apply(lambda v: f"{v:.15g}").str.replace(".", "", regex=False).str.lstrip("0")
    first = s.str[0].dropna(); first = first[first.str.contains(r"[1-9]", regex=True)]
    return first.astype(int)

def benford_expected() -> pd.Series:
    d = np.arange(1, 10); return pd.Series(np.log10(1 + 1/d), index=d)

def ui_benford():
    st.markdown('<div class="section-card"><div class="section-title">4️⃣ Ley de Benford aplicada a transacciones</div><div class="section-desc">Contrasta el primer dígito con Benford, lista transacciones sospechosas y permite descargar XLSX/DOCX.</div></div>', unsafe_allow_html=True)

    st.markdown("""
<div class="section-card"><div class="big-warning">
<strong>⚠️ Advertencia:</strong> Benford es válido para conjuntos grandes <em>no pre-condicionados</em>. Evitar precios fijos, topes/mínimos, folios o montos prefijados.
</div></div>
""", unsafe_allow_html=True)

    file_ben = st.file_uploader("📁 Subir archivo (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="benford")
    if not file_ben: return

    dfb = load_any(file_ben, widget_key="sheet_benford"); dfb = normalize_headers(dfb)
    st.success(f"✅ Archivo cargado. Filas: {len(dfb)}")
    with st.expander("Vista previa", expanded=False): st.dataframe(dfb.head())

    def is_amount_candidate(s: pd.Series) -> bool:
        if pd.api.types.is_numeric_dtype(s): return True
        if s.dtype == object: return coerce_amount(s).notna().mean() >= 0.30
        return False
    candidatas = [c for c in dfb.columns if is_amount_candidate(dfb[c])]
    if not candidatas: st.error("No hay columnas de monto válidas."); return

    sug = col_auto(dfb[candidatas], SINONIMOS_MONTO) or candidatas[0]
    col_m = st.selectbox("💰 Columna de monto", candidatas, index=(candidatas.index(sug) if sug in candidatas else 0))
    min_val = st.number_input("🔻 Ignorar montos menores a", min_value=0.0, value=0.0)
    min_count = st.number_input("🔔 Mínimo sugerido de observaciones", min_value=0, value=100)
    desvio_min = st.number_input("🎚 Umbral de desviación por dígito (pp)", min_value=0.0, value=2.0, step=0.5)

    if not st.button("🔍 Ejecutar Benford"): return

    serie_orig = dfb[col_m]
    if serie_orig.dtype == object:
        conv = coerce_amount(serie_orig)
        if conv.notna().mean() < 0.30: st.error("La columna elegida no se convierte a número (≥30%)."); return
        serie_num = conv
    else:
        serie_num = pd.to_numeric(serie_orig, errors="coerce")

    serie_num = serie_num.dropna()
    if min_val>0: serie_num = serie_num[serie_num.abs() >= min_val]

    n_total = len(serie_num)
    fd = first_digit_series(serie_num)     # FIX: Series, no ndarray
    n = len(fd)
    if n==0: st.error("No hay datos suficientes tras filtros."); return

    obs_counts = fd.value_counts().reindex(range(1,10), fill_value=0).sort_index()
    obs_prop   = obs_counts / n
    exp_prop   = benford_expected()
    exp_counts = exp_prop * n
    chi2 = (((obs_counts - exp_counts) ** 2) / exp_counts.replace(0, np.nan)).sum()
    chi2_crit = 15.507
    cumple = chi2 <= chi2_crit

    st.subheader("📊 Resumen Benford")
    c1,c2,c3 = st.columns(3)
    c1.metric("Observaciones válidas", n); c2.metric("Chi-cuadrado", f"{chi2:,.3f}"); c3.metric("¿Cumple (α=0.05)?", "Sí ✅" if cumple else "No ⚠️")
    if n < min_count: st.info(f"ℹ️ Nota: {n} obs.; sugerido ≥ {min_count}.")

    tabla = pd.DataFrame({
        "Dígito": list(range(1,10)),
        "Frecuencia Observada": obs_counts.values,
        "Proporción Observada (%)": (obs_prop.values*100).round(2),
        "Proporción Esperada (%)": (exp_prop.values*100).round(2),
        "Desviación (pp)": ((obs_prop-exp_prop).values*100).round(2)
    })
    st.dataframe(tabla)

    fig, ax = plt.subplots()
    idx = np.arange(1,10)
    ax.bar(idx-0.15, obs_prop.values, width=0.3, label="Observado")
    ax.bar(idx+0.15, exp_prop.values, width=0.3, label="Esperado (Benford)")
    ax.set_xticks(idx); ax.set_xlabel("Primer dígito"); ax.set_ylabel("Proporción"); ax.set_title("Benford: Observado vs Esperado"); ax.legend()
    st.pyplot(fig)

    sospechosos_dig = tabla.loc[tabla["Desviación (pp)"] >= desvio_min, "Dígito"].tolist()
    st.write(f"**Dígitos marcados (≥ {desvio_min:.1f} pp):** {sospechosos_dig if sospechosos_dig else 'Ninguno'}")

    fd_full = first_digit_series(serie_num)
    sospe_idx = fd_full[fd_full.isin(sospechosos_dig)].index
    sospe_rows = dfb.loc[sospe_idx].copy()
    sospe_rows["_monto_convertido_"] = serie_num.loc[sospe_idx]
    sospe_rows["_1er_dig"] = fd_full.loc[sospe_idx]

    with st.expander("Ver sospechosas", expanded=False):
        if len(sospe_rows):
            st.dataframe(sospe_rows.head(1000))
            st.download_button("⬇️ Descargar sospechosas (XLSX)",
                               to_xlsx_bytes(sospe_rows, "Sospechosas_Benford"),
                               "benford_sospechosas.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No hay transacciones sospechosas con el umbral dado.")

    st.download_button("⬇️ Descargar resumen (XLSX)",
                       to_xlsx_bytes(tabla, "Resumen_Benford"),
                       "benford_resumen.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    recomendaciones = [
        "Verificar que el conjunto sea adecuado (no pre-condicionado; suficiente volumen; diversidad).",
        "Para dígitos con mayor desviación, revisar muestra dirigida (comprobantes, aprobaciones).",
        "Analizar por segmentos (proveedor/cliente/centro/periodo) para localizar focos.",
        "Revisar reglas de redondeo, precios fijos, topes/mínimos que expliquen patrones.",
        "Si persisten desviaciones materiales sin causa, elevar como indicio y aplicar pruebas forenses."
    ]
    resumen = [
        f"Archivo: {file_ben.name}",
        f"Observaciones válidas: {n} (de {n_total} tras filtros)",
        f"Chi²: {chi2:,.3f} – {'Cumple' if cumple else 'No cumple'} (α=0.05, gl=8)",
        f"Dígitos con mayor desviación: {', '.join(map(str,sospechosos_dig)) if sospechosos_dig else 'Ninguno'}",
        f"Umbral de desviación: {desvio_min:.1f} pp | Ignorar menores a: {min_val:,.2f}"
    ]
    sections = [("RESUMEN", [f"• {x}" for x in resumen]),
                ("DESVIACIONES POR DÍGITO", [f"• {r.Dígito}: Obs {r['Proporción Observada (%)']}% vs Exp {r['Proporción Esperada (%)']}% (Δ {r['Desviación (pp)']} pp)" for _,r in tabla.iterrows()]),
                ("RECOMENDACIONES", [f"• {x}" for x in recomendaciones]),
                ("REFERENCIA XLSX", ["• 'benford_resumen.xlsx' (tabla) y 'benford_sospechosas.xlsx' (transacciones marcadas)."])]
    st.download_button("⬇️ Descargar reporte (DOCX)",
                       docx_from_sections("Ley de Benford – Reporte de Auditoría", sections),
                       "reporte_benford.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# ============================ Navegación en PESTAÑAS GRANDES ============================
tabs = st.tabs(["💥 Montos inusuales", "🔁 Conciliación A vs. B", "📈 Ley de Benford"])
with tabs[0]:
    ui_montos_inusuales()
with tabs[1]:
    ui_conciliacion()
with tabs[2]:
    ui_benford()
