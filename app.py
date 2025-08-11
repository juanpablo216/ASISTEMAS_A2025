# app.py
import streamlit as st
import pandas as pd
import numpy as np
import io, csv
import matplotlib.pyplot as plt

# ==============================
# Configuración general
# ==============================
st.set_page_config(page_title="CAAT – Auditoría Automatizada", layout="wide")
st.title("🧪 Herramienta CAAT – Auditoría Automatizada")
st.markdown("Sube archivos y ejecuta las pruebas en cada sección. Soporta **CSV/XLSX/XLS/TXT**.")

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
    s = s.str.replace(r"\.", "", regex=True)  # remover miles con punto
    s = s.str.replace(",", ".", regex=False)  # coma -> punto
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
            st.error("❌ No hay columnas en común entre A y B.")
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
                mostrar = ["._CLAVE_".replace(".", ""),"_MONTO__A","_MONTO__B","_diff_monto_abs"]
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

# ======================================================
# 4) CAAT – Ley de Benford aplicada a transacciones
# ======================================================
st.header("4️⃣ Ley de Benford aplicada a transacciones")
file_benford = st.file_uploader("📁 Subir archivo (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="benford")

def first_digit_series(series: pd.Series) -> pd.Series:
    # Asegura numérico robusto
    if series.dtype == object:
        x = coerce_amount(series)
    else:
        x = pd.to_numeric(series, errors="coerce")
    x = x.abs()
    x = x[x > 0].dropna()
    s = x.apply(lambda v: f"{v:.15g}")
    s = s.str.replace(".", "", regex=False).str.lstrip("0")
    first = s.str[0].dropna()
    first = first[first.str.contains(r"[1-9]", regex=True)]
    return first.astype(int)

def benford_expected() -> pd.Series:
    d = np.arange(1, 10)
    p = np.log10(1 + 1/d)
    return pd.Series(p, index=d)

if file_benford:
    try:
        dfb = load_any(file_benford, widget_key="sheet_benford")
        dfb = normalize_headers(dfb)
        st.success(f"✅ Archivo cargado. Filas: {len(dfb)}")
        with st.expander("Ver primeras filas"):
            st.dataframe(dfb.head())

        sugerida_monto_b = col_auto(dfb, SINONIMOS_MONTO) or (dfb.select_dtypes(include="number").columns.tolist()[:1] or [None])[0]
        col_monto_b = st.selectbox("💰 Columna de monto", dfb.columns.tolist(),
                                   index=(dfb.columns.tolist().index(sugerida_monto_b) if sugerida_monto_b in dfb.columns else 0))
        min_val = st.number_input("🔻 Ignorar montos menores a (opcional)", min_value=0.0, value=0.0)
        min_count_alert = st.number_input("🔔 Mínimo sugerido de observaciones", min_value=0, value=100)

        if st.button("🔍 Ejecutar Benford"):
            serie = dfb[col_monto_b]
            if serie.dtype == object:
                serie = coerce_amount(serie)
            base = pd.to_numeric(serie, errors="coerce").dropna()
            if min_val > 0:
                base = base[base.abs() >= min_val]

            fd = first_digit_series(base)
            n = len(fd)
            if n == 0:
                st.error("❌ No hay suficientes datos numéricos válidos tras la limpieza/filtros.")
            else:
                obs_counts = fd.value_counts().reindex(range(1,10), fill_value=0).sort_index()
                obs_prop = obs_counts / n
                exp_prop = benford_expected()
                exp_counts = (exp_prop * n)
                chi2 = (((obs_counts - exp_counts) ** 2) / exp_counts.replace(0, np.nan)).sum()
                chi2_crit = 15.507  # α=0.05, gl=8
                cumple = chi2 <= chi2_crit

                st.subheader("📊 Resumen Benford")
                c1, c2, c3 = st.columns(3)
                c1.metric("Observaciones válidas", n)
                c2.metric("Chi-cuadrado", f"{chi2:,.3f}")
                c3.metric("¿Cumple (α=0.05)?", "Sí ✅" if cumple else "No ⚠️")
                if n < min_count_alert:
                    st.info(f"ℹ️ Nota: {n} observaciones; sugerido ≥ {min_count_alert} para mayor robustez.")

                tabla = pd.DataFrame({
                    "Dígito": list(range(1,9+1)),
                    "Frecuencia Observada": obs_counts.values,
                    "Proporción Observada": (obs_prop.values * 100).round(2),
                    "Proporción Esperada (Benford %)": (exp_prop.values * 100).round(2),
                    "Conteo Esperado": exp_counts.round(2).values
                })
                st.dataframe(tabla)

                fig, ax = plt.subplots()
                idx = np.arange(1, 10)
                ax.bar(idx - 0.15, obs_prop.values, width=0.3, label="Observado")
                ax.bar(idx + 0.15, exp_prop.values, width=0.3, label="Esperado (Benford)")
                ax.set_xticks(idx)
                ax.set_xlabel("Primer dígito")
                ax.set_ylabel("Proporción")
                ax.set_title("Ley de Benford: Observado vs. Esperado")
                ax.legend()
                st.pyplot(fig)

                st.download_button("⬇️ Descargar tabla Benford (CSV)", to_csv_bytes(tabla), "benford_resultados.csv", "text/csv")

    except Exception as e:
        st.error(f"❌ Error en Benford: {e}")

# ======================================================
# 5) CAAT – Análisis de Concentración de Clientes/Proveedores
# ======================================================
st.header("5️⃣ Análisis de Concentración de Clientes o Proveedores")
file_conc = st.file_uploader("📁 Subir archivo de ventas o compras (CSV/XLSX/XLS/TXT)", type=["csv","xlsx","xls","txt"], key="conc_file")

if file_conc:
    try:
        dfc = load_any(file_conc, widget_key="sheet_conc")
        dfc = normalize_headers(dfc)
        st.success(f"✅ Archivo cargado. Filas: {len(dfc)}")
        with st.expander("Ver primeras filas"):
            st.dataframe(dfc.head())

        entidad_col = st.selectbox("🏷️ Columna de entidad (Cliente/Proveedor)", dfc.columns.tolist())

        numeric_cols = dfc.select_dtypes(include='number').columns.tolist()
        col_monto_default = numeric_cols[0] if numeric_cols else dfc.columns[0]
        monto_col = st.selectbox("💰 Columna de monto", dfc.columns.tolist(),
                                 index=(dfc.columns.tolist().index(col_monto_default) if col_monto_default in dfc.columns else 0))

        sentido = st.radio("Tipo de análisis", ["Clientes (ventas)", "Proveedores (compras)"], horizontal=True)
        umbral_flag = st.number_input("🎯 Umbral de concentración para marcar (ej. 40%)", min_value=0.0, max_value=100.0, value=40.0)
        top_n = st.slider("👑 Mostrar Top N en gráfico de barras", min_value=3, max_value=20, value=10)

        if st.button("🔍 Calcular concentración"):
            serie_monto = dfc[monto_col]
            if serie_monto.dtype == object:
                serie_monto = coerce_amount(serie_monto)
            dfc["_MONTO_"] = pd.to_numeric(serie_monto, errors="coerce")

            base = dfc.dropna(subset=[entidad_col, "_MONTO_"]).copy()
            base[entidad_col] = base[entidad_col].astype(str).str.strip()

            ag = (base.groupby(entidad_col, dropna=True)
                        .agg(Total=("_MONTO_", "sum"),
                             Transacciones=("_MONTO_", "count"))
                        .reset_index())

            ag = ag.sort_values("Total", ascending=False)
            total_general = ag["Total"].sum()
            ag["Participacion_%"] = (ag["Total"] / total_general * 100).round(2)
            ag["Acumulado_%"] = ag["Participacion_%"].cumsum().round(2)

            def cum_share(k):
                return ag["Participacion_%"].iloc[:k].sum() if len(ag) >= k else ag["Participacion_%"].sum()

            top1 = cum_share(1)
            top3 = cum_share(3)
            top5 = cum_share(5)
            top10 = cum_share(10)

            shares = ag["Participacion_%"] / 100.0
            hhi = int((shares.pow(2).sum() * 10000).round(0))

            st.subheader("📊 Indicadores de concentración")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Top 1", f"{top1:.2f}%")
            c2.metric("Top 3", f"{top3:.2f}%")
            c3.metric("Top 5", f"{top5:.2f}%")
            c4.metric("Top 10", f"{top10:.2f}%")
            c5.metric("HHI", f"{hhi}")

            st.subheader("📄 Tabla de concentración por entidad")
            st.dataframe(ag)

            marcados = ag[ag["Participacion_%"] >= umbral_flag]
            if not marcados.empty:
                st.warning(f"⚠️ Entidades con participación ≥ {umbral_flag:.0f}%: {len(marcados)}")
                st.dataframe(marcados)

            # Gráfico 1: Top N barras
            fig1, ax1 = plt.subplots()
            top_plot = ag.head(top_n)
            ax1.bar(top_plot[entidad_col].astype(str), top_plot["Participacion_%"])
            ax1.set_title(f"Top {top_n} participación (%) – {sentido}")
            ax1.set_ylabel("Participación (%)")
            ax1.set_xticklabels(top_plot[entidad_col].astype(str), rotation=45, ha="right")
            st.pyplot(fig1)

            # Gráfico 2: Curva de Lorenz
            shares_sorted = np.sort(shares.values)
            lorenz = np.cumsum(shares_sorted)
            lorenz = np.insert(lorenz, 0, 0)
            x = np.linspace(0.0, 1.0, len(lorenz))
            fig2, ax2 = plt.subplots()
            ax2.plot(x, lorenz, label="Curva de Lorenz")
            ax2.plot([0,1], [0,1], linestyle="--", label="Igualdad perfecta")
            ax2.set_title(f"Curva de Lorenz – {sentido}")
            ax2.set_xlabel("Proporción de entidades")
            ax2.set_ylabel("Proporción acumulada de monto")
            ax2.legend()
            st.pyplot(fig2)

            st.download_button("⬇️ Descargar tabla (CSV)", to_csv_bytes(ag), "concentracion_entidades.csv", "text/csv")
            if not marcados.empty:
                st.download_button("⬇️ Descargar marcados por umbral (CSV)", to_csv_bytes(marcados),
                                   "entidades_marcadas_umbral.csv", "text/csv")

    except Exception as e:
        st.error(f"❌ Error en análisis de concentración: {e}")
