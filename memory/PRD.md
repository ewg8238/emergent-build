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

## Backlog
- **P1**: Signed/expiring token on public upload links; real Twilio SMS (needs keys); real Apollo/Instantly (needs keys).
- **P2**: Split server.py into routers; document viewer for uploaded COIs; multi-user roles per contractor; email deliverability hardening (intermittent 422 from managed Resend under load).
