import streamlit as st
from services.scooter_api import get_scooters
from components.map_view import show_map

st.title("E-Scooter in St. Gallen")

scooters = get_scooters()
st.write(f"{len(scooters)} Scooter gefunden")
show_map(scooters)

