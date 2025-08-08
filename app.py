import streamlit as st
import pandas as pd

st.set_page_config(page_title="CAAT - Herramienta de Auditoría", layout="wide")

st.title("🧪 Herramienta CAAT - Auditoría Automatizada con Múltiples Pruebas")

st.markdown("""
Esta herramienta permite ejecutar diferentes pruebas de auditoría sobre archivos de datos cargados individualmente.
- 📁 Carga un archivo por cada prueba.
- 🧪 Las pruebas están separadas para mayor flexibilidad.
""")

# -----------------------------
# 🔍 PRUEBA 1: FACTURAS DUPLICADAS
# -----------------------------
st.header("1️⃣ Detección de Facturas Duplicadas")
archivo_duplicados = st.file_uploader("📁 Subir archivo para detectar facturas duplicadas", type=["csv", "xlsx", "xls", "txt"], key="duplicados")

def detectar_duplicados(df):
    combinaciones = [
        ['Número', 'R.U.C.', 'Total', 'Fecha'],
        ['SERIE_COMPROBANTE', 'RUC_EMISOR', 'IMPORTE_TOTAL', 'FECHA_EMISION'],
        ['NumeroFactura', 'IDProveedor', 'MontoTotal', 'FechaEmision']
    ]
    for campos in combinaciones:
        if all(col in df.columns for col in campos):
            duplicados = df[df.duplicated(subset=campos, keep=False)]
            return duplicados, campos
    return None, []

if archivo_duplicados:
    try:
        nombre = archivo_duplicados.name.lower()
        if nombre.endswith(".csv"):
            df = pd.read_csv(archivo_duplicados)
        elif nombre.endswith((".xlsx", ".xls")):
            df = pd.read_excel(archivo_duplicados)
        elif nombre.endswith(".txt"):
            df = pd.read_csv(archivo_duplicados, sep="\t")
        else:
            st.error("❌ Formato no compatible.")
            st.stop()

        st.success("✅ Archivo cargado. Total registros: {}".format(len(df)))
        st.dataframe(df.head())

        duplicados, campos = detectar_duplicados(df)
        if duplicados is not None and not duplicados.empty:
            st.warning(f"⚠️ Se encontraron {len(duplicados)} duplicados usando: {', '.join(campos)}")
            st.dataframe(duplicados)
            csv = duplicados.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ Descargar duplicados", csv, "duplicados.csv", "text/csv")
        else:
            st.success("✅ No se encontraron duplicados.")
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")


# -----------------------------
# 📈 PRUEBA 2: MONTOS INUSUALES
# -----------------------------
st.header("2️⃣ Detección de Montos Inusuales")
archivo_montos = st.file_uploader("📁 Subir archivo para detectar montos inusuales", type=["csv", "xlsx", "xls", "txt"], key="montos")

def detectar_montos(df, columna, metodo, umbral_fijo=10000, k=2):
    if columna not in df.columns:
        return pd.DataFrame(), None

    if metodo == "Umbral fijo":
        resultado = df[df[columna] > umbral_fijo]
        return resultado, umbral_fijo

    elif metodo == "Umbral estadístico":
        media = df[columna].mean()
        std = df[columna].std()
        limite = media + k * std
        resultado = df[df[columna] > limite]
        return resultado, limite

    return pd.DataFrame(), None

if archivo_montos:
    try:
        nombre = archivo_montos.name.lower()
        if nombre.endswith(".csv"):
            df_montos = pd.read_csv(archivo_montos)
        elif nombre.endswith((".xlsx", ".xls")):
            df_montos = pd.read_excel(archivo_montos)
        elif nombre.endswith(".txt"):
            df_montos = pd.read_csv(archivo_montos, sep="\t")
        else:
            st.error("❌ Formato no compatible.")
            st.stop()

        st.success("✅ Archivo cargado. Total registros: {}".format(len(df_montos)))
        st.dataframe(df_montos.head())

        columnas_numericas = df_montos.select_dtypes(include='number').columns.tolist()
        if columnas_numericas:
            columna = st.selectbox("📌 Selecciona columna de monto:", columnas_numericas)
            metodo = st.radio("Método para definir monto inusual:", ["Umbral fijo", "Umbral estadístico"])
            
            if metodo == "Umbral fijo":
                umbral = st.number_input("💰 Umbral fijo ($):", min_value=0.0, value=10000.0)
                if st.button("🔍 Ejecutar prueba (fijo)"):
                    resultado, umbral_usado = detectar_montos(df_montos, columna, metodo, umbral_fijo=umbral)
            else:
                k = st.slider("🔬 Coeficiente (σ)", min_value=1, max_value=5, value=2)
                if st.button("🔍 Ejecutar prueba (estadístico)"):
                    resultado, umbral_usado = detectar_montos(df_montos, columna, metodo, k=k)

            if 'resultado' in locals() and not resultado.empty:
                st.warning(f"⚠️ Se encontraron {len(resultado)} registros con montos inusuales. Umbral: {umbral_usado:,.2f}")
                st.dataframe(resultado)
                csv = resultado.to_csv(index=False).encode('utf-8')
                st.download_button("⬇️ Descargar resultados", csv, "montos_inusuales.csv", "text/csv")
            elif 'resultado' in locals():
                st.success("✅ No se encontraron montos inusuales.")

        else:
            st.error("❌ No se encontraron columnas numéricas.")
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")
