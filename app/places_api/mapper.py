"""
Mapper to normalize Google Places API (New) & SerpApi JSON responses into the LeadMaps internal schema.
"""
from typing import Dict, Any, Optional
import re


def normalize_phone_number(phone: Optional[str]) -> Optional[str]:
    """
    Standardize Indonesian phone numbers to a clean format.
    E.g. '+62 812-3456-789' -> '08123456789' or '(022) 2012345' -> '0222012345'
    """
    if not phone:
        return None
    # Strip spaces, dashes, parentheses
    cleaned = re.sub(r"[^\d+]", "", str(phone).strip())
    if cleaned.startswith("+62"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("62") and len(cleaned) > 9:
        cleaned = "0" + cleaned[2:]
    return cleaned if len(cleaned) >= 6 else str(phone).strip()


def normalize_phone_to_whatsapp(phone: Optional[str]) -> Optional[str]:
    """
    Format Indonesian phone numbers to a wa.me link.
    Example: '08123456789' or '+62 812-3456-789' -> 'https://wa.me/628123456789'
    Landlines (e.g. 022...) return None as WhatsApp requires mobile numbers.
    """
    if not phone:
        return None
    digits = re.sub(r"[^\d+]", "", str(phone).strip())
    if digits.startswith("+"):
        digits = digits[1:]
    elif digits.startswith("08"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits

    # Indonesian mobile numbers usually start with 628 and are 10-14 digits long
    if digits.startswith("628") and len(digits) >= 10:
        return f"https://wa.me/{digits}"
    return None


def map_place_to_business_dict(
    place_data: Dict[str, Any],
    default_location: str = "",
    default_category: str = "",
    province: Optional[str] = None,
    city: Optional[str] = None
) -> Dict[str, Any]:
    """
    Map Google Places (New) or SerpApi place object to internal Business dictionary.
    """
    # 1. Name handling (Google: displayName.text / SerpApi: title)
    display_name = place_data.get("displayName") or place_data.get("title")
    if isinstance(display_name, dict):
        name = display_name.get("text", "")
    elif isinstance(display_name, str):
        name = display_name
    else:
        name = "Usaha Tanpa Nama"

    # 2. Place ID handling (Google: id / SerpApi: place_id or data_id)
    place_id = place_data.get("id") or place_data.get("place_id") or place_data.get("data_id") or ""

    # 3. Category handling
    primary_type = place_data.get("primaryType") or place_data.get("type") or default_category
    if not primary_type and place_data.get("types"):
        primary_type = place_data["types"][0]

    category_str = str(primary_type).replace("_", " ").title() if primary_type else default_category

    # 4. Website & has_website flag
    website = place_data.get("websiteUri") or place_data.get("website") or ""
    website_clean = str(website).strip() if website else ""
    if website_clean.lower() in ("none", "null", "nan"):
        website_clean = ""
    has_website = bool(website_clean)

    # 5. Location coordinates (Google: location / SerpApi: gps_coordinates)
    loc = place_data.get("location") or place_data.get("gps_coordinates") or {}
    latitude = loc.get("latitude") if loc else None
    longitude = loc.get("longitude") if loc else None

    # 6. Address
    address = place_data.get("formattedAddress") or place_data.get("address") or ""

    # 7. Opening hours
    opening_hours_str = None
    if place_data.get("regularOpeningHours"):
        op_h = place_data["regularOpeningHours"]
        if isinstance(op_h, dict) and op_h.get("weekdayDescriptions"):
            opening_hours_str = "; ".join(op_h.get("weekdayDescriptions", []))
    elif place_data.get("operating_hours"):
        op_h = place_data["operating_hours"]
        if isinstance(op_h, dict):
            opening_hours_str = "; ".join([f"{k.capitalize()}: {v}" for k, v in op_h.items()])
    elif place_data.get("hours"):
        opening_hours_str = str(place_data["hours"])

    # 8. Phone & WA Link
    raw_phone = (
        place_data.get("nationalPhoneNumber") or 
        place_data.get("internationalPhoneNumber") or 
        place_data.get("phone")
    )
    clean_phone = normalize_phone_number(raw_phone)
    whatsapp_link = normalize_phone_to_whatsapp(raw_phone)

    # 9. Rating & Total Review
    rating_val = place_data.get("rating")
    try:
        rating_avg = float(rating_val) if rating_val is not None else None
    except (ValueError, TypeError):
        rating_avg = None

    review_val = place_data.get("userRatingCount") or place_data.get("reviews") or 0
    try:
        total_review = int(review_val)
    except (ValueError, TypeError):
        total_review = 0

    # 10. Google Maps URL
    gmaps_url = place_data.get("googleMapsUri") or place_data.get("place_id_search")
    if not gmaps_url and place_id:
        gmaps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    return {
        "google_place_id": place_id,
        "business_name": name,
        "category": category_str,
        "address": address,
        "location_query": default_location,
        "province": province,
        "city": city,
        "phone": clean_phone,
        "whatsapp_link": whatsapp_link,
        "website": website_clean if website_clean else None,
        "has_website": has_website,
        "rating_avg": rating_avg,
        "total_review": total_review,
        "opening_hours": opening_hours_str,
        "business_status": place_data.get("businessStatus", "OPERATIONAL"),
        "gmaps_url": gmaps_url,
        "latitude": latitude,
        "longitude": longitude,
    }
