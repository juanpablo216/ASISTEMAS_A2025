
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
