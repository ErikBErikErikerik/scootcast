""" map_view.py shows e-scooters on map of St. Gallen """
import pandas as pd
import streamlit as st


def show_map(scooters):
    """ shows a list of scooter on a map.
    scooters: list of dictionaries with the keys 'lat' and 'lon'
    """


    # when no scooter -> show a message, not empty map
    if len(scooters) == 0:
        st.write('No e-scooters available.')
        return


    # collect coordinates in a panda table with collumns 'lat' and 'lon'
    coordinates = pd.DataFrame({
        'lat': [scooter['lat'] for scooter in scooters],
        'lon': [scooter['lon'] for scooter in scooters]
    })

    # how many scooters are there?
    st.write(f'**{len(scooters)}** e-scooters found')

    # draw map
    #st.map is external
    #needs column names 'lat' and 'lon'
    st.map(coordinates)

# AI citation: this file was assisted and corrected by Claude (model Claude Opus 5.5,
# Anthropic) on 2026-11-25, which was reviewed by the team.