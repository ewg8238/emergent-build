# COI Autopilot — PRD

## Original Problem Statement
End-to-end automated B2B micro-SaaS for General Contractors (GCs) to track, parse and automate Subcontractor Certificate of Insurance (COI) compliance, with an automated outbound lead-generation engine. Adapted from the requested Supabase/n8n/Softr stack to the platform-native **React + FastAPI + MongoDB** stack (same architecture, workflows and UI).

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`), all routes under `/api`. APScheduler for cron workflows.
- **DB**: MongoDB collections mirroring the requested schema — `contractors` (double as auth users), `subcontractors`, `compliance_documents`, `prospects`, `notifications`, `payment_transactions`.
- **Frontend**: React (CRA + craco), Tailwind + shadcn/ui, Cabinet Grotesk / IBM Plex Sans, Swiss high-contrast design.

## Integrations
- **GPT-5.4 Vision** (emergentintegrations, Emergent LLM key) — COI parsing (PDF rendered via PyMuPDF).
- **JWT auth** (bcrypt + PyJWT, cookie + Bearer).
- **Stripe** claimable sandbox (test mode) — Pro Plan $149/mo (`pro_monthly`), managed payments; webhook `/api/stripe/webhook`.
- **Resend** (Emergent-managed) — real transactional email.
- **Twilio SMS — SIMULATED** (logged to `notifications`).
- **Apollo.io + Instantly.ai — SIMULATED** (mocked leads + sequence).

## User Personas
- **General Contractor (GC)**: logs in, invites subs, monitors compliance dashboard, runs reminder drips, manages prospecting.
- **Subcontractor**: receives link, uploads COI on public mobile page.

## Implemented (2026-08-04)
- DB architecture + seed (admin `ewg8238@gmail.com`, 4 subs/docs across all statuses, 6 prospects).
- Workflow A: Invite subcontractor → insert + email + simulated SMS with upload link.
- Workflow B: AI COI parsing + validation (EXPIRED / INSUFFICIENT <$1M / VALID / NEEDS_REVIEW) + GC notify.
- Workflow C: Daily expiration cron + manual "Run Reminder Drip".
- Workflow D: Weekly prospecting cron + manual "Run Pipeline" + Kanban outreach board.
- Pages: Landing (hero, bento features, pricing+Stripe), Login, Register, Dashboard (color-coded table, search, filter, stats), Invite, public Upload (confirmation), Prospects, Payment result.
- Stripe subscription checkout + status polling + webhook provisioning.
- Tested: backend 11/11 pass, all frontend flows pass.

## Implemented (2026-08-04) — Iteration 2
- **Secure upload links**: expiring (14-day) single-use tokens on `subcontractors`; `/api/upload` validates token (403 on invalid/expired/reused); reminder cron regenerates a fresh token + link.
- **COI document viewer**: uploaded files served at `/api/uploads/*`; dashboard "View" opens the certificate in a modal (image or PDF iframe).
- **Twilio SMS (LIVE-wired)**: `send_sms` sends real SMS when `TWILIO_*` set, else simulated. Keys configured. NOTE: trial account only texts verified recipients until upgraded.
- **Apollo.io + Instantly.ai (LIVE-wired)**: `run_prospecting` calls Apollo people search + Instantly campaign push when keys set, else mock. Apollo key configured but Free plan blocks the Search API (needs paid plan) → auto-falls back to mock. Instantly key/campaign not provided yet (push skipped).
- **P1**: Signed/expiring token on public upload links; real Twilio SMS (needs keys); real Apollo/Instantly (needs keys).
- **P2**: Split server.py into routers; document viewer for uploaded COIs; multi-user roles per contractor; email deliverability hardening (intermittent 422 from managed Resend under load).


## Implemented (2026-08-04) — Iteration 3
- **Instantly.ai enrollment (LIVE)**: `instantly_add_leads()` enrolls prospects into campaign `bb9e480a-55ab-44c7-8fa6-60e030d27c68` via V2 `/api/v2/leads` (verified). Runs from Apollo + mock paths.
- **Renewal auto-chase**: `run_expiration_check` re-nudges email+SMS on a 3-day cadence via `last_nudged_at`/`nudge_count` ("Reminder #n"); resets on VALID upload.
- **Compliance export**: `GET /api/compliance-documents/export?format=csv|pdf` (reportlab color-coded PDF). Dashboard CSV/PDF buttons.
- NOTE: Apollo Free plan still blocks Search API → prospecting falls back to mock leads (which now enroll into Instantly). Twilio still trial (verified recipients only).


## Implemented (2026-08-04) — Iteration 4
- **Scheduled weekly reports**: Monday 07:00 cron `run_weekly_reports` emails each GC an inline HTML compliance summary + link to auto-generated PDF (managed Resend has no attachments). Manual "Email" button on dashboard (`/api/reports/email-me`).
- **Escalation alerts**: GC emailed when a sub ignores >= threshold reminders (per-GC configurable), `escalated` flag prevents repeats, resets on VALID upload.
- **Company settings** (`GET/PUT /api/settings`, `POST /api/settings/logo`): logo upload (served `/api/uploads/logos/*`), brand color, escalation threshold (2/3/5), extra weekly-report recipients. New `/settings` page + nav link.
- **Branded PDF/email**: `build_compliance_pdf` renders GC logo + brand color on title and header row; report email uses brand color + logo. Verified visually.
