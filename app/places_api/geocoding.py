"""
Optional geocoding helper using Google Geocoding API or Places TextSearch center bias.
"""
from typing import Optional, Tuple
import httpx
from app.config import get_settings

settings = get_settings()


async def geocode_city(city_name: str) -> Optional[Tuple[float, float]]:
    """
    Resolve city or province name to (latitude, longitude) coordinates.
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        # Default center coordinates for Indonesia (e.g., Bandung / Jakarta)
        return (-6.917464, 107.619123)

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": city_name,
        "key": settings.GOOGLE_MAPS_API_KEY
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    return (loc["lat"], loc["lng"])
    except Exception as e:
        print(f"[Geocoding Warning] Could not geocode '{city_name}': {e}")
    return None
