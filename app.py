import streamlit as st
import pandas as pd

st.set_page_config(page_title="CAAT - Herramienta de Auditoría", layout="wide")

st.title("🧪 Herramienta CAAT - Pruebas de Auditoría Automatizadas")
st.markdown("Sube un archivo en formato **CSV**, **Excel (.xlsx/.xls)** o **.txt tabulado** y selecciona la prueba que deseas ejecutar.")

# Cargar archivo
archivo = st.file_uploader("📁 Cargar archivo de datos", type=["csv", "xlsx", "xls", "txt"])

# Funciones
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

def detectar_montos_inusuales(df, columna, metodo, umbral_fijo=10000.0, k=2):
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

# Procesamiento
if archivo:
    try:
        nombre = archivo.name.lower()
        if nombre.endswith(".csv"):
            df = pd.read_csv(archivo)
        elif nombre.endswith((".xlsx", ".xls")):
            df = pd.read_excel(archivo)
        elif nombre.endswith(".txt"):
            df = pd.read_csv(archivo, sep="\t", encoding="utf-8")
        else:
            st.error("❌ Formato de archivo no soportado.")
            st.stop()

        st.success("✅ Archivo cargado correctamente.")
        st.info(f"📊 Total de registros: {len(df)}")
        st.dataframe(df.head())

        # Selección de prueba
        prueba = st.selectbox("🧩 Selecciona la prueba a ejecutar:", [
            "Detección de Facturas Duplicadas",
            "Detección de Montos Inusuales"
        ])

        # 🧪 Prueba 1: Facturas duplicadas
        if prueba == "Detección de Facturas Duplicadas":
            duplicados, campos = detectar_duplicados(df)
            if duplicados is not None and not duplicados.empty:
                st.warning(f"⚠️ Se encontraron {len(duplicados)} duplicados usando: {', '.join(campos)}")
                st.dataframe(duplicados)
                csv = duplicados.to_csv(index=False).encode('utf-8')
                st.download_button("⬇️ Descargar duplicados", csv, "duplicados.csv", "text/csv")
            else:
                st.success("✅ No se encontraron facturas duplicadas.")

        # 🧪 Prueba 2: Montos inusuales
        elif prueba == "Detección de Montos Inusuales":
            columnas_numericas = df.select_dtypes(include='number').columns.tolist()
            if not columnas_numericas:
                st.error("❌ No se encontraron columnas numéricas.")
                st.stop()

            columna = st.selectbox("📌 Selecciona columna de monto:", columnas_numericas)
            metodo = st.radio("Método de detección:", ["Umbral fijo", "Umbral estadístico"])

            if metodo == "Umbral fijo":
                umbral = st.number_input("💰 Umbral fijo ($):", min_value=0.0, value=10000.0)
                if st.button("🔍 Ejecutar prueba"):
                    resultado, umbral_usado = detectar_montos_inusuales(df, columna, metodo, umbral)
                    if not resultado.empty:
                        st.warning(f"⚠️ Se encontraron {len(resultado)} registros > ${umbral_usado:,.2f}")
                        st.dataframe(resultado)
                        csv = resultado.to_csv(index=False).encode('utf-8')
                        st.download_button("⬇️ Descargar resultados", csv, "montos_inusuales.csv", "text/csv")
                    else:
                        st.success("✅ No se encontraron montos inusuales.")

            elif metodo == "Umbral estadístico":
                k = st.slider("🔬 Coeficiente (σ)", min_value=1, max_value=5, value=2)
                if st.button("🔍 Ejecutar prueba"):
                    resultado, limite = detectar_montos_inusuales(df, columna, metodo, k=k)
                    if not resultado.empty:
                        st.warning(f"⚠️ {len(resultado)} registros superan el umbral dinámico: ${limite:,.2f}")
                        st.dataframe(resultado)
                        csv = resultado.to_csv(index=False).encode('utf-8')
                        st.download_button("⬇️ Descargar resultados", csv, "montos_inusuales.csv", "text/csv")
                    else:
                        st.success("✅ No se encontraron montos inusuales.")

    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")
else:
    st.info("👈 Esperando que subas un archivo...")
