import streamlit as st
import pandas as pd
import io, csv

# ==============================
# Configuración general
# ==============================
st.set_page_config(page_title="CAAT – Auditoría Automatizada", layout="wide")
st.title("🧪 Herramienta CAAT – Auditoría Automatizada")
st.markdown("Sube archivos y ejecuta pruebas independientes en cada sección.")

# ==============================
# Utilidades comunes y robustas
# ==============================
SINONIMOS_ID = [
    "idfactura","id_factura","numero","número","numerofactura","numero_factura",
    "serie","serie_comprobante","clave_acceso","idtransaccion","id_transaccion",
    "referencia","doc","documento"
]
SINONIMOS_MONTO = [
    "total","monto","importe","valor","monto_total","total_ingresado",
    "importe_total","importe neto","subtotal+iva","total factura","totalfactura"
]
SINONIMOS_FECHA = [
    "fecha","fecha_emision","fecha emisión","f_emision","fecha documento",
    "fecha_doc","fechadoc","fecha fact","fecha factura","emision"
]

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
    # coincidencias parciales
    for c in df.columns:
        cl = c.lower()
        if any(alias in cl for alias in candidatos):
            return c
    return None

def coerce_amount(series):
    # Convierte '1.234,56' -> 1234.56 y también '1,234.56' -> 1234.56
    s = series.astype(str)
    # Primero quita separadores de miles
    s = s.str.replace(r"\.", "", regex=True)
    # Luego coma por punto
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")

def coerce_date(series):
    return pd.to_datetime(series, errors="coerce", dayfirst=True)

def to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")

