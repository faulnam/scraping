"""
Test script for Authentication System (Login, Session tokens, Protected Routes, Logout).
"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal, init_db
from app import models
from app.auth import hash_password, create_session_token, SESSION_COOKIE_NAME


def test_auth_flow():
    print("\n=======================================================")
    print(" TESTING AUTHENTICATION & LOGIN SYSTEM")
    print("=======================================================")
    init_db()
    db: Session = SessionLocal()
    client = TestClient(app, follow_redirects=False)

    # 1. Accessing protected route without cookie -> should redirect to /login
    resp = client.get("/")
    print(f"1. Unauthenticated GET / -> Status: {resp.status_code}, Location: {resp.headers.get('location')}")
    assert resp.status_code == 303
    assert "/login" in resp.headers.get("location", "")

    # 2. Login with wrong password -> should return 401 error
    resp = client.post("/login", data={"username": "admin", "password": "wrongpassword123", "next": "/"})
    print(f"2. Login with Wrong Password -> Status: {resp.status_code}")
    assert resp.status_code == 401
    assert "Username atau kata sandi tidak valid" in resp.text

    # 3. Login with correct admin credentials -> should redirect and set cookie
    resp = client.post("/login", data={"username": "admin", "password": "admin123", "next": "/"})
    print(f"3. Login with 'admin'/'admin123' -> Status: {resp.status_code}, Location: {resp.headers.get('location')}")
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/"
    assert SESSION_COOKIE_NAME in resp.cookies

    session_cookie = resp.cookies.get(SESSION_COOKIE_NAME)
    print(f"   Session Cookie Token: {session_cookie[:25]}...")

    # 4. Access protected route with session cookie -> should return 200 OK
    client.cookies.set(SESSION_COOKIE_NAME, session_cookie)
    resp = client.get("/")
    print(f"4. Authenticated GET / -> Status: {resp.status_code}")
    assert resp.status_code == 200
    assert "LeadMaps BI" in resp.text

    # 5. Access /settings/api-keys with session cookie -> should return 200 OK
    resp = client.get("/settings/api-keys")
    print(f"5. Authenticated GET /settings/api-keys -> Status: {resp.status_code}")
    assert resp.status_code == 200
    assert "Manajemen API Key" in resp.text

    # 6. Logout -> should clear cookie and redirect to /login
    resp = client.get("/logout")
    print(f"6. GET /logout -> Status: {resp.status_code}, Location: {resp.headers.get('location')}")
    assert resp.status_code == 303
    assert "/login" in resp.headers.get("location", "")

    db.close()
    print("\n [OK] AUTHENTICATION & LOGIN TESTS PASSED 100%!")


if __name__ == "__main__":
    test_auth_flow()
