from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os, logging, uuid, base64, json, asyncio
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Annotated, Any

import bcrypt, jwt, httpx, stripe, fitz
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, UploadFile, File, Form
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr, BeforeValidator, ConfigDict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coi")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

FRONTEND_URL = os.environ["FRONTEND_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ["EMERGENT_EMAIL_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

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
    # SMS is SIMULATED for the demo (logged to DB). Wire Twilio keys to send real SMS.
    await db.notifications.insert_one({"channel": "sms", "to": to, "subject": "SMS",
                                       "body": body, "status": "simulated", "created_at": now_iso()})
    logger.info(f"[SIMULATED SMS] to {to}: {body}")


def upload_link(sub_id, gc_id):
    return f"{FRONTEND_URL}/upload?sub_id={sub_id}&gc_id={gc_id}"


# ---------- AUTH ROUTES ----------
@api.post("/auth/register")
async def register(body: RegisterReq, response: Response):
    email = body.email.lower()
    if await db.contractors.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    doc = {"company_name": body.company_name, "email": email, "phone": body.phone,
           "password_hash": hash_password(body.password), "stripe_customer_id": None,
           "subscription_status": "trialing", "role": "contractor", "created_at": now_iso()}
    res = await db.contractors.insert_one(doc)
    uid = str(res.inserted_id)
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    return {"id": uid, "company_name": body.company_name, "email": email,
            "subscription_status": "trialing", "token": token}


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


# ---------- WORKFLOW A: Invite Subcontractor ----------
@api.post("/subcontractors/invite")
async def invite_subcontractor(body: InviteReq, user: dict = Depends(get_current_user)):
    gc_id = user["id"]
    doc = {"contractor_id": gc_id, "company_name": body.company_name, "contact_name": body.contact_name,
           "email": body.email.lower(), "phone": body.phone, "created_at": now_iso()}
    res = await db.subcontractors.insert_one(doc)
    sub_id = str(res.inserted_id)
    link = upload_link(sub_id, gc_id)
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
async def parse_coi_with_ai(image_b64: str) -> dict:
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"coi-{uuid.uuid4()}",
                   system_message=("You are an insurance document parser. Extract data from Certificate of "
                                   "Insurance (COI / ACORD) documents. Respond ONLY with strict JSON.")).with_model("openai", "gpt-5.4")
    prompt = ("Extract these fields from this Certificate of Insurance and return ONLY JSON: "
              '{"gl_policy_number": string|null, "gl_expiration_date": "YYYY-MM-DD"|null, '
              '"general_liability_limit": number|null (each-occurrence general liability limit in USD as a plain number)}. '
              "If a field is not found, use null.")
    msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
    resp = await chat.send_message(msg)
    text = resp if isinstance(resp, str) else str(resp)
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "", 1).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


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
async def upload_coi(sub_id: str = Form(...), gc_id: str = Form(...), file: UploadFile = File(...)):
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
    nudged = 0
    for d in docs:
        exp = str(d.get("gl_expiration_date"))[:10]
        new_status = "EXPIRED" if exp < today else "NEEDS_REVIEW"
        if d.get("status") != new_status:
            await db.compliance_documents.update_one({"_id": d["_id"]}, {"$set": {"status": new_status,
                "review_reason": "Policy expired" if new_status == "EXPIRED" else "Expiring within 30 days"}})
        sub = await db.subcontractors.find_one({"_id": ObjectId(d["subcontractor_id"])}) if ObjectId.is_valid(d.get("subcontractor_id", "")) else None
        if sub:
            await send_email(sub["email"], "Your COI is expiring soon — please renew",
                             f"<p>Hi {sub['contact_name']}, your Certificate of Insurance expires on {exp}. Please upload updated paperwork.</p>")
            await send_sms(sub.get("phone", ""), f"Reminder: your COI expires {exp}. Please send updated paperwork.")
            nudged += 1
    return {"scanned": len(docs), "nudged": nudged}


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


async def run_prospecting():
    added = 0
    for lead in MOCK_LEADS:
        if await db.contractors.find_one({"email": lead["email"]}) or await db.prospects.find_one({"email": lead["email"]}):
            continue
        await db.prospects.insert_one({**lead, "outreach_status": "NEW", "sequence": SEQUENCE,
                                       "created_at": now_iso()})
        added += 1
    return {"added": added, "sequence_steps": len(SEQUENCE)}


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler()


async def seed():
    await db.contractors.create_index("email", unique=True)
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin = await db.contractors.find_one({"email": admin_email})
    if not admin:
        res = await db.contractors.insert_one({
            "company_name": "Skyline General Contractors", "email": admin_email, "phone": "+13105550100",
            "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]), "stripe_customer_id": None,
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
    # write test credentials
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
    scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    client.close()
