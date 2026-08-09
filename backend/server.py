
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import openai
import os, logging, uuid, base64, json, asyncio, secrets, re
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from typing import List, Optional, Annotated, Any

import bcrypt, jwt, httpx, stripe, fitz
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, UploadFile, File, Form
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr, BeforeValidator, ConfigDict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
#from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
import csv, io
from fastapi.responses import Response as FileResponse
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coi")

mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db_name = os.getenv('DB_NAME', 'subcontractor_compliance')
db = client[db_name]

# Server & Auth Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
JWT_SECRET = os.getenv("JWT_SECRET", "default_dev_secret_key_change_in_prod")
JWT_ALG = "HS256"

# Email Configuration (Falls back to Resend or custom provider)
EMAIL_BASE_URL = os.getenv("EMAIL_BASE_URL", "https://api.resend.com")
EMAIL_KEY = os.getenv("RESEND_API_KEY", os.getenv("EMERGENT_EMAIL_KEY", "dummy_email_key"))
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Automated Micro SaaS")

# LLM Configuration
EMERGENT_LLM_KEY = os.getenv("OPENAI_API_KEY", os.getenv("EMERGENT_LLM_KEY", "dummy_llm_key"))

# Stripe Integration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_emergent")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Twilio (SMS) Integration
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_PHONE_NUMBER", "")

