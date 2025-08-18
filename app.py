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

# ==============================
# Configuración general
# ==============================
st.set_page_config(page_title="CAAT – Auditoría Automatizada", layout="wide")
st.title("🧪 Herramienta CAAT – Auditoría Automatizada")
st.markdown("Sube archivos y ejecuta las pruebas en cada sección. Soporta **CSV/XLSX/XLS/TXT**.")

# ===== Estilos y helper UI =====
st.markdown("""
<style>
.main .block-container {max-width: 1200px; padding-top: .5rem; padding-bottom: 2rem;}
.section-card {
  border: 1px solid rgba(125,125,125,.25);
  border-radius: 14px; padding: 16px 18px; margin: 18px 0 18px 0;
  background: rgba(200,200,255,.07);
}
.section-title { font-size: 26px; font-weight: 800; margin-bottom: 6px; }
.section-desc  { font-size: 16px; color:#374151; }
.badge {
  display: inline-block; padding: 4px 10px; border-radius: 999px;
  background: #eef2ff; color: #2f3ab2; font-size: 12px; font-weight: 600; margin-left: 6px;
  border: 1px solid rgba(47,58,178,.15);
}
.big-warning { font-size: 16px; line-height: 1.35; }
[data-testid="stFileUploader"] {border-radius: 12px; border: 1px dashed rgba(125,125,125,.35); padding: 14px;}
.stButton>button { border-radius: 999px !important; padding: .55rem 1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

def section_intro(n, title, desc):
    st.markdown(f"""
<div class="section-card">
  <div class="section-title">{n} {title} <span class="badge">CSV/XLSX/XLS/TXT</span></div>
  <div class="section-desc">{desc}</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🧭 Navegación")
    st.write("2) Montos inusuales\n\n3) Conciliación A vs B\n\n4) Benford")
    st.markdown("---")
    st.markdown("### 💡 Consejos")
    st.caption("- Benford: usa una **columna de montos** (no IDs) y muestra grande de datos.\n- Conciliación: define **columna clave** y tolerancia.\n- Descargas: resultados en **XLSX** y reportes en **DOCX**.")
    st.markdown("---")
    st.caption("Versión CAAT A-2025 • Streamlit")

# ==============================
# Utilidades de lectura y helpers
# ==============================
SINONIMOS_ID = ["idfactura","id_factura","numero","número","numerofactura","numero_factura",
    "serie","serie_comprobante","clave_acceso","idtransaccion","id_transaccion","referencia","doc","documento"]
SINONIMOS_MONTO = ["total","monto","importe","valor","monto_total","total_ingresado",
    "importe_total","importe neto","subtotal+iva","total factura","totalfactura"]
SINONIMOS_FECHA = ["fecha","fecha_emision","fecha emisión","f_emision","fecha documento",
    "fecha_doc","fechadoc","fecha fact","fecha factura","emision"]

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
            try:
                return pd.read_csv(bio, sep=delim, engine="python")
            except Exception:
                pass
        bio.seek(0)
        try:
            return pd.read_csv(bio, sep=None, engine="python")
        except Exception:
            bio.seek(0)
            return pd.read_csv(bio, sep=None, engine="python", encoding="latin-1")
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

def normalize_headers(df):
    df.columns = [str(c).strip() for c in df.columns]
    return df

def col_auto(df, candidatos):
    cols_norm = {c.lower().strip(): c for c in df.columns}
    for alias in candidatos:
        if alias in cols_norm:
            return cols_norm[alias]
    for c in df.columns:
        cl = c.lower()
        if any(alias in cl for alias in candidatos):
            return c
    return None

def coerce_amount(series):
    s = series.astype(str)
    s = s.str.replace(r"\.", "", regex=True)  # remover miles con punto
    s = s.str.replace(",", ".", regex=False)  # coma -> punto
    return pd.to_numeric(s, errors="coerce")

def coerce_date(series):
    return pd.to_datetime(series, errors="coerce", dayfirst=True)

def to_xlsx_bytes(df: pd.DataFrame, sheet_name="Hoja1") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()

def docx_bytes_from_text(title: str, paragraphs: list[str]) -> bytes:
    d = Document()
    d.add_heading(title, level=1)
    for p in paragraphs:
        par = d.add_paragraph(p)
        par.style.font.size = Pt(11)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()

# ======================================================
# 2) CAAT – Detección de Montos Inusuales (mejorado)
# ======================================================
section_intro("2️⃣", "Detección de Montos Inusuales",
              "Encuentra transacciones que superan un umbral (fijo o estadístico) y genera un **reporte con recomendaciones** para el auditor.")

file_unusual = st.file_uploader("📁 Subir archivo para montos inusuales (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="unusual")

if file_unusual:
    try:
        dfm = load_any(file_unusual, widget_key="sheet_unusual")
        dfm = normalize_headers(dfm)
        st.success(f"✅ Archivo cargado. Filas: {len(dfm)}")
        with st.expander("Ver primeras filas"):
            st.dataframe(dfm.head())

        # Selección de columnas
        sugerida_monto = col_auto(dfm, SINONIMOS_MONTO) or (dfm.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
        col_monto = st.selectbox("💰 Columna de monto", dfm.columns.tolist(),
                                 index=(dfm.columns.tolist().index(sugerida_monto) if sugerida_monto in dfm.columns else 0))
        col_id = st.selectbox("🔑 Columna identificadora (ID/Número/Referencia) (opcional)", ["(ninguna)"] + dfm.columns.tolist(), index=0)

        metodo = st.radio("Método de detección", ["Umbral fijo", "Umbral estadístico (media + k·σ)"], horizontal=True)
        ejecutar = False
        if metodo.startswith("Umbral fijo"):
            umbral = st.number_input("💵 Umbral fijo ($):", min_value=0.0, value=10000.0)
            ejecutar = st.button("🔍 Ejecutar (fijo)")
        else:
            k = st.slider("🔬 k (media + k·σ)", min_value=1, max_value=5, value=2)
            ejecutar = st.button("🔍 Ejecutar (estadístico)")

        if ejecutar:
            serie_monto = dfm[col_monto]
            if serie_monto.dtype == object:
                serie_monto = coerce_amount(serie_monto)

            dfm["_MONTO_"] = pd.to_numeric(serie_monto, errors="coerce")
            base = dfm.dropna(subset=["_MONTO_"]).copy()

            if metodo.startswith("Umbral fijo"):
                limite = umbral
                criterio_txt = f"Umbral fijo = {umbral:,.2f}"
            else:
                media = base["_MONTO_"].mean()
                std = base["_MONTO_"].std(ddof=0)
                limite = media + k * std
                criterio_txt = f"Umbral estadístico = media {media:,.2f} + {k}·σ {std:,.2f} → {limite:,.2f}"

            hallazgos = base[base["_MONTO_"] > limite].copy()
            st.subheader("📊 Resultados")
            st.write(f"**Criterio aplicado:** {criterio_txt}")
            st.metric("Transacciones analizadas", len(base))
            st.metric("Montos inusuales detectados", len(hallazgos))

            if not hallazgos.empty:
                if col_id != "(ninguna)":
                    cols_show = [col_id, col_monto]
                else:
                    cols_show = [col_monto]
                cols_show = [c for c in cols_show if c in hallazgos.columns] + [c for c in hallazgos.columns if c not in cols_show][:6]
                st.dataframe(hallazgos[cols_show])

                # Descargas XLSX
                st.download_button("⬇️ Descargar hallazgos (XLSX)",
                                   to_xlsx_bytes(hallazgos, sheet_name="Montos_Inusuales"),
                                   "montos_inusuales.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                # Reporte DOCX con recomendaciones
                recomendaciones = [
                    "Validar la existencia y documentación de las transacciones detectadas (órdenes, contratos, aprobaciones).",
                    "Solicitar explicaciones a los responsables de las áreas que originaron los movimientos.",
                    "Revisar políticas de límites de aprobación y segregación de funciones.",
                    "Aplicar procedimientos sustantivos adicionales (muestreo dirigido).",
                    "Verificar que los asientos contables hayan sido revisados por un responsable distinto al preparador.",
                    "Si hay patron recurrente por proveedor/centro de costo, evaluar riesgo de fraude o error sistemático."
                ]
                resumen = [
                    f"Archivo analizado: {file_unusual.name}",
                    f"Filas válidas: {len(base)}",
                    f"Hallazgos: {len(hallazgos)}",
                    f"Criterio: {criterio_txt}",
                    f"Fecha de análisis: {datetime.now():%Y-%m-%d %H:%M}"
                ]
                doc_parrafos = ["RESUMEN:"] + [f"• {x}" for x in resumen] + ["", "RECOMENDACIONES:"] + [f"• {r}" for r in recomendaciones]
                st.download_button("⬇️ Descargar reporte con recomendaciones (DOCX)",
                                   docx_bytes_from_text("Montos Inusuales – Reporte de Auditoría", doc_parrafos),
                                   "reporte_montos_inusuales.docx",
                                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            else:
                st.success("✅ No se encontraron montos inusuales con el criterio seleccionado.")

    except Exception as e:
        st.error(f"❌ Error: {e}")

# ======================================================
# 3) CAAT – Conciliación de Reportes (A vs. B) + recomendaciones
# ======================================================
section_intro("3️⃣", "Conciliación de Reportes (A vs. B)",
              "Compara dos archivos (p. ej., facturación y contabilidad) y genera un **informe para el auditor** con recomendaciones.")

colA, colB = st.columns(2)
with colA:
    file_A = st.file_uploader("📁 Archivo A (p.ej., Facturación)", type=["csv","xlsx","xls","txt"], key="conc_a")
with colB:
    file_B = st.file_uploader("📁 Archivo B (p.ej., Contabilidad)", type=["csv","xlsx","xls","txt"], key="conc_b")

if file_A and file_B:
    try:
        A = load_any(file_A, widget_key="sheet_A"); A = normalize_headers(A)
        B = load_any(file_B, widget_key="sheet_B"); B = normalize_headers(B)

        st.success(f"✅ Cargados A={len(A)} filas, B={len(B)} filas")
        with st.expander("Ver primeras filas"):
            st.write("A (preview)"); st.dataframe(A.head())
            st.write("B (preview)"); st.dataframe(B.head())

        # Auto sugerencias
        comunes = [c for c in A.columns if c in set(B.columns)]
        if not comunes:
            st.error("❌ No hay columnas en común entre A y B.")
            st.stop()

        def col_auto(df, candidatos):
            cols_norm = {c.lower().strip(): c for c in df.columns}
            for alias in candidatos:
                if alias in cols_norm:
                    return cols_norm[alias]
            for c in df.columns:
                if any(alias in c.lower() for alias in candidatos):
                    return c
            return None

        clave_sug = col_auto(A, SINONIMOS_ID) if col_auto(A, SINONIMOS_ID) in comunes else comunes[0]
        montoA_sug = col_auto(A, SINONIMOS_MONTO) or (A.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
        montoB_sug = col_auto(B, SINONIMOS_MONTO) or (B.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
        fechaA_sug = col_auto(A, SINONIMOS_FECHA)
        fechaB_sug = col_auto(B, SINONIMOS_FECHA)

        st.subheader("🔧 Configuración")
        clave = st.selectbox("🔑 Columna clave común", comunes, index=comunes.index(clave_sug) if clave_sug in comunes else 0)
        monto_A = st.selectbox("💰 Columna de monto en A", A.columns.tolist(), index=(A.columns.tolist().index(montoA_sug) if (montoA_sug in A.columns) else 0))
        monto_B = st.selectbox("💰 Columna de monto en B", B.columns.tolist(), index=(B.columns.tolist().index(montoB_sug) if (montoB_sug in B.columns) else 0))
        fecha_A_opt = st.selectbox("📅 Columna de fecha en A (opcional)", ["(ninguna)"] + A.columns.tolist(),
                                   index=(["(ninguna)"] + A.columns.tolist()).index(fechaA_sug) if (fechaA_sug in A.columns) else 0)
        fecha_B_opt = st.selectbox("📅 Columna de fecha en B (opcional)", ["(ninguna)"] + B.columns.tolist(),
                                   index=(["(ninguna)"] + B.columns.tolist()).index(fechaB_sug) if (fechaB_sug in B.columns) else 0)
        tolerancia = st.number_input("🎯 Tolerancia para diferencias de monto (valor absoluto)", min_value=0.0, value=0.0)

        if st.button("🔍 Ejecutar conciliación"):
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
            coinc["_diff_monto_abs"] = (coinc["_MONTO__A"] - coinc["_MONTO__B"]).abs()
            diff_monto = coinc[coinc["_diff_monto_abs"] > tolerancia].copy()

            diff_fecha = pd.DataFrame()
            if "_FECHA__A" in coinc.columns and "_FECHA__B" in coinc.columns:
                diff_fecha = coinc[(~coinc["_FECHA__A"].isna()) & (~coinc["_FECHA__B"].isna()) & (coinc["_FECHA__A"] != coinc["_FECHA__B"])][["_CLAVE_","_FECHA__A","_FECHA__B"]].copy()

            c1, c2, c3 = st.columns(3)
            c1.metric("Solo en A", len(solo_A)); c2.metric("Solo en B", len(solo_B)); c3.metric("Dif. de monto", len(diff_monto))

            with st.expander("🟦 Solo en A"):
                st.dataframe(solo_A)
                st.download_button("⬇️ Descargar (XLSX)", to_xlsx_bytes(solo_A, "Solo_en_A"), "solo_en_a.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            with st.expander("🟧 Solo en B"):
                st.dataframe(solo_B)
                st.download_button("⬇️ Descargar (XLSX)", to_xlsx_bytes(solo_B, "Solo_en_B"), "solo_en_b.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            with st.expander("🟥 Coincidentes con diferencias de monto"):
                st.dataframe(diff_monto[["_CLAVE_","_MONTO__A","_MONTO__B","_diff_monto_abs"]])
                st.download_button("⬇️ Descargar (XLSX)", to_xlsx_bytes(diff_monto, "Diferencias_Monto"), "diferencias_monto.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            if not diff_fecha.empty:
                with st.expander("🟨 Coincidentes con diferencias de fecha"):
                    st.dataframe(diff_fecha)
                    st.download_button("⬇️ Descargar (XLSX)", to_xlsx_bytes(diff_fecha, "Diferencias_Fecha"), "diferencias_fecha.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            # Reporte DOCX con recomendaciones
            recomendaciones = [
                "Investigar registros presentes en un sistema pero ausentes en el otro (Solo en A / Solo en B).",
                "Revisar integraciones/interfaz de datos y bitácoras de carga por fechas de corte.",
                "Para diferencias de monto, verificar tipo de cambio, descuentos, impuestos y redondeos.",
                "Validar que no existan asientos manuales fuera del proceso regular.",
                "Acordar con Contabilidad/facturación un procedimiento de conciliación periódico.",
                "Aplicar muestreo dirigido sobre discrepancias de mayor materialidad."
            ]
            resumen = [
                f"Archivo A: {file_A.name} | Archivo B: {file_B.name}",
                f"Solo en A: {len(solo_A)} | Solo en B: {len(solo_B)}",
                f"Diferencias de monto: {len(diff_monto)} | Diferencias de fecha: {len(diff_fecha)}",
                f"Tolerancia aplicada: {tolerancia:,.2f}",
                f"Fecha de análisis: {datetime.now():%Y-%m-%d %H:%M}"
            ]
            doc_parrafos = ["RESUMEN:"] + [f"• {x}" for x in resumen] + ["", "RECOMENDACIONES:"] + [f"• {r}" for r in recomendaciones]
            st.download_button("⬇️ Descargar reporte con recomendaciones (DOCX)",
                               docx_bytes_from_text("Conciliación A vs. B – Reporte de Auditoría", doc_parrafos),
                               "reporte_conciliacion.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    except Exception as e:
        st.error(f"❌ Error en conciliación: {e}")

# ======================================================
# 4) CAAT – Ley de Benford (con lista de “sospechosos” + alerta grande)
# ======================================================
section_intro("4️⃣", "Ley de Benford aplicada a transacciones",
              "Contrasta el primer dígito de los montos con la distribución esperada por Benford, **lista transacciones sospechosas** y emite un **reporte**.")

st.markdown("""
<div class="section-card">
<div class="big-warning">
<strong>⚠️ Advertencia importante:</strong> La Ley de Benford es apropiada para conjuntos grandes de datos
de naturaleza espontánea (no pre-condicionados), como ventas, gastos o pagos variados.
No debe aplicarse a series acotadas, precios fijos, datos con mínimos/máximos impuestos, folios,
o montos predefinidos; en esos casos, los resultados pueden ser engañosos.
</div>
</div>
""", unsafe_allow_html=True)

file_benford = st.file_uploader("📁 Subir archivo (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="benford")

def first_digit_series(series: pd.Series) -> pd.Series:
    if series.dtype == object: x = coerce_amount(series)
    else: x = pd.to_numeric(series, errors="coerce")
    x = x.abs(); x = x[x > 0].dropna()
    s = x.apply(lambda v: f"{v:.15g}")
    s = s.str.replace(".", "", regex=False).str.lstrip("0")
    first = s.str[0].dropna()
    first = first[first.str.contains(r"[1-9]", regex=True)]
    return first.astype(int)

def benford_expected() -> pd.Series:
    d = np.arange(1, 10); p = np.log10(1 + 1/d)
    return pd.Series(p, index=d)

if file_benford:
    try:
        dfb = load_any(file_benford, widget_key="sheet_benford"); dfb = normalize_headers(dfb)
        st.success(f"✅ Archivo cargado. Filas: {len(dfb)}")
        with st.expander("Ver primeras filas"): st.dataframe(dfb.head())

        # Columnas candidatas a monto (numéricas o texto convertible en ≥30%)
        def is_amount_candidate(s: pd.Series) -> bool:
            if pd.api.types.is_numeric_dtype(s): return True
            if s.dtype == object:
                conv = coerce_amount(s); return conv.notna().mean() >= 0.30
            return False
        candidatas = [c for c in dfb.columns if is_amount_candidate(dfb[c])]
        if not candidatas:
            st.error("No se hallaron columnas de monto válidas. Debe existir una columna numérica o convertible.")
            st.stop()

        sugerida_monto_b = col_auto(dfb[candidatas], SINONIMOS_MONTO) or candidatas[0]
        col_monto_b = st.selectbox("💰 Columna de monto", candidatas, index=(candidatas.index(sugerida_monto_b) if sugerida_monto_b in candidatas else 0))
        min_val = st.number_input("🔻 Ignorar montos menores a (opcional)", min_value=0.0, value=0.0)
        min_count_alert = st.number_input("🔔 Mínimo sugerido de observaciones", min_value=0, value=100)
        desvio_min = st.number_input("🎚 Umbral de desviación por dígito (puntos porcentuales)", min_value=0.0, value=2.0, step=0.5,
                                     help="Se marcarán como 'sospechosos' los dígitos cuya proporción Observada - Esperada ≥ este umbral.")

        if st.button("🔍 Ejecutar Benford"):
            serie = dfb[col_monto_b]; 
            if serie.dtype == object:
                conv = coerce_amount(serie)
                if conv.notna().mean() < 0.30:
                    st.error("La columna seleccionada no tiene suficientes valores convertibles a número (≥30%).")
                    st.stop()
                serie = conv
            base = pd.to_numeric(serie, errors="coerce").dropna()
            if min_val > 0: base = base[base.abs() >= min_val]

            fd = first_digit_series(base); n = len(fd)
            if n == 0:
                st.error("❌ No hay suficientes datos numéricos válidos tras la limpieza/filtros.")
            else:
                obs_counts = fd.value_counts().reindex(range(1,10), fill_value=0).sort_index()
                obs_prop   = obs_counts / n
                exp_prop   = benford_expected()
                exp_counts = (exp_prop * n)
                chi2 = (((obs_counts - exp_counts) ** 2) / exp_counts.replace(0, np.nan)).sum()
                chi2_crit = 15.507  # α=0.05, gl=8
                cumple = chi2 <= chi2_crit

                st.subheader("📊 Resumen Benford")
                c1, c2, c3 = st.columns(3)
                c1.metric("Observaciones válidas", n); c2.metric("Chi-cuadrado", f"{chi2:,.3f}"); c3.metric("¿Cumple (α=0.05)?", "Sí ✅" if cumple else "No ⚠️")
                if n < min_count_alert: st.info(f"ℹ️ Nota: {n} observaciones; sugerido ≥ {min_count_alert} para mayor robustez.")

                # Tabla observados vs esperados
                tabla = pd.DataFrame({
                    "Dígito": list(range(1,10)),
                    "Frecuencia Observada": obs_counts.values,
                    "Proporción Observada (%)": (obs_prop.values * 100).round(2),
                    "Proporción Esperada (%)": (exp_prop.values * 100).round(2),
                    "Desviación (pp)": ((obs_prop - exp_prop).values * 100).round(2)
                })
                st.dataframe(tabla)

                # Gráfico barras
                fig, ax = plt.subplots()
                idx = np.arange(1, 10)
                ax.bar(idx - 0.15, obs_prop.values, width=0.3, label="Observado")
                ax.bar(idx + 0.15, exp_prop.values, width=0.3, label="Esperado (Benford)")
                ax.set_xticks(idx); ax.set_xlabel("Primer dígito"); ax.set_ylabel("Proporción")
                ax.set_title("Ley de Benford: Observado vs. Esperado"); ax.legend()
                st.pyplot(fig)

                # Dígitos sospechosos y transacciones asociadas
                sospechosos = tabla.loc[tabla["Desviación (pp)"] >= desvio_min, "Dígito"].tolist()
                st.write(f"**Dígitos marcados como 'sospechosos' (desviación ≥ {desvio_min:.1f} pp):** {sospechosos if sospechosos else 'Ninguno'}")

                df_base = pd.DataFrame({"_monto_": base})
                df_base["_1er_dig"] = first_digit_series(base.values)
                sospechosas = df_base[df_base["_1er_dig"].isin(sospechosos)].copy()

                with st.expander("🔎 Ver transacciones sospechosas por dígito"):
                    if not sospechosas.empty:
                        st.dataframe(sospechosas.head(1000))  # muestra razonable
                        st.download_button("⬇️ Descargar sospechosas (XLSX)",
                                           to_xlsx_bytes(sospechosas, "Sospechosas_Benford"),
                                           "benford_sospechosas.xlsx",
                                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    else:
                        st.info("No se encontraron transacciones sospechosas con el umbral seleccionado.")

                # Descarga XLSX del resumen
                st.download_button("⬇️ Descargar tabla resumen (XLSX)",
                                   to_xlsx_bytes(tabla, "Resumen_Benford"),
                                   "benford_resumen.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"❌ Error en Benford: {e}")
