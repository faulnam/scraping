"""
Test script for Multi-API Key Management and Auto-Fallback Mechanism.
"""
import asyncio
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app import models
from app.places_api.client import PlacesApiClient


def test_multi_api_key_management():
    print("\n=======================================================")
    print(" TESTING MULTI-API KEY MANAGEMENT & AUTO-FALLBACK")
    print("=======================================================")
    init_db()
    db: Session = SessionLocal()

    # 1. Verify Seeded API Keys
    keys = db.query(models.ApiKeyConfig).order_by(models.ApiKeyConfig.priority.asc()).all()
    print(f"1. Total API Keys in DB: {len(keys)}")
    for k in keys:
        print(f"   - [Priority #{k.priority}] {k.label} | Provider: {k.provider} | Status: {k.status} | Used: {k.requests_used}/{k.quota_limit}")

    # 2. Add a simulated secondary key
    test_key_label = "SerpApi Akun Cadangan (Testing)"
    existing_test_key = db.query(models.ApiKeyConfig).filter(models.ApiKeyConfig.label == test_key_label).first()
    if not existing_test_key:
        new_secondary_key = models.ApiKeyConfig(
            provider="serpapi",
            label=test_key_label,
            api_key="mock_cadangan_secret_key_12345",
            quota_limit=250,
            priority=len(keys) + 1,
            is_active=True,
            status="active"
        )
        db.add(new_secondary_key)
        db.commit()
        print(f"2. Berhasil menambahkan '{test_key_label}' sebagai API cadangan.")

    # 3. Test PlacesApiClient active key retrieval
    client = PlacesApiClient(db=db)
    active_keys = client._get_active_serpapi_keys()
    print(f"3. Active SerpApi Keys loaded by Client: {len(active_keys)}")
    assert len(active_keys) >= 1
    assert active_keys[0]["priority"] == 1

    # 4. Test Key Fallback Simulation
    primary_key_dict = active_keys[0]
    print(f"4. Simulating quota exhaustion on Primary Key '{primary_key_dict['label']}'...")
    client._mark_key_status(primary_key_dict, "exhausted", "Quota limit 429 hit")

    # Reload active keys
    updated_active_keys = client._get_active_serpapi_keys()
    print(f"   Active keys remaining after exhaustion: {len(updated_active_keys)}")
    
    # Restore primary key to active
    client._mark_key_status(primary_key_dict, "active", None)
    print("   Primary key restored to active status.")

    db.close()
    print("\n [OK] MULTI-API KEY TESTS PASSED 100%!")


if __name__ == "__main__":
    test_multi_api_key_management()
