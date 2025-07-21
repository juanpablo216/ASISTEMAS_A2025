import streamlit as st
import pandas as pd
import plotly.express as px

# Leer archivo Excel
df = pd.read_excel("Cuestionario.xlsx")

st.set_page_config(page_title="Auditoría de Sistemas", layout="wide")
st.title("📋 Evaluación de Auditoría – Aplicación Streamlit")

# Obtener dominios únicos
dominios = df['Dominio'].unique()
respuestas = {}

# Mostrar preguntas por dominio
st.header("🧩 Cuestionario")
for dominio in dominios:
    st.subheader(f"🔹 Dominio: {dominio}")
    preguntas = df[df['Dominio'] == dominio]['Pregunta']
    dominio_respuestas = []
    for pregunta in preguntas:
        valor = st.slider(pregunta, 1, 5, 3)
        dominio_respuestas.append(valor)
    respuestas[dominio] = dominio_respuestas

# Evaluar resultados
if st.button("📊 Evaluar resultados"):
    resultados = {}
    for dominio, valores in respuestas.items():
        promedio = sum(valores) / len(valores)
        resultados[dominio] = promedio

    resultados_df = pd.DataFrame(list(resultados.items()), columns=["Dominio", "Promedio"])

    st.subheader("📈 Gráfico de Resultados")
    fig = px.bar(resultados_df, x="Dominio", y="Promedio", color="Promedio",
                 color_continuous_scale=["red", "yellow", "green"], range_y=[1, 5])
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🧠 Interpretación")
    for dominio, promedio in resultados.items():
        if promedio <= 2.0:
            mensaje = "🔴 Riesgo Alto – Se requiere intervención inmediata"
        elif promedio <= 3.5:
            mensaje = "🟡 Riesgo Medio – Oportunidad de mejora"
        else:
            mensaje = "🟢 Cumplimiento Bueno – Controles adecuados"
        st.markdown(f"**{dominio}** → {mensaje} (Puntaje: {promedio:.2f})")