# Prospecting & Marketing Integrations
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY", "")
INSTANTLY_CAMPAIGN_ID = os.getenv("INSTANTLY_CAMPAIGN_ID", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")

app = FastAPI()
api = APIRouter(prefix="/api")

PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- Auth helpers ----------
def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


def create_access_token(uid: str, email: str) -> str:
    return jwt.encode({"sub": uid, "email": email, "type": "access",
                       "exp": datetime.now(timezone.utc) + timedelta(days=7)}, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        h = request.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            token = h[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user = await db.contractors.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(401, "User not found")
        user["id"] = str(user.pop("_id"))
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def set_auth_cookie(resp: Response, token: str):
    resp.set_cookie("access_token", token, httponly=True, secure=True,
                    samesite="none", max_age=604800, path="/")


# ---------- Models ----------
class RegisterReq(BaseModel):
    company_name: str
    email: EmailStr
    phone: str = ""
    password: str


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class InviteReq(BaseModel):
    company_name: str
    contact_name: str
    email: EmailStr
    phone: str = ""


class CheckoutReq(BaseModel):
    lookup_key: str = "pro_monthly"
    origin_url: str
    user_id: Optional[str] = None


class SettingsReq(BaseModel):
    brand_color: Optional[str] = None
    escalation_threshold: Optional[int] = None
    report_recipients: Optional[List[str]] = None
    report_day: Optional[int] = None
    report_hour: Optional[int] = None
    timezone: Optional[str] = None
    slug: Optional[str] = None
    onboarded: Optional[bool] = None


class ForgotReq(BaseModel):
    email: EmailStr


class ResetReq(BaseModel):
    token: str
    password: str


# ---------- Notifications (email via Resend, SMS simulated) ----------
async def send_email(to: str, subject: str, html: str):
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                             headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        r.raise_for_status()
        ok = True
    except Exception as e:
        logger.error(f"email fail: {e}")
        ok = False
    await db.notifications.insert_one({"channel": "email", "to": to, "subject": subject,
                                       "body": html, "status": "sent" if ok else "failed", "created_at": now_iso()})
    return ok


async def send_sms(to: str, body: str):
    # Real SMS via Twilio when keys are configured; otherwise SIMULATED (logged to DB).
    status = "simulated"
    if TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM and to and to not in ("unknown", ""):
        try:
            from twilio.rest import Client as TwilioClient

            def _send():
                TwilioClient(TWILIO_SID, TWILIO_TOKEN).messages.create(to=to, from_=TWILIO_FROM, body=body)
            await asyncio.to_thread(_send)
            status = "sent"
        except Exception as e:
            logger.error(f"twilio fail: {e}")
            status = "failed"
    else:
        logger.info(f"[SIMULATED SMS] to {to}: {body}")
    await db.notifications.insert_one({"channel": "sms", "to": to, "subject": "SMS",
                                       "body": body, "status": status, "created_at": now_iso()})


def new_upload_token():
    return secrets.token_urlsafe(24)


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "gc"


async def unique_slug(base, exclude_id=None):
    slug, i = base, 1
    while True:
        existing = await db.contractors.find_one({"slug": slug})
        if not existing or (exclude_id and str(existing["_id"]) == exclude_id):
            return slug
        i += 1
        slug = f"{base}-{i}"


def token_expiry():
    return (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()


def upload_link(slug, sub_id, gc_id, token):
    return f"{FRONTEND_URL}/u/{slug}?sub_id={sub_id}&gc_id={gc_id}&token={token}"


# ---------- AUTH ROUTES ----------
@api.post("/auth/register")
async def register(body: RegisterReq, response: Response):
    email = body.email.lower()
    if await db.contractors.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    doc = {"company_name": body.company_name, "email": email, "phone": body.phone,
           "password_hash": hash_password(body.password), "stripe_customer_id": None,
           "subscription_status": "trialing", "role": "contractor", "created_at": now_iso(),
           "slug": await unique_slug(slugify(body.company_name)), "timezone": "UTC", "onboarded": False}
    res = await db.contractors.insert_one(doc)
    uid = str(res.inserted_id)
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    return {"id": uid, "company_name": body.company_name, "email": email,
            "subscription_status": "trialing", "onboarded": False, "token": token}


@api.post("/auth/login")
async def login(body: LoginReq, response: Response):
    email = body.email.lower()
    user = await db.contractors.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(401, "Invalid email or password")
    uid = str(user["_id"])
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    return {"id": uid, "company_name": user["company_name"], "email": email,
            "subscription_status": user.get("subscription_status", "trialing"), "token": token}


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotReq):
    email = body.email.lower()
    user = await db.contractors.find_one({"email": email})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": str(user["_id"]),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "used": False, "created_at": now_iso()})
        link = f"{FRONTEND_URL}/reset-password?token={token}"
        await send_email(email, "Reset your COI Autopilot password",
            f"<div style='font-family:Arial'><h2>Password reset</h2>"
            f"<p>We received a request to reset your password. This link expires in 1 hour.</p>"
            f"<p><a href='{link}' style='background:#000;color:#fff;padding:10px 20px;text-decoration:none'>Reset password</a></p>"
            f"<p>If you didn't request this, you can safely ignore this email.</p></div>")
    return {"ok": True, "message": "If an account with that email exists, a reset link has been sent."}


@api.post("/auth/reset-password")
async def reset_password(body: ResetReq):
    rec = await db.password_reset_tokens.find_one({"token": body.token})
    if not rec or rec.get("used"):
        raise HTTPException(400, "This reset link is invalid or has already been used.")
    exp = rec["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(400, "This reset link has expired. Please request a new one.")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    await db.contractors.update_one({"_id": ObjectId(rec["user_id"])}, {"$set": {"password_hash": hash_password(body.password)}})
    await db.password_reset_tokens.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
    return {"ok": True}


# ---------- WORKFLOW A: Invite Subcontractor ----------
@api.post("/subcontractors/invite")
async def invite_subcontractor(body: InviteReq, user: dict = Depends(get_current_user)):
    gc_id = user["id"]
    token = new_upload_token()
    doc = {"contractor_id": gc_id, "company_name": body.company_name, "contact_name": body.contact_name,
           "email": body.email.lower(), "phone": body.phone, "created_at": now_iso(),
           "upload_token": token, "upload_token_expires": token_expiry(), "upload_token_used": False}
    res = await db.subcontractors.insert_one(doc)
    sub_id = str(res.inserted_id)
    doc.pop("_id", None)
    link = upload_link(user.get("slug", "portal"), sub_id, gc_id, token)
    html = f"""<table width="100%"><tr><td style="font-family:Arial;padding:24px">
    <h2>COI Upload Request from {user['company_name']}</h2>
    <p>Hi {body.contact_name}, please upload your current Certificate of Insurance (COI).</p>
    <p><a href="{link}" style="background:#000;color:#fff;padding:12px 24px;text-decoration:none">Upload Your COI</a></p>
    <p>Or paste this link: {link}</p></td></tr></table>"""
    await send_email(body.email, f"Action needed: Upload your COI for {user['company_name']}", html)
    await send_sms(body.phone or "unknown", f"{user['company_name']} requests your COI. Upload here: {link}")
    doc.pop("_id", None)
    return {"id": sub_id, "upload_link": link, **doc}


@api.get("/subcontractors")
async def list_subcontractors(user: dict = Depends(get_current_user)):
    subs = await db.subcontractors.find({"contractor_id": user["id"]}).sort("created_at", -1).to_list(500)
    for s in subs:
        s["id"] = str(s.pop("_id"))
    return subs


# ---------- WORKFLOW B: AI Document Parsing ----------
import json
import os
import openai

# Initialize the Async OpenAI client using OPENAI_API_KEY from backend/.env
openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def parse_coi_with_ai(image_b64: str) -> dict:
    prompt = (
        "Extract these fields from this Certificate of Insurance and return ONLY JSON: "
        '{"gl_policy_number": string|null, "gl_expiration_date": "YYYY-MM-DD"|null, '
        '"general_liability_limit": number|null (each-occurrence general liability limit in USD as a plain number)}. '
        "If a field is not found, use null."
    )
    
    # Check if the b64 string already includes the data prefix header; format as data URL
    image_url = image_b64 if image_b64.startswith("data:") else f"data:image/png;base64,{image_b64}"

    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an insurance document parser. Extract data from Certificate of Insurance (COI / ACORD) documents. Respond ONLY with strict JSON."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ],
        response_format={"type": "json_object"}
    )
    
    # Guard against a missing/null content field in the LLM response
    content = response.choices[0].message.content or "{}"
    text = content.strip()
    try:
        return json.loads(text)
    except Exception:
        # If parsing fails, return an empty dict to trigger review flows upstream
        return {}


def validate_coi(parsed: dict) -> tuple:
    status, reason = "VALID", ""
    exp = parsed.get("gl_expiration_date")
    limit = parsed.get("general_liability_limit")
    if exp:
        try:
            if date.fromisoformat(str(exp)[:10]) < date.today():
                return "EXPIRED", "General liability policy has expired"
        except Exception:
            pass
    if limit is not None:
        try:
            if float(limit) < 1_000_000:
                return "INSUFFICIENT", "Liability limit under $1M threshold"
        except Exception:
            pass
    if not exp or limit is None:
        return "NEEDS_REVIEW", "Could not extract all required fields; manual review needed"
    return status, reason


@api.post("/upload")
async def upload_coi(sub_id: str = Form(...), gc_id: str = Form(...), token: str = Form(""), file: UploadFile = File(...)):
    sub = await db.subcontractors.find_one({"_id": ObjectId(sub_id)}) if ObjectId.is_valid(sub_id) else None
    if not sub or not sub.get("upload_token") or sub.get("upload_token") != token:
        raise HTTPException(403, "Invalid upload link. Please use the secure link sent to you.")
    if sub.get("upload_token_expires") and sub["upload_token_expires"] < now_iso():
        raise HTTPException(403, "This upload link has expired. Please request a new one.")
    if sub.get("upload_token_used"):
        raise HTTPException(403, "This upload link has already been used. Please request a new one.")
    raw = await file.read()
    ct = (file.content_type or "").lower()
    fname = file.filename or "coi"
    if "pdf" in ct or fname.lower().endswith(".pdf"):
        pdf = fitz.open(stream=raw, filetype="pdf")
        pix = pdf[0].get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
    else:
        img_bytes = raw
    b64 = base64.b64encode(img_bytes).decode()

    parsed, err = {}, None
    try:
        parsed = await parse_coi_with_ai(b64)
    except Exception as e:
        logger.error(f"AI parse fail: {e}")
        err = str(e)

    if err:
        status, reason = "NEEDS_REVIEW", "AI parsing failed; manual review required"
    else:
        status, reason = validate_coi(parsed)

    updir = ROOT_DIR / "uploads"
    updir.mkdir(exist_ok=True)
    saved = updir / f"{sub_id}_{uuid.uuid4().hex[:8]}_{fname}"
    saved.write_bytes(raw)

    doc = {"subcontractor_id": sub_id, "contractor_id": gc_id,
           "gl_policy_number": parsed.get("gl_policy_number"),
           "gl_expiration_date": parsed.get("gl_expiration_date"),
           "general_liability_limit": parsed.get("general_liability_limit"),
           "status": status, "review_reason": reason,
           "document_url": f"/api/uploads/{saved.name}", "created_at": now_iso()}
    await db.compliance_documents.update_one({"subcontractor_id": sub_id}, {"$set": doc}, upsert=True)
    sub_update = {"upload_token_used": True}
    if status == "VALID":
        # assign keys individually to avoid type-checker confusion over dict.update signatures
        sub_update["last_nudged_at"] = False
        sub_update["nudge_count"] = False
        sub_update["escalated"] = False
    await db.subcontractors.update_one({"_id": ObjectId(sub_id)}, {"$set": sub_update})

    sub = await db.subcontractors.find_one({"_id": ObjectId(sub_id)}) if ObjectId.is_valid(sub_id) else None
    gc = await db.contractors.find_one({"_id": ObjectId(gc_id)}) if ObjectId.is_valid(gc_id) else None
    if gc:
        subname = sub["company_name"] if sub else "A subcontractor"
        html = (f"<div style='font-family:Arial'><h2>COI Processed: {status}</h2>"
                f"<p>{subname} uploaded a COI. Status: <b>{status}</b>. {reason}</p></div>")
        await send_email(gc["email"], f"COI processed ({status}) for {subname}", html)
    return {"status": status, "review_reason": reason, "parsed": parsed}


# ---------- Dashboard: compliance documents ----------
async def enrich_docs(docs):
    out = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        sub = None
        if ObjectId.is_valid(d.get("subcontractor_id", "")):
            sub = await db.subcontractors.find_one({"_id": ObjectId(d["subcontractor_id"])})
        d["subcontractor_name"] = sub["company_name"] if sub else "Unknown"
        d["contact_name"] = sub["contact_name"] if sub else ""
        d["contact_email"] = sub["email"] if sub else ""
        out.append(d)
    return out


@api.get("/compliance-documents")
async def compliance_docs(user: dict = Depends(get_current_user)):
    docs = await db.compliance_documents.find({"contractor_id": user["id"]}).sort("created_at", -1).to_list(1000)
    return await enrich_docs(docs)


async def compliance_report_rows(contractor_id):
    docs = await db.compliance_documents.find({"contractor_id": contractor_id}).sort("created_at", -1).to_list(1000)
    rows = await enrich_docs(docs)
    head = ["Subcontractor", "Contact", "Email", "Policy #", "GL Limit", "Expiration", "Status", "Notes"]
    data = [[r["subcontractor_name"], r.get("contact_name", ""), r.get("contact_email", ""),
             r.get("gl_policy_number") or "",
             f"${int(r['general_liability_limit']):,}" if r.get("general_liability_limit") else "",
             r.get("gl_expiration_date") or "", r["status"], r.get("review_reason") or ""] for r in rows]
    return head, data, rows


def _hexcolor(v, fallback="#000000"):
    try:
        return colors.HexColor(v)
    except Exception:
        return colors.HexColor(fallback)


def build_compliance_pdf(company_name, head, data, rows, brand_color="#000000", logo_url=None) -> bytes:
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=landscape(letter), title="COI Compliance Report")
    styles = getSampleStyleSheet()
    elems = []
    if logo_url:
        lp = ROOT_DIR / logo_url.lstrip("/").replace("api/uploads/", "uploads/")
        if lp.exists():
            try:
                elems.append(RLImage(str(lp), width=150, height=50, kind="proportional", hAlign="LEFT"))
                elems.append(Spacer(1, 8))
            except Exception:
                pass
    elems.append(Paragraph(f"<font color='{brand_color}'>COI Compliance Report — {company_name}</font>", styles["Title"]))
    elems.append(Paragraph(datetime.now(timezone.utc).strftime("Generated %Y-%m-%d %H:%M UTC"), styles["Normal"]))
    elems.append(Spacer(1, 12))
    cmap = {"VALID": colors.HexColor("#02C039"), "EXPIRED": colors.HexColor("#FF3B30"),
            "NEEDS_REVIEW": colors.HexColor("#FF9500"), "INSUFFICIENT": colors.HexColor("#FF9500")}
    table = Table([head] + (data or [["No documents yet", "", "", "", "", "", "", ""]]), repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), _hexcolor(brand_color)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")])]
    for i, r in enumerate(rows, start=1):
        c = cmap.get(r["status"])
        if c:
            style.append(("TEXTCOLOR", (6, i), (6, i), c))
    table.setStyle(TableStyle(style))
    elems.append(table)
    pdf.build(elems)
    return buf.getvalue()


@api.get("/compliance-documents/export")
async def export_compliance(format: str = "csv", user: dict = Depends(get_current_user)):
    head, data, rows = await compliance_report_rows(user["id"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    if format == "pdf":
        return FileResponse(content=build_compliance_pdf(user["company_name"], head, data, rows,
                            user.get("brand_color") or "#000000", user.get("logo_url")),
                            media_type="application/pdf",
                            headers={"Content-Disposition": f"attachment; filename=coi_report_{stamp}.pdf"})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    w.writerows(data)
    return FileResponse(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=coi_report_{stamp}.csv"})


async def send_report_email(gc):
    cid = gc.get("id") or str(gc.get("_id"))
    email = gc["email"]
    company_name = gc.get("company_name", "Your Company")
    brand = gc.get("brand_color") or "#000000"
    logo = gc.get("logo_url")
    recipients = list(dict.fromkeys([email] + [r for r in (gc.get("report_recipients") or []) if r]))
    head, data, rows = await compliance_report_rows(cid)
    counts = {"VALID": 0, "EXPIRED": 0, "NEEDS_REVIEW": 0, "INSUFFICIENT": 0}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    pdf_bytes = build_compliance_pdf(company_name, head, data, rows, brand, logo)
    rdir = ROOT_DIR / "uploads" / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    fname = f"{cid}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    (rdir / fname).write_bytes(pdf_bytes)
    pdf_url = f"{FRONTEND_URL}/api/uploads/reports/{fname}"
    cc = {"VALID": "#02C039", "EXPIRED": "#FF3B30", "NEEDS_REVIEW": "#FF9500", "INSUFFICIENT": "#FF9500"}
    logo_html = f"<img src='{FRONTEND_URL}{logo}' alt='logo' style='max-height:48px;margin-bottom:8px'/><br/>" if logo else ""
    body_rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #eee'>{r['subcontractor_name']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{r.get('gl_expiration_date') or '—'}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;color:{cc.get(r['status'],'#111')};font-weight:600'>{r['status']}</td></tr>"
        for r in rows) or "<tr><td colspan='3' style='padding:8px'>No subcontractors yet.</td></tr>"
    html = (f"<div style='font-family:Arial;max-width:640px'>{logo_html}"
            f"<h2 style='margin-bottom:4px;color:{brand}'>Weekly COI Compliance Summary</h2>"
            f"<p style='color:#666;margin-top:0'>{company_name} — {datetime.now(timezone.utc).strftime('%B %d, %Y')}</p>"
            f"<p><b style='color:#02C039'>{counts['VALID']} Valid</b> &nbsp;·&nbsp; "
            f"<b style='color:#FF3B30'>{counts['EXPIRED']} Expired</b> &nbsp;·&nbsp; "
            f"<b style='color:#FF9500'>{counts['NEEDS_REVIEW']} Needs review</b> &nbsp;·&nbsp; "
            f"<b style='color:#FF9500'>{counts['INSUFFICIENT']} Insufficient</b></p>"
            f"<table style='border-collapse:collapse;width:100%;font-size:14px'>"
            f"<tr><th align='left' style='padding:8px;border-bottom:2px solid #000'>Subcontractor</th>"
            f"<th align='left' style='padding:8px;border-bottom:2px solid #000'>Expiration</th>"
            f"<th align='left' style='padding:8px;border-bottom:2px solid #000'>Status</th></tr>{body_rows}</table>"
            f"<p style='margin-top:20px'><a href='{pdf_url}' style='background:{brand};color:#fff;padding:10px 20px;text-decoration:none'>Download full PDF report</a></p></div>")
    for to in recipients:
        await send_email(to, f"Weekly COI Compliance Summary — {company_name}", html)


async def run_weekly_reports():
    sent = 0
    for gc in await db.contractors.find({}).to_list(1000):
        await send_report_email(gc)
        sent += 1
    return {"reports_sent": sent}


async def run_scheduled_reports():
    now = datetime.now(timezone.utc)
    sent = 0
    for gc in await db.contractors.find({}).to_list(1000):
        try:
            tz = ZoneInfo(gc.get("timezone") or "UTC")
        except Exception:
            tz = ZoneInfo("UTC")
        local = now.astimezone(tz)
        today = local.date().isoformat()
        if local.weekday() == gc.get("report_day", 0) and local.hour == gc.get("report_hour", 7) and gc.get("last_report_sent") != today:
            await send_report_email(gc)
            await db.contractors.update_one({"_id": gc["_id"]}, {"$set": {"last_report_sent": today}})
            sent += 1
    return {"reports_sent": sent}


@api.post("/cron/weekly-reports")
async def cron_weekly_reports(user: dict = Depends(get_current_user)):
    return await run_weekly_reports()


@api.post("/reports/email-me")
async def email_me_report(user: dict = Depends(get_current_user)):
    gc = await db.contractors.find_one({"_id": ObjectId(user["id"])})
    await send_report_email(gc)
    return {"sent": True, "to": user["email"]}


@api.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    return {"company_name": user["company_name"], "brand_color": user.get("brand_color", "#111111"),
            "logo_url": user.get("logo_url"), "escalation_threshold": user.get("escalation_threshold", 3),
            "report_recipients": user.get("report_recipients", []),
            "report_day": user.get("report_day", 0), "report_hour": user.get("report_hour", 7),
            "timezone": user.get("timezone", "UTC"), "slug": user.get("slug"),
            "onboarded": user.get("onboarded", True)}


@api.put("/settings")
async def update_settings(body: SettingsReq, user: dict = Depends(get_current_user)):
    upd = {}
    if body.brand_color is not None:
        upd["brand_color"] = body.brand_color
    if body.escalation_threshold is not None:
        upd["escalation_threshold"] = int(body.escalation_threshold)
    if body.report_recipients is not None:
        upd["report_recipients"] = [e.strip() for e in body.report_recipients if e and e.strip()]
    if body.report_day is not None:
        upd["report_day"] = max(0, min(6, int(body.report_day)))
    if body.report_hour is not None:
        upd["report_hour"] = max(0, min(23, int(body.report_hour)))
    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
            upd["timezone"] = body.timezone
        except Exception:
            raise HTTPException(400, "Invalid timezone")
    if body.slug is not None:
        upd["slug"] = await unique_slug(slugify(body.slug), user["id"])
    if body.onboarded is not None:
        upd["onboarded"] = bool(body.onboarded)
    if upd:
        await db.contractors.update_one({"_id": ObjectId(user["id"])}, {"$set": upd})
    return {"ok": True, **upd}


@api.get("/public/slug/{slug}")
async def public_by_slug(slug: str):
    gc = await db.contractors.find_one({"slug": slug})
    if not gc:
        raise HTTPException(404, "Not found")
    return {"id": str(gc["_id"]), "company_name": gc.get("company_name"),
            "logo_url": gc.get("logo_url"), "brand_color": gc.get("brand_color", "#111111")}


@api.get("/public/contractor/{gc_id}")
async def public_contractor(gc_id: str):
    gc = await db.contractors.find_one({"_id": ObjectId(gc_id)}) if ObjectId.is_valid(gc_id) else None
    if not gc:
        raise HTTPException(404, "Not found")
    return {"company_name": gc.get("company_name"), "logo_url": gc.get("logo_url"),
            "brand_color": gc.get("brand_color", "#111111")}


@api.post("/settings/logo")
async def upload_logo(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    raw = await file.read()
    ldir = ROOT_DIR / "uploads" / "logos"
    ldir.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(file.filename or "logo.png")[1] or ".png"
    fname = f"{user['id']}{ext}"
    (ldir / fname).write_bytes(raw)
    url = f"/api/uploads/logos/{fname}"
    await db.contractors.update_one({"_id": ObjectId(user["id"])}, {"$set": {"logo_url": url}})
    return {"logo_url": url}


@api.get("/dashboard/stats")
async def stats(user: dict = Depends(get_current_user)):
    docs = await db.compliance_documents.find({"contractor_id": user["id"]}).to_list(1000)
    counts = {"total": len(docs), "VALID": 0, "EXPIRED": 0, "NEEDS_REVIEW": 0, "INSUFFICIENT": 0}
    for d in docs:
        counts[d.get("status", "NEEDS_REVIEW")] = counts.get(d.get("status", "NEEDS_REVIEW"), 0) + 1
    return counts


# ---------- WORKFLOW C: Daily expiration cron ----------
async def run_expiration_check():
    soon = (date.today() + timedelta(days=30)).isoformat()
    today = date.today().isoformat()
    docs = await db.compliance_documents.find({"gl_expiration_date": {"$lte": soon, "$ne": None}}).to_list(2000)
    nudged, escalated = 0, 0
    for d in docs:
        exp = str(d.get("gl_expiration_date"))[:10]
        new_status = "EXPIRED" if exp < today else "NEEDS_REVIEW"
        if d.get("status") != new_status:
            await db.compliance_documents.update_one({"_id": d["_id"]}, {"$set": {"status": new_status,
                "review_reason": "Policy expired" if new_status == "EXPIRED" else "Expiring within 30 days"}})
        sub = await db.subcontractors.find_one({"_id": ObjectId(d["subcontractor_id"])}) if ObjectId.is_valid(d.get("subcontractor_id", "")) else None
        if sub:
            last = sub.get("last_nudged_at")
            if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)) < timedelta(days=3):
                continue
            gc = await db.contractors.find_one({"_id": ObjectId(sub["contractor_id"])}) if ObjectId.is_valid(sub.get("contractor_id", "")) else None
            n = sub.get("nudge_count", 0) + 1
            tok = new_upload_token()
            await db.subcontractors.update_one({"_id": sub["_id"]}, {"$set": {
                "upload_token": tok, "upload_token_expires": token_expiry(), "upload_token_used": False,
                "last_nudged_at": now_iso(), "nudge_count": n}})
            link = upload_link((gc or {}).get("slug", "portal"), str(sub["_id"]), sub["contractor_id"], tok)
            await send_email(sub["email"], f"Reminder #{n}: your COI is expiring — please renew",
                             f"<p>Hi {sub['contact_name']}, your COI expires on {exp}. <a href='{link}'>Upload updated paperwork here</a>.</p>")
            await send_sms(sub.get("phone", ""), f"Reminder #{n}: your COI expires {exp}. Upload updated paperwork: {link}")
            nudged += 1
            threshold = (gc or {}).get("escalation_threshold", 3)
            if gc and n >= threshold and not sub.get("escalated"):
                await send_email(gc["email"], f"Action needed: {sub['company_name']} is ignoring COI reminders",
                                 f"<div style='font-family:Arial'><h2>Compliance escalation</h2>"
                                 f"<p><b>{sub['company_name']}</b> ({sub['contact_name']}, {sub['email']}, {sub.get('phone','')}) "
                                 f"has received {n} COI renewal reminders without uploading updated paperwork. "
                                 f"Their policy expires {exp}. Please follow up directly.</p></div>")
                await db.subcontractors.update_one({"_id": sub["_id"]}, {"$set": {"escalated": True}})
                escalated += 1
    return {"scanned": len(docs), "nudged": nudged, "escalated": escalated}


@api.post("/cron/check-expirations")
async def cron_expirations(user: dict = Depends(get_current_user)):
    return await run_expiration_check()


# ---------- WORKFLOW D: Prospecting & Outreach (mocked Apollo + Instantly) ----------
MOCK_LEADS = [
    {"company_name": "Summit Commercial Builders", "contact_name": "Mark Reyes", "email": "mark@summitcb.com", "phone": "+13105550111", "title": "VP of Construction"},
    {"company_name": "Ironclad General Contracting", "contact_name": "Dana White", "email": "dana@ironcladgc.com", "phone": "+12145550122", "title": "Owner"},
    {"company_name": "Meridian Build Group", "contact_name": "Priya Shah", "email": "priya@meridianbuild.com", "phone": "+16465550133", "title": "Project Manager"},
    {"company_name": "Cornerstone Structures", "contact_name": "Luis Gomez", "email": "luis@cornerstonestruct.com", "phone": "+13235550144", "title": "Owner"},
    {"company_name": "Vanguard Construction Partners", "contact_name": "Emily Chen", "email": "emily@vanguardcp.com", "phone": "+17185550155", "title": "VP of Construction"},
    {"company_name": "Apex Site Developers", "contact_name": "Robert King", "email": "robert@apexsite.com", "phone": "+14155550166", "title": "Project Manager"},
]
SEQUENCE = [
    {"day": 1, "subject": "Still chasing subs for COIs?", "body": "Manual COI tracking risks site fines. We automate it end-to-end."},
    {"day": 4, "subject": "How GCs cut COI admin 90%", "body": "AI parses every COI + 30-day background SMS/email drips keep subs compliant."},
    {"day": 8, "subject": "Start your 14-day trial", "body": "See it live and start your Pro trial ($149/mo)."},
]


async def instantly_add_leads(leads):
    if not (INSTANTLY_API_KEY and INSTANTLY_CAMPAIGN_ID and leads):
        return
    async with httpx.AsyncClient(timeout=40) as c:
        for ld in leads:
            try:
                await c.post("https://api.instantly.ai/api/v2/leads",
                             headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}", "Content-Type": "application/json"},
                             json={"campaign": INSTANTLY_CAMPAIGN_ID, "email": ld["email"],
                                   "first_name": ld.get("first_name"), "last_name": ld.get("last_name"),
                                   "company_name": ld.get("company_name"),
                                   "skip_if_in_campaign": True, "skip_if_in_workspace": True})
            except Exception as e:
                logger.error(f"instantly add fail: {e}")


async def apollo_instantly_prospecting():
    """Live: Apollo people search (GC titles, commercial construction, 10-200) -> dedupe -> Instantly campaign."""
    headers = {"x-api-key": APOLLO_API_KEY, "Content-Type": "application/json"}
    body = {"page": 1, "per_page": 25,
            "person_titles[]": ["Owner", "VP of Construction", "Project Manager"],
            "q_organization_keyword_tags[]": ["commercial construction"],
            "organization_num_employees_ranges[]": ["10,200"]}
    added, pushed = 0, []
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post("https://api.apollo.io/api/v1/mixed_people/api_search", headers=headers, json=body)
        r.raise_for_status()
        people = r.json().get("people", [])
        for p in people:
            email = (p.get("email") or "").strip().lower()
            org = (p.get("organization") or {}).get("name") or p.get("organization_name") or "Unknown Co"
            name = p.get("name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            dedupe = {"email": email} if email else {"company_name": org, "contact_name": name}
            if email and (await db.contractors.find_one({"email": email})):
                continue
            if await db.prospects.find_one(dedupe):
                continue
            await db.prospects.insert_one({"company_name": org, "contact_name": name, "email": email,
                "phone": p.get("phone") or "", "title": p.get("title") or "", "outreach_status": "NEW",
                "sequence": SEQUENCE, "created_at": now_iso()})
            if email:
                pushed.append({"email": email, "first_name": p.get("first_name") or name.split(" ")[0],
                               "last_name": p.get("last_name"), "company_name": org, "job_title": p.get("title")})
            added += 1
    await instantly_add_leads(pushed)
    return {"added": added, "sequence_steps": len(SEQUENCE), "source": "apollo"}


async def google_prospecting():
    added = 0
    query = os.environ.get("GOOGLE_SEARCH_QUERY") or "commercial general contractor construction company"
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.get("https://www.googleapis.com/customsearch/v1",
                        params={"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": 10})
        r.raise_for_status()
        for it in r.json().get("items", []):
            website = it.get("link", "")
            if not website:
                continue
            domain = urlparse(website).netloc.replace("www.", "")
            name = (it.get("title") or domain).split("|")[0].split("-")[0].strip()[:80]
            if await db.prospects.find_one({"$or": [{"website": website}, {"company_name": name}]}):
                continue
            await db.prospects.insert_one({"company_name": name, "contact_name": "", "email": "", "phone": "",
                "title": "General Contractor", "website": website, "source": "google",
                "outreach_status": "NEW", "sequence": SEQUENCE, "created_at": now_iso()})
            added += 1
    return {"added": added, "source": "google"}


async def run_prospecting():
    added, sources = 0, []
    if APOLLO_API_KEY:
        try:
            r = await apollo_instantly_prospecting(); added += r["added"]; sources.append("apollo")
        except Exception as e:
            logger.error(f"apollo fail: {e}")
    if GOOGLE_API_KEY and GOOGLE_CSE_ID:
        try:
            r = await google_prospecting(); added += r["added"]; sources.append("google")
        except Exception as e:
            logger.error(f"google fail: {e}")
    if not sources:
        pushed = []
        for lead in MOCK_LEADS:
            if await db.contractors.find_one({"email": lead["email"]}) or await db.prospects.find_one({"email": lead["email"]}):
                continue
            await db.prospects.insert_one({**lead, "outreach_status": "NEW", "sequence": SEQUENCE, "created_at": now_iso()})
            parts = lead["contact_name"].split(" ")
            pushed.append({"email": lead["email"], "first_name": parts[0], "last_name": parts[-1], "company_name": lead["company_name"]})
            added += 1
        await instantly_add_leads(pushed)
        sources.append("mock")
    return {"added": added, "sequence_steps": len(SEQUENCE), "source": "+".join(sources)}


@api.post("/cron/prospecting")
async def cron_prospecting(user: dict = Depends(get_current_user)):
    return await run_prospecting()


@api.get("/prospects")
async def list_prospects(user: dict = Depends(get_current_user)):
    ps = await db.prospects.find().sort("created_at", -1).to_list(500)
    for p in ps:
        p["id"] = str(p.pop("_id"))
    return ps


@api.patch("/prospects/{pid}")
async def update_prospect(pid: str, body: dict, user: dict = Depends(get_current_user)):
    status = body.get("outreach_status")
    if status not in ("NEW", "EMAILED", "RESPONDED", "CONVERTED"):
        raise HTTPException(400, "Invalid status")
    await db.prospects.update_one({"_id": ObjectId(pid)}, {"$set": {"outreach_status": status}})
    return {"ok": True}


# ---------- Notifications feed ----------
@api.get("/notifications")
async def notifications(user: dict = Depends(get_current_user)):
    ns = await db.notifications.find().sort("created_at", -1).to_list(100)
    for n in ns:
        n["id"] = str(n.pop("_id"))
    return ns


# ---------- PAYMENTS (Stripe Flow A) ----------
@api.post("/payments/checkout")
async def create_checkout(req: CheckoutReq):
    prices = stripe.Price.list(lookup_keys=[req.lookup_key], active=True, limit=1).data
    if not prices:
        raise HTTPException(500, "Price not found")
    price = prices[0]
    session = stripe.checkout.Session.create(
        line_items=[{"price": price.id, "quantity": 1}],
        mode="subscription",
        success_url=f"{req.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{req.origin_url}/payment/cancel",
        managed_payments={"enabled": True},
        metadata={"user_id": req.user_id or "", "lookup_key": req.lookup_key},
    )
    await db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": req.user_id, "lookup_key": req.lookup_key,
        "amount": (price.unit_amount or 0) / 100, "currency": price.currency,
        "status": "initiated", "payment_status": "pending", "created_at": now_iso(), "updated_at": now_iso()})
    return {"checkout_url": session.url, "session_id": session.id}


@api.get("/payments/status/{session_id}")
async def payment_status(session_id: str):
    rec = await db.payment_transactions.find_one({"session_id": session_id})
    if not rec:
        raise HTTPException(404, "Transaction not found")
    if rec.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"status": "completed", "payment_status": "paid", "updated_at": now_iso()}})
                if rec.get("user_id") and ObjectId.is_valid(rec["user_id"]):
                    await db.contractors.update_one({"_id": ObjectId(rec["user_id"])},
                        {"$set": {"subscription_status": "active", "stripe_customer_id": s.customer}})
                rec = await db.payment_transactions.find_one({"session_id": session_id})
        except stripe.error.StripeError:
            pass
    return {"session_id": rec["session_id"], "status": rec["status"], "payment_status": rec["payment_status"]}


