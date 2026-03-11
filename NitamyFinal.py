import streamlit as st
import pandas as pd
import googlemaps
import datetime
import folium
from streamlit_folium import st_folium
import polyline
import urllib.parse

# ---------------------------------------------------
# CONFIGURACIÓN GENERAL
# ---------------------------------------------------
st.set_page_config(page_title="Optimizador de Rutas", layout="wide")

st.title("🚚 Optimizador de Rutas")

if "MAPS_API_KEY" not in st.secrets:
    st.error("⚠️ Configura la MAPS_API_KEY en Secrets.")
    st.stop()

gmaps = googlemaps.Client(key=st.secrets["MAPS_API_KEY"])

flota = [
    {"nombre": "ISUZU 2", "capacidad": 6500, "costo_km": 3.42},
    {"nombre": "RAM 4000", "capacidad": 3500, "costo_km": 6.31},
    {"nombre": "ISUZU 1", "capacidad": 4000, "costo_km": 3.68},
    {"nombre": "VW CRAFTER", "capacidad": 1000, "costo_km": 1.76},
    {"nombre": "URVAN PANEL", "capacidad": 1350, "costo_km": 1.90},
    {"nombre": "CHEVROLET TORNADO", "capacidad": 650, "costo_km": 1.70},
]

if "resultado_ruta" not in st.session_state:
    st.session_state["resultado_ruta"] = None

if "error_ruta" not in st.session_state:
    st.session_state["error_ruta"] = None


# ---------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------
def limpiar_destinos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Destino" not in df.columns:
        return pd.DataFrame(columns=["Destino", "¿Límite?", "Hora Límite"])

    df = df.copy()

    df["Destino"] = df["Destino"].fillna("").astype(str).str.strip()

    if "¿Límite?" not in df.columns:
        df["¿Límite?"] = False
    else:
        df["¿Límite?"] = df["¿Límite?"].fillna(False).astype(bool)

    if "Hora Límite" not in df.columns:
        df["Hora Límite"] = None

    df = df[df["Destino"] != ""].reset_index(drop=True)
    return df


def seleccionar_vehiculo(peso: float):
    candidatos = [v for v in flota if v["capacidad"] >= peso]
    if not candidatos:
        return None
    return min(candidatos, key=lambda x: x["costo_km"])


def formatear_hora(dt_obj: datetime.datetime) -> str:
    return dt_obj.strftime("%I:%M %p").lstrip("0")


def crear_url_google_maps(origen: str, destinos_ordenados: list[str]) -> str:
    """
    Crea URL para abrir la ruta circular en Google Maps.
    Google Maps limita waypoints, pero para pocos destinos funciona bien.
    """
    if not destinos_ordenados:
        return ""

    origin_enc = urllib.parse.quote(origen)
    destination_enc = urllib.parse.quote(origen)

    # Google Maps Directions URL
    base_url = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_enc}"
        f"&destination={destination_enc}"
        f"&travelmode=driving"
    )

    if destinos_ordenados:
        wp = "|".join(urllib.parse.quote(x) for x in destinos_ordenados)
        base_url += f"&waypoints={wp}"

    return base_url


