import streamlit as st
import pandas as pd

st.set_page_config(page_title="CAAT - Detección de Facturas Duplicadas", layout="wide")

st.title("🔎 Herramienta CAAT - Detección de Facturas Duplicadas")
st.markdown("Sube un archivo en formato **CSV**, **Excel (.xlsx/.xls)** o **.txt tabulado** y la app identificará duplicados automáticamente.")

# Subir archivo
archivo = st.file_uploader("📁 Cargar archivo de facturas", type=["csv", "xlsx", "xls", "txt"])

# Función para detectar duplicados
def detectar_duplicados(df):
    # Posibles combinaciones comunes para detectar duplicados
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

# Procesar archivo
if archivo:
    nombre_archivo = archivo.name.lower()
    try:
        if nombre_archivo.endswith(".csv"):
            df = pd.read_csv(archivo)
        elif nombre_archivo.endswith((".xlsx", ".xls")):
            df = pd.read_excel(archivo)
        elif nombre_archivo.endswith(".txt"):
            df = pd.read_csv(archivo, sep="\t", encoding="utf-8")
        else:
            st.error("❌ Formato de archivo no compatible.")
            st.stop()

        st.success("✅ Archivo cargado correctamente.")
        st.write("Vista previa de los datos:")
        st.dataframe(df.head())

        duplicados, campos_utilizados = detectar_duplicados(df)

        if duplicados is not None and not duplicados.empty:
            st.warning(f"⚠️ Se encontraron {len(duplicados)} registros duplicados basados en los campos: {', '.join(campos_utilizados)}.")
            st.dataframe(duplicados)

            # Botón para descargar
            csv = duplicados.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ Descargar duplicados CSV", csv, "facturas_duplicadas.csv", "text/csv")
        else:
            st.success("✅ No se encontraron facturas duplicadas o no hay campos comunes detectables.")
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")
else:
    st.info("👈 Esperando que subas un archivo...")
