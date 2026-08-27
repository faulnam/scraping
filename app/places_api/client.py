"""
Places API Client: Supports live Google Places API (New), live SerpApi Google Maps engine,
and fixture-based mock support for offline testing.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from app.config import get_settings
from app.places_api.field_masks import SEARCH_FIELD_MASK, PLACE_DETAILS_FIELD_MASK

settings = get_settings()

PLACES_BASE_URL = "https://places.googleapis.com/v1/places"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class PlacesApiClient:
    """Wrapper client for Google Places API (New) and SerpApi Google Maps."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        serpapi_key: Optional[str] = None,
        use_mock: Optional[bool] = None
    ):
        self.google_api_key = api_key or settings.GOOGLE_MAPS_API_KEY or ""
        self.serpapi_key = serpapi_key or settings.SERPAPI_API_KEY or ""

        if use_mock is not None:
            self.is_mock_mode = use_mock
        else:
            has_valid_key = bool(self.google_api_key.strip() or self.serpapi_key.strip())
            self.is_mock_mode = not has_valid_key

        self._mock_search_data: Optional[Dict[str, Any]] = None
        self._mock_details_data: Optional[Dict[str, Any]] = None
        self._serpapi_details_cache: Dict[str, Any] = {}

    def _load_mock_fixtures(self):
        """Load fixture files if available."""
        if self._mock_search_data is None:
            search_file = FIXTURES_DIR / "places_search_response.json"
            if search_file.exists():
                with open(search_file, "r", encoding="utf-8") as f:
                    self._mock_search_data = json.load(f)
            else:
                self._mock_search_data = {"places": [], "nextPageToken": None}

        if self._mock_details_data is None:
            details_file = FIXTURES_DIR / "places_details_responses.json"
            if details_file.exists():
                with open(details_file, "r", encoding="utf-8") as f:
                    self._mock_details_data = json.load(f)
            else:
                self._mock_details_data = {}

    async def search_text(
        self,
        text_query: str,
        page_size: int = 20,
        page_token: Optional[str] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Execute search query against SerpApi (Google Maps), Google Places API (New), or Mock Fixtures.
        """
        # 1. Mock Mode
        if self.is_mock_mode:
            print(f"[Places API - MOCK MODE] Using fixture data for search_text: '{text_query}'")
            self._load_mock_fixtures()
            places = self._mock_search_data.get("places", [])[:page_size] if self._mock_search_data else []
            return {
                "places": places,
                "nextPageToken": None,
                "api_requests_used": 1
            }

        # 2. SerpApi Mode (Live Google Maps search without credit card)
        if self.serpapi_key and self.serpapi_key.strip():
            print(f"[SerpApi - LIVE MODE] Searching Google Maps for '{text_query}'...")
            params = {
                "engine": "google_maps",
                "q": text_query,
                "api_key": self.serpapi_key.strip(),
                "hl": "id",
                "gl": "id",
            }
            if page_token:
                params["start"] = page_token

            for attempt in range(1, max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.get(SERPAPI_SEARCH_URL, params=params)
                        if resp.status_code == 200:
                            data = resp.json()
                            results = data.get("local_results", [])
                            # Cache full details for subsequent get_place_details calls
                            places_list = []
                            for item in results:
                                place_id = item.get("place_id") or item.get("data_id") or item.get("title")
                                item["id"] = place_id
                                self._serpapi_details_cache[place_id] = item
                                places_list.append(item)

                            return {
                                "places": places_list,
                                "nextPageToken": data.get("serpapi_pagination", {}).get("next"),
                                "api_requests_used": 1
                            }
                        elif resp.status_code in (429, 500, 502, 503, 504):
                            wait_sec = 2 ** attempt
                            print(f"[SerpApi {resp.status_code}] Retrying in {wait_sec}s...")
                            await asyncio.sleep(wait_sec)
                        else:
                            print(f"[SerpApi Error] HTTP {resp.status_code}: {resp.text}")
                            break
                except Exception as e:
                    print(f"[SerpApi Exception] Attempt {attempt} failed: {e}")
                    await asyncio.sleep(1.0 * attempt)

            return {"places": [], "nextPageToken": None, "api_requests_used": 1}

        # 3. Official Google Places API (New) Mode
        url = f"{PLACES_BASE_URL}:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.google_api_key,
            "X-Goog-FieldMask": SEARCH_FIELD_MASK,
        }
        body: Dict[str, Any] = {
            "textQuery": text_query,
            "pageSize": min(page_size, 20),
        }
        if page_token:
            body["pageToken"] = page_token

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, headers=headers, json=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        data["api_requests_used"] = 1
                        return data
                    elif resp.status_code in (429, 500, 502, 503, 504):
                        wait_sec = 2 ** attempt
                        print(f"[Places API {resp.status_code}] Retrying search_text in {wait_sec}s...")
                        await asyncio.sleep(wait_sec)
                    else:
                        print(f"[Places API Error] HTTP {resp.status_code}: {resp.text}")
                        break
            except Exception as e:
                print(f"[Places API Exception] Attempt {attempt} failed: {e}")
                await asyncio.sleep(1.0 * attempt)

        # Fallback to empty result on failure
        return {"places": [], "nextPageToken": None, "api_requests_used": 1}

    async def get_place_details(
        self,
        place_id: str,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch full details for 1 place_id.
        """
        # 1. Check SerpApi memory cache (SerpApi already returns full details in local_results)
        if place_id in self._serpapi_details_cache:
            return self._serpapi_details_cache[place_id]

        # 2. Mock Mode
        if self.is_mock_mode:
            self._load_mock_fixtures()
            if self._mock_details_data and place_id in self._mock_details_data:
                return self._mock_details_data[place_id]
            # Fallback mock detail if not found in fixture map
            return {
                "id": place_id,
                "displayName": {"text": "Usaha Prospek Mock", "languageCode": "id"},
                "formattedAddress": "Jl. Testing Prospek No. 1, Kota Bandung, Jawa Barat",
                "nationalPhoneNumber": "0812-3456-7890",
                "websiteUri": None,
                "rating": 4.5,
                "userRatingCount": 25,
                "regularOpeningHours": {
                    "weekdayDescriptions": ["Senin: 08.00–17.00", "Selasa: 08.00–17.00"]
                },
                "businessStatus": "OPERATIONAL",
                "googleMapsUri": f"https://maps.google.com/?cid={place_id}",
                "location": {"latitude": -6.917464, "longitude": 107.619123}
            }

        # 3. Official Google Places API (New) Details
        if self.google_api_key and self.google_api_key.strip():
            url = f"{PLACES_BASE_URL}/{place_id}"
            headers = {
                "X-Goog-Api-Key": self.google_api_key,
                "X-Goog-FieldMask": PLACE_DETAILS_FIELD_MASK,
            }

            for attempt in range(1, max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            return resp.json()
                        elif resp.status_code in (429, 500, 502, 503, 504):
                            wait_sec = 2 ** attempt
                            print(f"[Places Details {resp.status_code}] Retrying {place_id} in {wait_sec}s...")
                            await asyncio.sleep(wait_sec)
                        else:
                            print(f"[Places Details Error] {place_id} HTTP {resp.status_code}: {resp.text}")
                            break
                except Exception as e:
                    print(f"[Places Details Exception] {place_id} Attempt {attempt} failed: {e}")
                    await asyncio.sleep(1.0 * attempt)

        return None
