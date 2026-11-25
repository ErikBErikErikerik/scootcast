from dataclasses import dataclass


@dataclass
class Scooter:
    """Ein E-Scooter mit Position und Infos."""
    id: str          # eindeutige Nummer
    lat: float       # Breitengrad (Nord/Süd)
    lon: float       # Längengrad (Ost/West)
    anbieter: str    # z.B. "Tier" oder "Voi"
    akku: int        # Akkustand in Prozent (0-100)