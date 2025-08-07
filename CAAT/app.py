
import pandas as pd

# Cargar archivo
df = pd.read_excel("FACTURAS.xlsx")

# Campos clave para identificar duplicados
campos_clave = ['Número', 'R.U.C.', 'Total', 'Fecha']

# Verificamos si todos los campos están presentes
if all(col in df.columns for col in campos_clave):
    duplicados = df[df.duplicated(subset=campos_clave, keep=False)]
    
    if not duplicados.empty:
        print(f"🔍 Se detectaron {len(duplicados)} posibles facturas duplicadas:")
        print(duplicados[campos_clave + ['Nombres']])
    else:
        print("✅ No se encontraron facturas duplicadas.")
else:
    print("❌ Faltan columnas necesarias en el archivo.")

# Herramienta CAAT para Auditoría

Aplicación web desarrollada en Python y Streamlit para ejecutar pruebas automatizadas de auditoría:
- Detección de facturas duplicadas
- Montos inusuales
- Conciliación de reportes
- Registros fuera de horario
- Revisión de horas extras

## Cómo usar
1. Subir archivo .csv o .xlsx
2. Elegir prueba
3. Descargar resultados

streamlit
pandas
openpyxl