@api.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Invalid signature")
    obj, t = event["data"]["object"], event["type"]
    if t in ("checkout.session.completed", "customer.subscription.created"):
        sid = obj.get("id")
        await db.payment_transactions.update_one(
            {"session_id": sid, "payment_status": {"$ne": "paid"}},
            {"$set": {"status": "completed", "payment_status": "paid", "updated_at": now_iso()}})
        rec = await db.payment_transactions.find_one({"session_id": sid})
        if rec and rec.get("user_id") and ObjectId.is_valid(rec["user_id"]):
            await db.contractors.update_one({"_id": ObjectId(rec["user_id"])},
                {"$set": {"subscription_status": "active", "stripe_customer_id": obj.get("customer")}})
    return {"status": "ok"}


@api.get("/")
async def root():
    return {"message": "COI Autopilot API"}


app.include_router(api)

from fastapi.staticfiles import StaticFiles
(ROOT_DIR / "uploads").mkdir(exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(ROOT_DIR / "uploads")), name="uploads")

origins = [
    "https://emergent-build.onrender.com",
    FRONTEND_URL,
    "http://localhost:3000",
    "http://localhost:5173",
]

# Filter out empty or duplicate origins
allowed_origins = list(set([o for o in origins if o]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler()


async def seed():
    await db.contractors.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "AdminPass123!")
    admin = await db.contractors.find_one({"email": admin_email})
    if not admin:
        res = await db.contractors.insert_one({
            "company_name": "Skyline General Contractors", "email": admin_email, "phone": "+13105550100",
            "password_hash": hash_password(admin_password), "stripe_customer_id": None,
            "subscription_status": "active", "role": "contractor", "created_at": now_iso()})
        gc_id = str(res.inserted_id)
        demo_subs = [
            ("Ace Electrical Co", "Tom Baker", "tom@aceelectric.com", "+13105551201", "POL-GL-88123", (date.today() + timedelta(days=200)).isoformat(), 2000000, "VALID", ""),
            ("Rapid Plumbing LLC", "Sara Lin", "sara@rapidplumb.com", "+13105551202", "POL-GL-77004", (date.today() - timedelta(days=10)).isoformat(), 1500000, "EXPIRED", "Policy expired"),
            ("Precision Framing", "Joe Diaz", "joe@precisionframe.com", "+13105551203", "POL-GL-55210", (date.today() + timedelta(days=20)).isoformat(), 1000000, "NEEDS_REVIEW", "Expiring within 30 days"),
            ("BudgetPaint Pros", "Nina Roy", "nina@budgetpaint.com", "+13105551204", "POL-GL-33119", (date.today() + timedelta(days=150)).isoformat(), 500000, "INSUFFICIENT", "Liability limit under $1M threshold"),
        ]
        for cn, ct, em, ph, pol, exp, lim, st, rr in demo_subs:
            sres = await db.subcontractors.insert_one({"contractor_id": gc_id, "company_name": cn,
                "contact_name": ct, "email": em, "phone": ph, "created_at": now_iso()})
            await db.compliance_documents.insert_one({"subcontractor_id": str(sres.inserted_id),
                "contractor_id": gc_id, "gl_policy_number": pol, "gl_expiration_date": exp,
                "general_liability_limit": lim, "status": st, "review_reason": rr,
                "document_url": "", "created_at": now_iso()})
    if await db.prospects.count_documents({}) == 0:
        await run_prospecting()
    for gc in await db.contractors.find({"slug": {"$exists": False}}).to_list(1000):
        s = await unique_slug(slugify(gc.get("company_name", "gc")), str(gc["_id"]))
        await db.contractors.update_one({"_id": gc["_id"]}, {"$set": {"slug": s, "timezone": gc.get("timezone", "UTC"), "onboarded": True}})    # write test credentials
    try:
        Path("/app/memory/test_credentials.md").write_text(
            f"# Test Credentials\n\n## Contractor (admin/owner)\n- Email: {admin_email}\n- Password: {os.environ['ADMIN_PASSWORD']}\n- Login: POST /api/auth/login\n\nDashboard is at /dashboard after login.\n")
    except Exception:
        pass


@app.on_event("startup")
async def startup():
    await seed()
    scheduler.add_job(run_expiration_check, "cron", hour=0, minute=0, id="daily_exp", replace_existing=True)
    scheduler.add_job(run_prospecting, "cron", day_of_week="mon", hour=8, minute=0, id="weekly_prospect", replace_existing=True)
    scheduler.add_job(run_scheduled_reports, "cron", minute=0, id="hourly_reports", replace_existing=True)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    client.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)