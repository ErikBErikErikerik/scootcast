# Library for sending requests to the internet 
import requests

# Base address of the sharedmobility.ch API 
BASE_URL = "https://api.sharedmobility.ch/v1/sharedmobility/identify"


def get_scooters():
    """Fetch all e-scooters around St. Gallen and return them as a list of dictionaries."""

    # Empty list where we collect all scooters
    scooters = []

    # The API returns at most 50 results per request.
    # offset = from which result on the API should start (0 = the very first one)
    offset = 0

    # Repeat until there are no more scooters to fetch
    while True:
        # Our request parameters (names taken from the API documentation)
        params = {
            "Geometry": "9.3767,47.4245",   # center point: Marktplatz St. Gallen (longitude, latitude)
            "Tolerance": 3000,               # search radius in meters
            "offset": offset,                # start position (0, 50, 100, ...)
            "geometryFormat": "esrijson",    # format of the coordinates in the response
            "filters": "ch.bfe.sharedmobility.vehicle_type=E-Scooter",  # only e-scooters
        }

        # Send a GET request to the API
        response = requests.get(BASE_URL, params=params, timeout=10)

        # Check that the request was successful (200 = OK), otherwise stop
        if response.status_code != 200:
            print("Failed to retrieve data:", response.status_code)
            break

        # Parse the JSON response -> list of scooters
        data = response.json()

        # Go through every scooter in the response
        for entry in data:
            # Keep only the information we need, in a simple dictionary
            scooter = {
                "id": entry["id"],                                    # unique id
                "lat": entry["geometry"]["y"],                        # latitude (north/south)
                "lon": entry["geometry"]["x"],                        # longitude (east/west)
                "provider": entry["attributes"]["provider_name"],     # e.g. "Dott st.-gallen"
                "available": entry["attributes"]["available"],        # True = can be rented
            }
            # Add the scooter to our list
            scooters.append(scooter)

        # Fewer than 50 results -> this was the last page, stop
        if len(data) < 50:
            break

        # Otherwise: fetch the next 50
        offset = offset + 50

    # Return the complete list of scooters
    return scooters


# Test: only runs when this file is started directly (python services/scooter_api.py)
if __name__ == "__main__":
    all_scooters = get_scooters()
    print("Number of scooters:", len(all_scooters))