def calcular_ruta(origen: str, destinos_raw: pd.DataFrame, peso: float,
                  fecha: datetime.date, hora: datetime.time) -> dict:
    departure_dt = datetime.datetime.combine(fecha, hora)

    respuesta = gmaps.directions(
        origin=origen,
        destination=origen,  # fuerza ruta circular
        waypoints=destinos_raw["Destino"].tolist(),
        optimize_waypoints=True,
        mode="driving",
        departure_time=departure_dt
    )

    if not respuesta:
        raise ValueError("Google Maps no devolvió resultados para la ruta.")

    ruta = respuesta[0]
    legs = ruta.get("legs", [])

    if not legs:
        raise ValueError("La respuesta no contiene tramos ('legs').")

    distancia_total_m = sum(leg.get("distance", {}).get("value", 0) for leg in legs)
    distancia_total_km = distancia_total_m / 1000

    tiempo_total_seg = sum(leg.get("duration", {}).get("value", 0) for leg in legs)
    tiempo_total_hrs = tiempo_total_seg / 3600

    vehiculo = seleccionar_vehiculo(peso)
    if vehiculo is None:
        raise ValueError(f"No existe una unidad con capacidad suficiente para {peso} kg.")

    costo_estimado = distancia_total_km * vehiculo["costo_km"]

    waypoint_order = ruta.get("waypoint_order", list(range(len(destinos_raw))))
    destinos_ordenados_df = destinos_raw.iloc[waypoint_order].reset_index(drop=True)

    # Construcción del itinerario con hora estimada de llegada y estatus
    itinerario = []
    acumulado_seg = 0

    # Los primeros N legs corresponden a origen -> paradas -> ... -> última parada
    # El último leg es regreso a base
    num_stops = len(destinos_ordenados_df)

    for i in range(num_stops):
        leg = legs[i]
        acumulado_seg += leg.get("duration", {}).get("value", 0)
        llegada_dt = departure_dt + datetime.timedelta(seconds=acumulado_seg)

        destino_row = destinos_ordenados_df.iloc[i]
        usa_limite = bool(destino_row.get("¿Límite?", False))
        hora_limite = destino_row.get("Hora Límite", None)

        estatus = "SIN LÍMITE"
        if usa_limite and pd.notna(hora_limite):
            try:
                if isinstance(hora_limite, str):
                    hora_limite = datetime.datetime.strptime(hora_limite.strip(), "%H:%M").time()

                limite_dt = datetime.datetime.combine(fecha, hora_limite)

                if llegada_dt <= limite_dt:
                    estatus = "🟢 A TIEMPO"
                else:
                    estatus = "🔴 TARDE"
            except Exception:
                estatus = "LÍMITE INVÁLIDO"

        elif usa_limite:
            estatus = "LÍMITE SIN HORA"

        itinerario.append({
            "Orden": i + 1,
            "Destino": destino_row["Destino"],
            "Llegada": formatear_hora(llegada_dt),
            "Estatus": estatus
        })

    itinerario_df = pd.DataFrame(itinerario)

    # Mapa
    puntos = []
    encoded = ruta.get("overview_polyline", {}).get("points")
    if encoded:
        puntos = polyline.decode(encoded)

    # Ruta ordenada para botón Google Maps
    destinos_ordenados = destinos_ordenados_df["Destino"].tolist()
    maps_url = crear_url_google_maps(origen, destinos_ordenados)

    return {
        "distancia_total_km": distancia_total_km,
        "tiempo_total_hrs": tiempo_total_hrs,
        "vehiculo": vehiculo,
        "costo_estimado": costo_estimado,
        "itinerario_df": itinerario_df,
        "puntos_mapa": puntos,
        "ruta_bruta": ruta,
        "legs": legs,
        "maps_url": maps_url,
        "destinos_ordenados": destinos_ordenados,
        "origen": origen
    }


def render_kpi_principal(resultado: dict):
    distancia = resultado["distancia_total_km"]

    st.subheader("📏 Kilometraje Total")
    st.write(f"**Distancia total de la ruta (A-B-A): {distancia:.2f} km**")
    st.success(f"Kilometraje total: {distancia:.2f} km")
    st.metric("Kilometraje total", f"{distancia:.2f} km")


def render_kpis_secundarios(resultado: dict):
    try:
        k1, k2, k3 = st.columns(3)
        k1.metric("Tiempo Estimado", f"{resultado['tiempo_total_hrs']:.2f} horas")
        k2.metric("Unidad Sugerida", resultado["vehiculo"]["nombre"])
        k3.metric("Costo de Transporte", f"${resultado['costo_estimado']:.2f} MXN")
    except Exception:
        st.write(f"**Tiempo Estimado:** {resultado['tiempo_total_hrs']:.2f} horas")
        st.write(f"**Unidad Sugerida:** {resultado['vehiculo']['nombre']}")
        st.write(f"**Costo de Transporte:** ${resultado['costo_estimado']:.2f} MXN")