# ======================================================
# 1) CAAT – Detección de Facturas Duplicadas (multi-formato)
# ======================================================
st.header("1️⃣ Detección de Facturas Duplicadas")
file_dup = st.file_uploader("📁 Subir archivo para duplicados (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="dup")

def detectar_duplicados(df):
    # combinaciones típicas en distintos orígenes
    combinaciones = [
        ['Número', 'R.U.C.', 'Total', 'Fecha'],
        ['SERIE_COMPROBANTE', 'RUC_EMISOR', 'IMPORTE_TOTAL', 'FECHA_EMISION'],
        ['NumeroFactura', 'IDProveedor', 'MontoTotal', 'FechaEmision']
    ]
    for campos in combinaciones:
        if all(col in df.columns for col in campos):
            return df[df.duplicated(subset=campos, keep=False)], campos
    return pd.DataFrame(), []

if file_dup:
    try:
        df = load_any(file_dup, widget_key="sheet_dup")
        df = normalize_headers(df)
        st.success(f"✅ Archivo cargado. Filas: {len(df)}")
        with st.expander("Ver primeras filas"):
            st.dataframe(df.head())

        duplicados, campos = detectar_duplicados(df)
        if not duplicados.empty:
            st.warning(f"⚠️ Se encontraron {len(duplicados)} duplicados basados en: {', '.join(campos)}")
            st.dataframe(duplicados)
            st.download_button("⬇️ Descargar duplicados (CSV)", to_csv_bytes(duplicados), "duplicados.csv", "text/csv")
        else:
            st.success("✅ No se encontraron facturas duplicadas o no se detectaron columnas comunes.")
    except Exception as e:
        st.error(f"❌ Error: {e}")

# ======================================================
# 2) CAAT – Detección de Montos Inusuales (fijo o estadístico)
# ======================================================
st.header("2️⃣ Detección de Montos Inusuales")
file_unusual = st.file_uploader("📁 Subir archivo para montos inusuales (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="unusual")

if file_unusual:
    try:
        dfm = load_any(file_unusual, widget_key="sheet_unusual")
        dfm = normalize_headers(dfm)
        st.success(f"✅ Archivo cargado. Filas: {len(dfm)}")
        with st.expander("Ver primeras filas"):
            st.dataframe(dfm.head())

        # Sugerir columna de monto
        sugerida_monto = col_auto(dfm, SINONIMOS_MONTO) or (dfm.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
        col_monto = st.selectbox("💰 Columna de monto", dfm.columns.tolist(),
                                 index=(dfm.columns.tolist().index(sugerida_monto) if sugerida_monto in dfm.columns else 0))

        metodo = st.radio("Método de detección", ["Umbral fijo", "Umbral estadístico"], horizontal=True)
        ejecutar = False
        if metodo == "Umbral fijo":
            umbral = st.number_input("💵 Umbral fijo ($):", min_value=0.0, value=10000.0)
            ejecutar = st.button("🔍 Ejecutar (fijo)")
        else:
            k = st.slider("🔬 Coeficiente σ (media + k*desv)", min_value=1, max_value=5, value=2)
            ejecutar = st.button("🔍 Ejecutar (estadístico)")

        if ejecutar:
            serie_monto = dfm[col_monto]
            if serie_monto.dtype == object:
                serie_monto = coerce_amount(serie_monto)

            dfm["_MONTO_"] = pd.to_numeric(serie_monto, errors="coerce")
            base = dfm.dropna(subset=["_MONTO_"]).copy()

            if metodo == "Umbral fijo":
                hallazgos = base[base["_MONTO_"] > umbral]
                umbral_txt = f"{umbral:,.2f}"
            else:
                media = base["_MONTO_"].mean()
                std = base["_MONTO_"].std()
                limite = media + k * std
                hallazgos = base[base["_MONTO_"] > limite]
                umbral_txt = f"{limite:,.2f} (media {media:,.2f} + {k}σ {std:,.2f})"

            if not hallazgos.empty:
                st.warning(f"⚠️ {len(hallazgos)} montos inusuales sobre el umbral: {umbral_txt}")
                st.dataframe(hallazgos)
                st.download_button("⬇️ Descargar resultados (CSV)", to_csv_bytes(hallazgos), "montos_inusuales.csv", "text/csv")
            else:
                st.success("✅ No se encontraron montos inusuales.")
    except Exception as e:
        st.error(f"❌ Error: {e}")

# ======================================================
# 3) CAAT – Conciliación de Reportes (A vs B, robusto)
# ======================================================
st.header("3️⃣ Conciliación de Reportes (A vs. B)")

colA, colB = st.columns(2)
with colA:
    file_A = st.file_uploader("📁 Archivo A (p.ej., Facturación)", type=["csv","xlsx","xls","txt"], key="conc_a")
with colB:
    file_B = st.file_uploader("📁 Archivo B (p.ej., Contabilidad)", type=["csv","xlsx","xls","txt"], key="conc_b")

if file_A and file_B:
    try:
        A = load_any(file_A, widget_key="sheet_A")
        B = load_any(file_B, widget_key="sheet_B")
        A = normalize_headers(A)
        B = normalize_headers(B)

        st.success(f"✅ Cargados A={len(A)} filas, B={len(B)} filas")
        with st.expander("Ver primeras filas"):
            st.write("A (preview)"); st.dataframe(A.head())
            st.write("B (preview)"); st.dataframe(B.head())

        # Auto-sugerencias
        clave_sug = None
        id_A = col_auto(A, SINONIMOS_ID)
        id_B = col_auto(B, SINONIMOS_ID)
        if id_A and id_B and id_A in B.columns:
            clave_sug = id_A
        else:
            inter_cols = [c for c in A.columns if c in set(B.columns)]
            if inter_cols:
                clave_sug = inter_cols[0]

        montoA_sug = col_auto(A, SINONIMOS_MONTO) or (A.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
        montoB_sug = col_auto(B, SINONIMOS_MONTO) or (B.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
        fechaA_sug = col_auto(A, SINONIMOS_FECHA)
        fechaB_sug = col_auto(B, SINONIMOS_FECHA)

        st.subheader("🔧 Configuración")
        comunes = [c for c in A.columns if c in set(B.columns)]
        if not comunes:
            st.error("❌ No hay columnas en común entre A y B. Selecciona archivos con al menos una columna coincidente.")
            st.stop()

        clave = st.selectbox("🔑 Columna clave común", comunes,
                             index=(comunes.index(clave_sug) if (clave_sug in comunes) else 0))
        monto_A = st.selectbox("💰 Columna de monto en A", A.columns.tolist(),
                               index=(A.columns.tolist().index(montoA_sug) if (montoA_sug in A.columns) else 0))
        monto_B = st.selectbox("💰 Columna de monto en B", B.columns.tolist(),
                               index=(B.columns.tolist().index(montoB_sug) if (montoB_sug in B.columns) else 0))
        fecha_A_opt = st.selectbox("📅 Columna de fecha en A (opcional)", ["(ninguna)"] + A.columns.tolist(),
                                   index=(["(ninguna)"] + A.columns.tolist()).index(fechaA_sug) if (fechaA_sug in (A.columns if A is not None else [])) else 0)
        fecha_B_opt = st.selectbox("📅 Columna de fecha en B (opcional)", ["(ninguna)"] + B.columns.tolist(),
                                   index=(["(ninguna)"] + B.columns.tolist()).index(fechaB_sug) if (fechaB_sug in (B.columns if B is not None else [])) else 0)

        tolerancia = st.number_input("🎯 Tolerancia para diferencias de monto (valor absoluto)", min_value=0.0, value=0.0)

        if st.button("🔍 Ejecutar conciliación"):
            # Normalización clave:
            A["_CLAVE_"] = A[clave].astype(str).str.strip().str.upper()
            B["_CLAVE_"] = B[clave].astype(str).str.strip().str.upper()

            # Normalización montos:
            A["_MONTO_"] = coerce_amount(A[monto_A]) if A[monto_A].dtype == object else pd.to_numeric(A[monto_A], errors="coerce")
            B["_MONTO_"] = coerce_amount(B[monto_B]) if B[monto_B].dtype == object else pd.to_numeric(B[monto_B], errors="coerce")

            # Fechas opcionales:
            if fecha_A_opt != "(ninguna)":
                A["_FECHA_"] = coerce_date(A[fecha_A_opt])
            if fecha_B_opt != "(ninguna)":
                B["_FECHA_"] = coerce_date(B[fecha_B_opt])

            merged = A.merge(B, on="_CLAVE_", how="outer", suffixes=("_A","_B"), indicator=True)

            solo_A = merged[merged["_merge"]=="left_only"].copy()
            solo_B = merged[merged["_merge"]=="right_only"].copy()
            coinc = merged[merged["_merge"]=="both"].copy()

            # Diferencias de monto
            coinc["_diff_monto_abs"] = (coinc["_MONTO__A"] - coinc["_MONTO__B"]).abs()
            diff_monto = coinc[coinc["_diff_monto_abs"] > tolerancia].copy()

            # Diferencias de fecha (si existen)
            diff_fecha = pd.DataFrame()
            if "_FECHA__A" in coinc.columns and "_FECHA__B" in coinc.columns:
                diff_fecha = coinc[
                    (~coinc["_FECHA__A"].isna()) & (~coinc["_FECHA__B"].isna()) & (coinc["_FECHA__A"] != coinc["_FECHA__B"])
                ][["_CLAVE_","_FECHA__A","_FECHA__B"]].copy()

            # KPIs
            c1, c2, c3 = st.columns(3)
            c1.metric("Solo en A", len(solo_A))
            c2.metric("Solo en B", len(solo_B))
            c3.metric("Dif. de monto", len(diff_monto))

            with st.expander("🟦 Solo en A"):
                st.dataframe(solo_A)
                st.download_button("⬇️ Descargar Solo en A (CSV)", to_csv_bytes(solo_A), "solo_en_A.csv", "text/csv")

            with st.expander("🟧 Solo en B"):
                st.dataframe(solo_B)
                st.download_button("⬇️ Descargar Solo en B (CSV)", to_csv_bytes(solo_B), "solo_en_B.csv", "text/csv")

            with st.expander("🟥 Coincidentes con diferencias de monto"):
                mostrar = ["_CLAVE_","_MONTO__A","_MONTO__B","_diff_monto_abs"]
                if "_FECHA__A" in diff_monto.columns: mostrar.append("_FECHA__A")
                if "_FECHA__B" in diff_monto.columns: mostrar.append("_FECHA__B")
                st.dataframe(diff_monto[mostrar])
                st.download_button("⬇️ Descargar Diferencias de Monto (CSV)", to_csv_bytes(diff_monto), "diferencias_monto.csv", "text/csv")

            if not diff_fecha.empty:
                with st.expander("🟨 Coincidentes con diferencias de fecha"):
                    st.dataframe(diff_fecha)
                    st.download_button("⬇️ Descargar Diferencias de Fecha (CSV)", to_csv_bytes(diff_fecha), "diferencias_fecha.csv", "text/csv")

    except Exception as e:
        st.error(f"❌ Error en conciliación: {e}")
