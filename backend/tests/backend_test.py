"""COI Autopilot backend tests"""
import os, io, uuid, time
import pytest
import requests
from PIL import Image, ImageDraw

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coi-automation-1.preview.emergentagent.com').rstrip('/')
ADMIN_EMAIL = "ewg8238@gmail.com"
ADMIN_PASSWORD = "Compliance2026!"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("token")
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return data


# ---------- Auth ----------
def test_login_and_me(s, admin_token):
    r = s.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN_EMAIL


def test_login_bad_password(s):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_register_new_contractor():
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "company_name": "TEST_Co", "email": email, "phone": "+15555550100", "password": "Passw0rd!"
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["email"] == email
    assert d["token"]


# ---------- Dashboard ----------
def test_compliance_documents(s, admin_token):
    r = s.get(f"{BASE_URL}/api/compliance-documents")
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) >= 4
    statuses = {d["status"] for d in docs}
    for st in ("VALID", "EXPIRED", "NEEDS_REVIEW", "INSUFFICIENT"):
        assert st in statuses, f"missing status {st}, got {statuses}"


def test_dashboard_stats(s, admin_token):
    r = s.get(f"{BASE_URL}/api/dashboard/stats")
    assert r.status_code == 200
    c = r.json()
    assert c["total"] >= 4
    assert c["VALID"] >= 1
    assert c["EXPIRED"] >= 1


# ---------- Workflow A ----------
def test_invite_subcontractor(s, admin_token):
    payload = {"company_name": "TEST_Sub", "contact_name": "Testy", "email": f"testsub_{uuid.uuid4().hex[:6]}@example.com", "phone": "+15555550199"}
    r = s.post(f"{BASE_URL}/api/subcontractors/invite", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("upload_link") and "sub_id=" in d["upload_link"]
    assert d.get("id")
    # verify notification created
    n = s.get(f"{BASE_URL}/api/notifications")
    assert n.status_code == 200
    notes = n.json()
    assert any(x["channel"] == "sms" and x["status"] == "simulated" for x in notes)


# ---------- Workflow B: Upload with AI parsing ----------
def _make_coi_image():
    img = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 30), "CERTIFICATE OF LIABILITY INSURANCE", fill="black")
    d.text((30, 100), "Policy Number: POL-GL-TEST-12345", fill="black")
    d.text((30, 160), "General Liability Each Occurrence: $2,000,000", fill="black")
    d.text((30, 220), "Expiration Date: 2027-06-15", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_upload_ai_parsing(s, admin_token):
    subs = s.get(f"{BASE_URL}/api/subcontractors").json()
    assert subs
    sub_id = subs[0]["id"]
    gc_id = admin_token["id"]
    img = _make_coi_image()
    files = {"file": ("coi.png", img, "image/png")}
    r = requests.post(f"{BASE_URL}/api/upload", data={"sub_id": sub_id, "gc_id": gc_id}, files=files, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] in ("VALID", "EXPIRED", "NEEDS_REVIEW", "INSUFFICIENT")
    assert "parsed" in d
    # verify doc persisted
    docs = s.get(f"{BASE_URL}/api/compliance-documents").json()
    assert any(x["subcontractor_id"] == sub_id for x in docs)


# ---------- Workflow C ----------
def test_cron_expirations(s, admin_token):
    r = s.post(f"{BASE_URL}/api/cron/check-expirations")
    assert r.status_code == 200
    d = r.json()
    assert "scanned" in d and "nudged" in d


# ---------- Workflow D ----------
def test_prospecting_and_prospects(s, admin_token):
    r = s.post(f"{BASE_URL}/api/cron/prospecting")
    assert r.status_code == 200
    r2 = s.get(f"{BASE_URL}/api/prospects")
    assert r2.status_code == 200
    ps = r2.json()
    assert len(ps) >= 6
    # patch first prospect status
    pid = ps[0]["id"]
    r3 = s.patch(f"{BASE_URL}/api/prospects/{pid}", json={"outreach_status": "EMAILED"})
    assert r3.status_code == 200
    # verify
    ps2 = s.get(f"{BASE_URL}/api/prospects").json()
    assert any(p["id"] == pid and p["outreach_status"] == "EMAILED" for p in ps2)


def test_prospect_invalid_status(s, admin_token):
    ps = s.get(f"{BASE_URL}/api/prospects").json()
    pid = ps[0]["id"]
    r = s.patch(f"{BASE_URL}/api/prospects/{pid}", json={"outreach_status": "BOGUS"})
    assert r.status_code == 400


# ---------- Payments ----------
def test_stripe_checkout(s, admin_token):
    r = s.post(f"{BASE_URL}/api/payments/checkout", json={
        "lookup_key": "pro_monthly", "origin_url": BASE_URL, "user_id": admin_token["id"]
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("checkout_url", "").startswith("http")
    assert d.get("session_id")
    # status endpoint
    r2 = s.get(f"{BASE_URL}/api/payments/status/{d['session_id']}")
    assert r2.status_code == 200
    st = r2.json()
    assert st["session_id"] == d["session_id"]
    assert "payment_status" in st
