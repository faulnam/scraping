"""
Ingestion Pipeline: Orchestrates Google Places API search, 30-day cache dedup,
pandas-based data cleaning & phone normalization, lead scoring, and MySQL persistence.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import CrawlRun, Business, LeadStatus, ContactStatus
from app.places_api.client import PlacesApiClient
from app.places_api.mapper import map_place_to_business_dict, normalize_phone_number, normalize_phone_to_whatsapp
from app.leads.scoring import calculate_lead_priority


def clean_businesses_dataframe(raw_items: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Use pandas to clean, validate, and normalize business data:
    - Standardize phone numbers (stripping formatting noise)
    - Formulate valid WhatsApp direct links for Indonesian mobile numbers
    - Ensure robust has_website boolean flags
    - Clean text whitespace and null values
    """
    if not raw_items:
        return pd.DataFrame()

    df = pd.DataFrame(raw_items)

    # Clean text strings
    string_cols = ["business_name", "category", "address", "location_query", "province", "city", "website", "opening_hours", "business_status", "gmaps_url"]
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: str(x).strip() if pd.notna(x) and x is not None else None)

    # Website cleanup & has_website boolean flag
    if "website" in df.columns:
        df["has_website"] = df["website"].apply(
            lambda x: bool(x and str(x).strip() and str(x).strip().lower() != "none" and str(x).strip().lower() != "nan")
        )
    else:
        df["has_website"] = False

    # Phone normalization using pandas apply
    if "phone" in df.columns:
        df["phone"] = df["phone"].apply(normalize_phone_number)
        df["whatsapp_link"] = df["phone"].apply(normalize_phone_to_whatsapp)
    else:
        df["phone"] = None
        df["whatsapp_link"] = None

    # Rating and reviews numerical cleaning
    if "rating_avg" in df.columns:
        df["rating_avg"] = pd.to_numeric(df["rating_avg"], errors="coerce")
    else:
        df["rating_avg"] = None

    if "total_review" in df.columns:
        df["total_review"] = pd.to_numeric(df["total_review"], errors="coerce").fillna(0).astype(int)
    else:
        df["total_review"] = 0

    return df