def render_itinerario(resultado: dict):
    st.markdown("## 🏁 Itinerario Detallado")

    st.markdown(
        f"""
        <div style="background-color:#dff0e4; padding:18px; border-radius:12px; margin-bottom:14px;">
            <span style="font-size:18px; color:#177d3f;">
                Unidad Sugerida: <b>{resultado['vehiculo']['nombre']}</b>
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if resultado["maps_url"]:
        st.link_button("🗺️ ABRIR NAVEGACIÓN (GOOGLE MAPS)", resultado["maps_url"])

    if not resultado["itinerario_df"].empty:
        st.dataframe(
            resultado["itinerario_df"],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No se generó itinerario visible.")

    st.info("**Final:** regreso al punto de origen.")


def render_mapa(resultado: dict):
    st.markdown("## 🗺️ Mapa Interactivo")

    puntos = resultado["puntos_mapa"]
    if not puntos:
        st.warning("No fue posible decodificar la polilínea del mapa.")
        return

    m = folium.Map(location=puntos[0], zoom_start=11)

    # Polilínea
    folium.PolyLine(
        puntos,
        color="blue",
        weight=6,
        opacity=0.75,
        tooltip="Ruta optimizada"
    ).add_to(m)

    # Marker base
    folium.Marker(
        location=puntos[0],
        popup="Base (Inicio / Fin)",
        tooltip="Base",
        icon=folium.Icon(color="green", icon="home", prefix="fa")
    ).add_to(m)

    # Marcadores de destinos con geocodificación simple
    for i, destino in enumerate(resultado["destinos_ordenados"], start=1):
        try:
            geo = gmaps.geocode(destino)
            if geo:
                latlng = geo[0]["geometry"]["location"]
                folium.Marker(
                    location=[latlng["lat"], latlng["lng"]],
                    popup=f"Parada {i}: {destino}",
                    tooltip=f"Parada {i}",
                    icon=folium.Icon(color="blue", icon="truck", prefix="fa")
                ).add_to(m)
        except Exception:
            pass

    st_folium(m, width=900, height=520, key="mapa_final")


# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------
with st.sidebar:
    st.header("📋 Parámetros de Ruta")

    with st.form("panel_control"):
        origen = st.text_input(
            "Base de Salida",
            "20 de Noviembre, Santa María Aztahuacán, Iztapalapa"
        )

        peso = st.number_input("Carga total (kg)", min_value=1, value=500)

        fecha = st.date_input("Fecha", datetime.date.today())
        hora = st.time_input("Hora Salida", datetime.time(8, 0))

        st.write("---")
        st.subheader("📍 Destinos")

        df_base = pd.DataFrame(columns=["Destino", "¿Límite?", "Hora Límite"])
        df_editado = st.data_editor(
            df_base,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="editor_destinos"
        )

        btn_calcular = st.form_submit_button("🚀 OPTIMIZAR RUTA")


# ---------------------------------------------------
# PROCESO
# ---------------------------------------------------
if btn_calcular:
    st.session_state["resultado_ruta"] = None
    st.session_state["error_ruta"] = None

    try:
        destinos_raw = limpiar_destinos(df_editado)

        if destinos_raw.empty:
            st.session_state["error_ruta"] = "⚠️ Agrega al menos un destino válido."
        else:
            resultado = calcular_ruta(origen, destinos_raw, peso, fecha, hora)
            st.session_state["resultado_ruta"] = resultado

    except Exception as e:
        st.session_state["error_ruta"] = f"Error técnico en el cálculo: {e}"


# ---------------------------------------------------
# RENDER FINAL
# ---------------------------------------------------
if st.session_state["error_ruta"]:
    st.error(st.session_state["error_ruta"])

if st.session_state["resultado_ruta"] is not None:
    resultado = st.session_state["resultado_ruta"]

    # KPI principal arriba
    render_kpi_principal(resultado)

    st.markdown("---")

    # KPIs secundarios
    render_kpis_secundarios(resultado)

    st.markdown("---")

    # Layout principal
    try:
        col_it, col_map = st.columns([1, 1.25])

        with col_it:
            render_itinerario(resultado)

        with col_map:
            render_mapa(resultado)

    except Exception:
        render_itinerario(resultado)
        render_mapa(resultado)
