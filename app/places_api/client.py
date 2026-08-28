"""
Places API Client: Supports live Google Places API (New), live SerpApi Google Maps engine,
multi-key auto-fallback, priority key rotation, and fixture-based mock support for offline testing.
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.places_api.field_masks import SEARCH_FIELD_MASK, PLACE_DETAILS_FIELD_MASK
from app import models

settings = get_settings()

PLACES_BASE_URL = "https://places.googleapis.com/v1/places"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class PlacesApiClient:
    """Wrapper client for Google Places API (New) and SerpApi Google Maps with Multi-Key Auto-Fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        serpapi_key: Optional[str] = None,
        use_mock: Optional[bool] = None,
        db: Optional[Session] = None
    ):
        self.db = db
        self.google_api_key = api_key or settings.GOOGLE_MAPS_API_KEY or ""
        self.serpapi_key = serpapi_key or settings.SERPAPI_API_KEY or ""

        if use_mock is not None:
            self.is_mock_mode = use_mock
        else:
            # Check if any valid key exists in DB or in settings
            has_db_key = False
            if self.db:
                try:
                    has_db_key = self.db.query(models.ApiKeyConfig).filter(
                        models.ApiKeyConfig.is_active == True,
                        models.ApiKeyConfig.status != "invalid"
                    ).count() > 0
                except Exception:
                    pass
            has_valid_key = bool(self.google_api_key.strip() or self.serpapi_key.strip() or has_db_key)
            self.is_mock_mode = not has_valid_key

        self._mock_search_data: Optional[Dict[str, Any]] = None
        self._mock_details_data: Optional[Dict[str, Any]] = None
        self._serpapi_details_cache: Dict[str, Any] = {}

    def _get_active_serpapi_keys(self) -> List[Dict[str, Any]]:
        """Retrieve active SerpApi keys from DB ordered by priority, or fallback to settings."""
        keys = []
        if self.db:
            try:
                db_keys = self.db.query(models.ApiKeyConfig).filter(
                    models.ApiKeyConfig.provider == "serpapi",
                    models.ApiKeyConfig.is_active == True,
                    models.ApiKeyConfig.status != "exhausted",
                    models.ApiKeyConfig.status != "invalid"
                ).order_by(models.ApiKeyConfig.priority.asc()).all()

                for k in db_keys:
                    if k.api_key and k.api_key.strip():
                        keys.append({
                            "id": k.id,
                            "label": k.label,
                            "api_key": k.api_key.strip(),
                            "priority": k.priority,
                            "db_obj": k
                        })
            except Exception as e:
                print(f"[Places API Client] Error loading keys from DB: {e}")

        # Fallback to single serpapi_key from config if DB has no active keys
        if not keys and self.serpapi_key and self.serpapi_key.strip():
            keys.append({
                "id": None,
                "label": "SerpApi Default (.env)",
                "api_key": self.serpapi_key.strip(),
                "priority": 1,
                "db_obj": None
            })

        return keys

    def _mark_key_status(self, key_info: Dict[str, Any], status: str, error_msg: Optional[str] = None):
        """Update key status in database if key has a db record."""
        db_obj = key_info.get("db_obj")
        if db_obj and self.db:
            try:
                db_obj.status = status
                if error_msg:
                    db_obj.last_error_message = error_msg[:500]
                self.db.commit()
                print(f"[API Key Manager] Key '{key_info['label']}' marked as '{status}': {error_msg}")
            except Exception as err:
                print(f"[API Key Manager] Failed to update key status: {err}")
                self.db.rollback()

    def _record_key_usage(self, key_info: Dict[str, Any]):
        """Increment usage counter and update last_used_at for key."""
        db_obj = key_info.get("db_obj")
        if db_obj and self.db:
            try:
                db_obj.requests_used = (db_obj.requests_used or 0) + 1
                db_obj.last_used_at = datetime.utcnow()
                self.db.commit()
            except Exception as err:
                print(f"[API Key Manager] Failed to record usage: {err}")
                self.db.rollback()

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
        start_offset: int = 0,
        page_token: Optional[str] = None,
        max_retries_per_key: int = 2
    ) -> Dict[str, Any]:
        """
        Execute search query against SerpApi (Google Maps) with Multi-Key Fallback,
        Google Places API (New), or Mock Fixtures.
        """
        # 1. Mock Mode
        if self.is_mock_mode:
            print(f"[Places API - MOCK MODE] Using fixture data for search_text: '{text_query}' (offset {start_offset})")
            self._load_mock_fixtures()
            all_places = self._mock_search_data.get("places", []) if self._mock_search_data else []
            slice_end = start_offset + page_size
            places = all_places[start_offset:slice_end]
            has_next = slice_end < len(all_places)
            return {
                "places": places,
                "nextPageToken": str(slice_end) if has_next else None,
                "has_next_page": has_next,
                "api_requests_used": 1
            }

        # 2. SerpApi Multi-Key Auto-Fallback Mode
        active_serp_keys = self._get_active_serpapi_keys()
        if active_serp_keys:
            for key_info in active_serp_keys:
                api_key_str = key_info["api_key"]
                key_label = key_info["label"]
                print(f"[SerpApi - LIVE MODE] Searching '{text_query}' with Key '{key_label}' (start={start_offset})...")

                params = {
                    "engine": "google_maps",
                    "q": text_query,
                    "api_key": api_key_str,
                    "hl": "id",
                    "gl": "id",
                }
                if start_offset > 0:
                    params["start"] = start_offset
                elif page_token and str(page_token).isdigit():
                    params["start"] = int(page_token)

                key_failed_exhausted = False

                for attempt in range(1, max_retries_per_key + 1):
                    try:
                        async with httpx.AsyncClient(timeout=35.0) as client:
                            resp = await client.get(SERPAPI_SEARCH_URL, params=params)
                            
                            if resp.status_code == 200:
                                data = resp.json()

                                # Check if SerpApi returned an account/quota error inside JSON
                                if "error" in data:
                                    err_text = str(data["error"])
                                    print(f"[SerpApi Error Response] {err_text}")
                                    if "run out of searches" in err_text.lower() or "limit" in err_text.lower():
                                        self._mark_key_status(key_info, "exhausted", err_text)
                                        key_failed_exhausted = True
                                        break
                                    elif "invalid" in err_text.lower() or "api key" in err_text.lower():
                                        self._mark_key_status(key_info, "invalid", err_text)
                                        key_failed_exhausted = True
                                        break

                                results = data.get("local_results", [])
                                # Cache full details for subsequent get_place_details calls
                                places_list = []
                                for item in results:
                                    place_id = item.get("place_id") or item.get("data_id") or item.get("title")
                                    item["id"] = place_id
                                    self._serpapi_details_cache[place_id] = item
                                    places_list.append(item)

                                # Record successful usage in DB
                                self._record_key_usage(key_info)

                                pagination_info = data.get("serpapi_pagination", {})
                                next_url = pagination_info.get("next")
                                has_next = bool(next_url or (len(places_list) >= 15))

                                return {
                                    "places": places_list,
                                    "nextPageToken": next_url,
                                    "has_next_page": has_next,
                                    "api_requests_used": 1,
                                    "active_key_used": key_label
                                }

                            elif resp.status_code in (401, 403):
                                err_text = f"HTTP {resp.status_code}: {resp.text}"
                                print(f"[SerpApi Auth Error] {err_text}")
                                self._mark_key_status(key_info, "exhausted" if "search" in resp.text.lower() else "invalid", err_text)
                                key_failed_exhausted = True
                                break

                            elif resp.status_code == 429:
                                print(f"[SerpApi 429 Rate Limit/Quota] Key '{key_label}' limit hit.")
                                self._mark_key_status(key_info, "exhausted", "Quota limit 429 hit.")
                                key_failed_exhausted = True
                                break

                            elif resp.status_code in (500, 502, 503, 504):
                                wait_sec = 2 ** attempt
                                print(f"[SerpApi {resp.status_code}] Retrying in {wait_sec}s...")
                                await asyncio.sleep(wait_sec)

                            else:
                                print(f"[SerpApi Error] HTTP {resp.status_code}: {resp.text}")
                                break

                    except Exception as e:
                        print(f"[SerpApi Exception] Attempt {attempt} with '{key_label}' failed: {e}")
                        await asyncio.sleep(1.0 * attempt)

                if key_failed_exhausted:
                    print(f"⚠️ [SerpApi Auto-Fallback] Beralih otomatis dari Key '{key_label}' ke API Key berikutnya...")
                    continue  # Try next key in loop

            # If all SerpApi keys failed
            print("❌ [SerpApi Alert] Semua API key SerpApi telah dicoba dan tidak ada yang berhasil.")
            return {"places": [], "nextPageToken": None, "has_next_page": False, "api_requests_used": 0, "error": "Semua API key SerpApi habis atau tidak valid."}

        # 3. Official Google Places API (New) Mode
        if self.google_api_key and self.google_api_key.strip():
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

            for attempt in range(1, 3):
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        resp = await client.post(url, headers=headers, json=body)
                        if resp.status_code == 200:
                            data = resp.json()
                            data["api_requests_used"] = 1
                            data["has_next_page"] = bool(data.get("nextPageToken"))
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

        # Fallback to empty result on complete failure
        return {"places": [], "nextPageToken": None, "has_next_page": False, "api_requests_used": 0}

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