async def run_ingest_pipeline(
    category_query: str,
    location_query: str,
    province: Optional[str] = None,
    city: Optional[str] = None,
    max_results: Optional[int] = None,  # None = Unlimited / Ambil Hingga Habis
    db: Optional[Session] = None,
    client: Optional[PlacesApiClient] = None
) -> CrawlRun:
    """
    Main ingestion execution:
    1. Records new CrawlRun session in MySQL.
    2. Searches places via PlacesApiClient iteratively (pagination looping until exhausted or max_results reached).
    3. Checks MySQL for existing place_ids:
       - If scraped < 30 days ago: Uses cached data, skips details API call (Cost Saving Rule).
       - If new / expired: Calls Place Details (Enterprise field mask).
    4. Cleans and normalizes dataset using pandas (phone numbers, WA links, nulls).
    5. Saves/updates businesses in MySQL.
    6. Computes auto-priority and creates or preserves LeadStatus records.
    7. Summarizes results and API usage on CrawlRun record.
    """
    should_close_db = False
    if db is None:
        db = SessionLocal()
        should_close_db = True

    if client is None:
        client = PlacesApiClient(db=db)

    # 1. Initialize CrawlRun record
    crawl_run = CrawlRun(
        location_query=location_query,
        category_query=category_query,
        province=province,
        city=city,
        search_method="text_search",
        started_at=datetime.utcnow(),
        status="running",
        total_businesses=0,
        api_requests_used=0
    )
    db.add(crawl_run)
    db.commit()
    db.refresh(crawl_run)

    api_requests_used = 0

    try:
        # Build search query string
        full_query = f"{category_query} {location_query}".strip()

        candidate_places: List[Dict[str, Any]] = []
        seen_place_ids = set()
        start_offset = 0
        page_num = 1
        has_more = True

        print(f"[Ingest Pipeline] Memulai pencarian '{full_query}' (Mode: {'Semua Hingga Habis' if not max_results else f'Maksimal {max_results} leads'})...")

        while has_more:
            search_result = await client.search_text(
                text_query=full_query,
                page_size=20,
                start_offset=start_offset
            )
            api_requests_used += search_result.get("api_requests_used", 0)

            new_places = search_result.get("places", [])
            if not new_places:
                print(f"[Ingest Pipeline] Tidak ada hasil lagi pada offset {start_offset}.")
                break

            added_this_page = 0
            for place in new_places:
                place_id = place.get("id")
                if place_id and place_id not in seen_place_ids:
                    seen_place_ids.add(place_id)
                    candidate_places.append(place)
                    added_this_page += 1

            print(f"[Ingest Pipeline] Halaman {page_num} (offset {start_offset}): Ditemukan {len(new_places)} listing ({added_this_page} unik baru). Total terakumulasi: {len(candidate_places)} leads.")

            # Stop conditions:
            # 1. Tidak ada hasil baru yang unik di halaman ini
            if added_this_page == 0:
                print("[Ingest Pipeline] Berhenti: Semua hasil di halaman ini sudah terdata.")
                break

            # 2. Batas max_results tercapai jika dikonfigurasi
            if max_results and len(candidate_places) >= max_results:
                print(f"[Ingest Pipeline] Target kuota tercapai: {len(candidate_places)}/{max_results} leads.")
                candidate_places = candidate_places[:max_results]
                break

            # 3. SerpApi/Google Places API tidak memiliki halaman lanjutan lagi
            if not search_result.get("has_next_page", False):
                print("[Ingest Pipeline] Mencapai halaman terakhir hasil Google Maps.")
                break

            # 4. Safety Cap (500 leads per sesi untuk mencegah infinite loop)
            if len(candidate_places) >= 500:
                print("[Ingest Pipeline] Mencapai batas pengaman maksimum 500 leads per satu sesi.")
                break

            start_offset += 20
            page_num += 1
            await asyncio.sleep(0.4)  # Small delay between page calls

        now = datetime.utcnow()
        cache_threshold = now - timedelta(days=30)

        raw_businesses_to_process: List[Dict[str, Any]] = []

        for place in candidate_places:
            place_id = place.get("id")
            if not place_id:
                continue

            # 2. Dedup check against MySQL (30-day cache rule)
            existing_biz = db.query(Business).filter(Business.google_place_id == place_id).first()

            if existing_biz and existing_biz.scraped_at and existing_biz.scraped_at >= cache_threshold:
                # Cache HIT: skip API details call to save cost
                biz_dict = {
                    "google_place_id": existing_biz.google_place_id,
                    "business_name": existing_biz.business_name,
                    "category": existing_biz.category or category_query,
                    "address": existing_biz.address,
                    "location_query": location_query,
                    "province": province or existing_biz.province,
                    "city": city or existing_biz.city,
                    "phone": existing_biz.phone,
                    "whatsapp_link": existing_biz.whatsapp_link,
                    "website": existing_biz.website,
                    "has_website": existing_biz.has_website,
                    "rating_avg": float(existing_biz.rating_avg) if existing_biz.rating_avg is not None else None,
                    "total_review": existing_biz.total_review,
                    "opening_hours": existing_biz.opening_hours,
                    "business_status": existing_biz.business_status,
                    "gmaps_url": existing_biz.gmaps_url,
                    "latitude": float(existing_biz.latitude) if existing_biz.latitude is not None else None,
                    "longitude": float(existing_biz.longitude) if existing_biz.longitude is not None else None,
                    "_is_cached": True,
                    "_existing_id": existing_biz.id
                }
            else:
                # Cache MISS / Expired: fetch Place Details
                details = await client.get_place_details(place_id=place_id)
                api_requests_used += 1

                raw_place_data = details if details else place
                biz_dict = map_place_to_business_dict(
                    raw_place_data,
                    default_location=location_query,
                    default_category=category_query,
                    province=province,
                    city=city
                )
                biz_dict["_is_cached"] = False
                biz_dict["_existing_id"] = existing_biz.id if existing_biz else None

            raw_businesses_to_process.append(biz_dict)

        # 3. Clean and normalize using pandas
        if raw_businesses_to_process:
            cleaned_df = clean_businesses_dataframe(raw_businesses_to_process)
        else:
            cleaned_df = pd.DataFrame()

        total_saved = 0

        # 4. Upsert into MySQL and Auto-sync LeadStatus
        for _, row in cleaned_df.iterrows():
            place_id = row["google_place_id"]
            is_cached = row.get("_is_cached", False)
            existing_id = row.get("_existing_id")

            if existing_id and not is_cached:
                # Update existing business record
                biz = db.query(Business).filter(Business.id == existing_id).first()
                if biz:
                    biz.business_name = row["business_name"]
                    biz.category = row["category"]
                    biz.address = row["address"]
                    biz.location_query = location_query
                    biz.province = province or biz.province
                    biz.city = city or biz.city
                    biz.phone = row["phone"]
                    biz.whatsapp_link = row["whatsapp_link"]
                    biz.website = row["website"]
                    biz.has_website = bool(row["has_website"])
                    biz.rating_avg = row["rating_avg"] if pd.notna(row["rating_avg"]) else None
                    biz.total_review = int(row["total_review"]) if pd.notna(row["total_review"]) else 0
                    biz.opening_hours = row["opening_hours"]
                    biz.business_status = row["business_status"]
                    biz.gmaps_url = row["gmaps_url"]
                    biz.latitude = row["latitude"] if pd.notna(row["latitude"]) else None
                    biz.longitude = row["longitude"] if pd.notna(row["longitude"]) else None
                    biz.scraped_at = now
            elif existing_id and is_cached:
                biz = db.query(Business).filter(Business.id == existing_id).first()
            else:
                # Insert brand new Business record
                biz = Business(
                    crawl_run_id=crawl_run.id,
                    google_place_id=place_id,
                    location_query=location_query,
                    category=row["category"],
                    business_name=row["business_name"],
                    address=row["address"],
                    province=province,
                    city=city,
                    phone=row["phone"],
                    whatsapp_link=row["whatsapp_link"],
                    website=row["website"],
                    has_website=bool(row["has_website"]),
                    rating_avg=row["rating_avg"] if pd.notna(row["rating_avg"]) else None,
                    total_review=int(row["total_review"]) if pd.notna(row["total_review"]) else 0,
                    opening_hours=row["opening_hours"],
                    business_status=row["business_status"],
                    gmaps_url=row["gmaps_url"],
                    latitude=row["latitude"] if pd.notna(row["latitude"]) else None,
                    longitude=row["longitude"] if pd.notna(row["longitude"]) else None,
                    scraped_at=now
                )
                db.add(biz)

            db.flush()

            # 5. LeadStatus 1-to-1 sync & priority calculation
            priority_score = calculate_lead_priority(
                has_website=bool(biz.has_website),
                rating_avg=float(biz.rating_avg) if biz.rating_avg is not None else None,
                total_review=int(biz.total_review) if biz.total_review is not None else 0
            )

            existing_lead_status = db.query(LeadStatus).filter(LeadStatus.business_id == biz.id).first()
            if existing_lead_status:
                # Update priority score while strictly PRESERVING sales follow-up contact_status & notes
                existing_lead_status.priority = priority_score
                existing_lead_status.updated_at = now
            else:
                # Create initial lead status
                new_lead_status = LeadStatus(
                    business_id=biz.id,
                    contact_status=ContactStatus.BELUM_DIHUBUNGI,
                    priority=priority_score,
                    updated_at=now
                )
                db.add(new_lead_status)

            total_saved += 1

        # 6. Finalize CrawlRun record
        crawl_run.status = "success"
        crawl_run.finished_at = datetime.utcnow()
        crawl_run.total_businesses = total_saved
        crawl_run.api_requests_used = api_requests_used
        db.commit()
        db.refresh(crawl_run)

    except Exception as e:
        db.rollback()
        crawl_run.status = "failed"
        crawl_run.finished_at = datetime.utcnow()
        crawl_run.api_requests_used = api_requests_used
        db.commit()
        print(f"[Ingest Pipeline Error] {e}")
        raise e
    finally:
        if should_close_db:
            db.close()

    return crawl_run
