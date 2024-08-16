import streamlit as st
from model import RouteFinder
from helper import *
import pydeck as pdk
from bokeh.models.widgets import Button
from bokeh.models import CustomJS
from streamlit_bokeh_events import streamlit_bokeh_events



# Title and description
st.title("Running Route Recommendation")
st.write("Enter your location and preferred distance to recommend a route for you.")

col1, col2 = st.columns(2)
with col1:
    placeholder2 = st.empty()
    latitude = placeholder2.number_input("Latitude")
with col2:
    # Latitude input
    placeholder1 = st.empty()
    longitude = placeholder1.number_input("Longitude")

# Latitude input
loc_button = Button(label="Get Your Location")
loc_button.js_on_event("button_click", CustomJS(code="""
    navigator.geolocation.getCurrentPosition(
        (loc) => {
            document.dispatchEvent(new CustomEvent("GET_LOCATION", {detail: {lat: loc.coords.latitude, lon: loc.coords.longitude}}))
        }
    )
    """))
result = streamlit_bokeh_events(
    loc_button,
    events="GET_LOCATION",
    key="get_location",
    refresh_on_update=False,
    override_height=75,
    debounce_time=0)
if result and "GET_LOCATION" in result:
    location = result.get("GET_LOCATION")
    longitude = placeholder1.number_input("Longitude", value=location['lon'], key='lon')
    latitude = placeholder2.number_input("Latitude", value=location['lat'], key='lat')

# Preferred distance input
distance = st.slider("Preferred Distance (in kilometers)", min_value=1, max_value=100, value=5)

# Run button
if st.button("Generate"):
    with st.spinner('Wait for it...'):
        route_finder = RouteFinder(
            strava_client_id=st.secrets["strava_client_id"],
            strava_client_secret=st.secrets["strava_client_secret"],
            strava_refresh_token=st.secrets["strava_refresh_token"],
            google_api_key=st.secrets["google_api_key"],
            init_cor=(float(latitude), float(longitude)),
            ideal_distance=int(distance),
            init_diag_distance=30,
            k=3,
            downsample_ratio=2
        )
        route_finder.run()
        view_state, layer = format_output_route(route_finder)
        r = pdk.Deck(layers=[layer], initial_view_state=view_state, map_style='road')

    st.pydeck_chart(r)

