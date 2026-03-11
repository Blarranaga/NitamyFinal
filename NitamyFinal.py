import streamlit as st
import pandas as pd
import googlemaps
import datetime

st.set_page_config(page_title="VRP Test App", layout="wide")

st.title("🧪 VRP Test App")
st.info("Si ves esta app, ya estás corriendo un archivo nuevo y correcto.")

if "MAPS_API_KEY" not in st.secrets:
    st.error("Falta MAPS_API_KEY en Streamlit Secrets.")
    st.stop()

try:
    gmaps = googlemaps.Client(key=st.secrets["MAPS_API_KEY"])
except Exception as e:
    st.error(f"No se pudo inicializar Google Maps: {e}")
    st.stop()

if "resultado" not in st.session_state:
    st.session_state["resultado"] = None

with st.sidebar:
    st.header("Parámetros")
    with st.form("test_form"):
        origen = st.text_input(
            "Origen / Base",
            "20 de Noviembre, Santa María Aztahuacán, Iztapalapa, CDMX"
        )
        peso = st.number_input("Carga total (kg)", min_value=1, value=500)
        fecha = st.date_input("Fecha", datetime.date.today())
        hora = st.time_input("Hora salida", datetime.time(8, 0))

        st.subheader("Destinos")
        df = pd.DataFrame(columns=["Destino"])
        df_editado = st.data_editor(
            df,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="destinos_editor"
        )

        calcular = st.form_submit_button("Calcular prueba")

if calcular:
    try:
        destinos = df_editado.copy()
        destinos["Destino"] = destinos["Destino"].fillna("").astype(str).str.strip()
        destinos = destinos[destinos["Destino"] != ""]

        if destinos.empty:
            st.error("Agrega al menos un destino.")
        else:
            respuesta = gmaps.directions(
                origin=origen,
                destination=origen,
                waypoints=destinos["Destino"].tolist(),
                optimize_waypoints=True,
                mode="driving",
                departure_time="now"
            )

            if not respuesta:
                st.error("Google Maps no devolvió ruta.")
            else:
                ruta = respuesta[0]
                legs = ruta.get("legs", [])

                distancia_total_m = sum(
                    leg.get("distance", {}).get("value", 0) for leg in legs
                )
                distancia_total_km = distancia_total_m / 1000

                tiempo_total_seg = sum(
                    leg.get("duration", {}).get("value", 0) for leg in legs
                )
                tiempo_total_hr = tiempo_total_seg / 3600

                st.session_state["resultado"] = {
                    "distancia_km": distancia_total_km,
                    "tiempo_hr": tiempo_total_hr,
                    "legs": legs,
                    "waypoint_order": ruta.get("waypoint_order", []),
                    "destinos": destinos.reset_index(drop=True)
                }

    except Exception as e:
        st.error(f"Error durante la prueba: {e}")

resultado = st.session_state.get("resultado")

if resultado is not None:
    st.subheader("✅ Resultado de prueba")

    # Mostrar el KPI de 4 maneras distintas para validar renderizado
    st.write(f"**Distancia total (A-B-A): {resultado['distancia_km']:.2f} km**")
    st.success(f"Kilometraje total: {resultado['distancia_km']:.2f} km")
    st.metric("Kilometraje total", f"{resultado['distancia_km']:.2f} km")
    st.code(f"DISTANCIA_TOTAL_KM = {resultado['distancia_km']:.2f}")

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Tiempo total:** {resultado['tiempo_hr']:.2f} horas")
        st.write(f"**Número de tramos (legs):** {len(resultado['legs'])}")

    with col2:
        st.write("**Distancia por tramo (m):**")
        st.write([
            leg.get("distance", {}).get("value", 0)
            for leg in resultado["legs"]
        ])

    orden = resultado["waypoint_order"]
    destinos = resultado["destinos"]

    if orden:
        itinerario = []
        for i, idx in enumerate(orden):
            itinerario.append({
                "Orden": i + 1,
                "Destino": destinos.iloc[idx]["Destino"]
            })
        st.dataframe(pd.DataFrame(itinerario), use_container_width=True, hide_index=True)
    else:
        st.info("No se recibió waypoint_order, pero la ruta fue calculada.")
