"""Named places that the analyses compare, as lists of grid cells.

The names are our own estimates from the coordinates. Check them on a map
before showing them in the presentation.

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-26 and reviewed by the project team.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collector"))

from collect import cell_id

# (lat, lon) of the cell centers that make up each place.
PLACE_COORDINATES = {
    "st_gallen": {
        "Bahnhof": [(47.4227, 9.3683), (47.4245, 9.3710), (47.4209, 9.3683)],
        "HSG": [(47.4317, 9.3763), (47.4317, 9.3736)],
    },
    "zurich": {
        "Enge": [(47.3599, 8.5349)],
        "ETH Zentrum": [(47.3760, 8.5481)],
        "ETH Hoenggerberg": [(47.4084, 8.5057)],
        "Stadelhofen": [(47.3670, 8.5481)],
    },
}

# The same places as grid cell IDs, e.g. PLACES["zurich"]["Enge"] == ["26360_3215"].
PLACES = {
    city: {name: [cell_id(lat, lon) for lat, lon in points] for name, points in places.items()}
    for city, places in PLACE_COORDINATES.items()
}
