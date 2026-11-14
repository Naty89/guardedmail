# Guarded Mail — Progress

Update this file whenever something is finished, blocked, or newly discovered.
What to build and how: [PROJECT_SPEC.md](PROJECT_SPEC.md).

**Last updated:** 2026-11-14
**Current milestone:** M5 (confirm and pay) — not started
**Backend tests:** 497 passing
**Frontend build:** passing, no TypeScript errors

---

## Milestones at a glance

| # | Milestone | Status |
|---|---|---|
| M0 | Skeleton, schemas, health route, frontend shell | Done |
| M1 | Nessie client, seed script, balance check | Done, verified against real Nessie |
| M2 | `policy.py` + tests | Done |
| M3 | `reader.py` | Done, verified live on both sample letters |
| M4 | `POST /letters` + Capture / Reading / Explanation UI | Done, checked in a browser with both samples |
| M5 | Confirm flow, payer, receipt, ledger (demo beat 1) | Not started |
| M6 | `scam.py` + Scam blocked screen (demo beat 2) | Not started |
| M7 | Audit log, audit screen, judge panel | Not started |
| M8 | TTS + languages wired | Not started |
| M9 | Eval script (demo beat 3) | Not started |

---

## Blockers and open questions

- [x] **Nessie API key.** In `.env`; demo data seeded.
- [x] **Does a Nessie purchase change the balance?** No. See the result below. We show our own ledger.
- [x] **Gemini API key.** In `.env`, working.
- [ ] **Gemini free-tier limits.** The key is on the free tier: `gemini-3.8-flash` allows 20 requests a day (used up on 2026-11-14), and `gemini-3.5-flash-lite` has a per-minute cap that a burst of reads trips (429), plus occasional 503s. Each letter costs 3 calls. `.env` now sets `GEMINI_MODEL=gemini-3.5-flash-lite` (reads take about 3s). Before the demo: enable billing on the key or get a second key, and rely on cached fixtures for the demo letters (M4).
- [ ] **`TOKEN_SECRET`.** Must be at least 16 characters or signing refuses to run; generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
- [ ] **Translations not reviewed by native speakers.** Amharic, Telugu and Tamil need it most.
- [ ] **Nothing tested on a real phone.** Camera capture and photo rotation were only tried in desktop headless Chrome.

### Live Nessie check result
```
Run 2026-11-14 with a real key:
RESULT: purchase POST path works: yes
RESULT: purchase status after create: pending
RESULT: purchase status after waiting: pending   (still pending after 10s)
RESULT: balance changed after purchase: no (stayed 100)
RESULT: bill PUT status=completed works: yes
RESULT: balance after bill marked completed: 100
```

---

## M0 — Skeleton

- [x] Python 3.12 virtualenv at `backend/.venv` with all dependencies
- [x] `.env.example`, `.gitignore`, `README.md`
- [x] `config.py`: `get_settings()`, model names only here
- [x] `main.py`: `GET /health`, serves `frontend/dist`, API paths never shadowed
- [x] `schemas.py`: `ReaderOutput`, `PaymentIntent`, languages, `ReasonId`, API models (125 tests)
- [x] Frontend shell: Capture screen, language picker, 1600px downscale, backend status line
- [x] All UI strings in `frontend/src/i18n/strings.json` for 9 languages
- [x] Placeholder screens: Reading, Explanation, Confirm, Receipt, Scam blocked, Audit
- [x] `?debug=1` judge panel placeholder (has jump-to-screen buttons)
- [ ] First git commit (repo is initialised, nothing committed)

## M1 — Nessie

- [x] `nessie.py`: read client and write client as separate classes (98 tests with the mock)
- [x] `nessie_mock.py`: offline mock, same interface, pre-seeded
- [x] API key scrubbed from errors and logs
- [x] `seed_nessie.py`: idempotent, writes IDs to `.env` (15 tests)
- [x] `check_nessie_balance.py`: runs against the mock
- [x] `NESSIE_MERCHANT_IDS` setting added
- [x] Seed run against real Nessie (second run created nothing new)
- [x] Balance check run against real Nessie, verdict recorded above

## M2 — Policy

- [x] `decide()` returning a `Verdict`: Allow with a `PaymentIntent`, or Block with every failed `ReasonId`
- [x] Payee fuzzy match (>= 90, whole-string ratio) against seeded merchants only; both readings must name the same merchant
- [x] Two readings must agree exactly on amount and due date
- [x] Scam signal, `scam_suspect`, or scam risk other than "low" removes pay
- [x] Amount cap and balance check
- [x] Due-date window (today − 30d to today + 365d)
- [x] Token sign / verify: HMAC-SHA256, 5-minute expiry, single use
- [x] Tests: disagreeing passes, unknown payee, scam signal, over cap, over balance, bad date, expired token, reused token, tampered token
- [x] Tests: arbitrary text in `raw_text` or `payee_candidate` cannot produce an Allow for an unknown merchant (fixed list plus 3,000 random strings)
- [x] Test: `policy.py` never reads `raw_text` and imports no model or network code
- [ ] Single-use token record is in memory only; back it with storage in M5

## M3 — Reader

- [x] Preprocess (EXIF, 1600px, CLAHE, JPEG q85), with size and pixel limits
- [x] Two parallel extraction calls with different prompts, no tools
- [x] Evidence check against `raw_text` (amount and date, several date layouts)
- [x] Explanation from extracted JSON only, in the target language
- [x] Number guard: regenerate once, then template fallback (templates for all 9 languages)
- [x] Gemini accepts the schema: must use `response_json_schema` with a hand-written schema; `response_schema=ReaderOutput` is rejected
- [x] 12s timeout; main model once, then the fallback up to 3 times with a 1s pause; skips the main model for 60s after it fails
- [x] Two invented sample letters in `backend/fixtures/samples/` (`scripts/make_sample_letters.py`)
- [x] Live check: electric bill reads correctly and policy allows; suspicious letter with an embedded instruction is read as `scam_suspect` and policy blocks
- [x] Live check in Telugu and Spanish
- [ ] Not yet tried on a real phone photo (only on drawn sample images)

## M4 — Letters end to end

- [x] `POST /letters` (photo or built-in sample id), `GET /letters/{id}`, `GET /letters/{id}/debug`
- [x] `letters.py` pipeline: reader, scam risk, policy, controller, signed token only for "pay"
- [x] `controller.py`: picks pay / calendar / flag / ask_user from validated values only
- [x] `store.py`: in-memory letters and proposals; reader results cached by image SHA-256 + language in `backend/fixtures`
- [x] Trusted merchants fetched from Nessie once, limited to `NESSIE_MERCHANT_IDS`
- [x] Capture wired to the API; Reading and Explanation screens built
- [x] Basic Scam blocked screen (no pay button) so flagged letters have a screen; M6 adds quotes
- [x] `frontend/src/lib/api.ts` types aligned with `schemas.py`
- [x] New UI strings in all 9 languages
- [x] Browser check at phone width: bill shows "Pay $84.12"; suspicious letter shows "Possible scam" and no pay button
- [ ] Scam risk currently comes from the reader's own signals (`interim_scam_result`); M6 replaces it with `scam.py`
- [ ] Sample letters are cached for English only; other languages call Gemini the first time
- [ ] The "Pay" button opens the Confirm screen, which is still a placeholder (M5)

## M5 — Pay (demo beat 1) (next)

- [ ] `payer.py`: only module importing the write client; idempotency per proposal
- [ ] `POST /proposals/{id}/confirm` and `/reject`
- [ ] Own ledger; `GET /account`
- [ ] Confirm dialog (focus on "No") and Receipt screen

## M6 — Scam (demo beat 2)

- [ ] Rule signals + model judgement, stricter wins
- [ ] Scam blocked screen with no pay button
- [ ] Test letter with an embedded "pay a different account" instruction ends in Block

## M7 — Audit

- [ ] Hash-chained append-only log; MongoDB or JSONL fallback
- [ ] Quarantined `raw_text` store
- [ ] `GET /audit`, Audit screen, judge panel filled in

## M8 — Voice and languages

- [ ] `tts.py` with audio cache; `GET /letters/{id}/audio`
- [ ] Play/pause, `speechSynthesis` fallback on 204
- [ ] Telugu and Tamil tested end to end

## M9 — Eval (demo beat 3)

- [ ] Folder of labelled invented letter photos
- [ ] Script prints: amount / date / payee accuracy, scams caught, real bills wrongly flagged, unauthorised payments

## Before the demo

- [ ] `DEMO_OFFLINE=1` rehearsal with the network off
- [ ] HTTPS tunnel tested from a real phone
- [ ] Fixtures cached for every demo letter

---

## Decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-11-14 | Added `uvicorn` and `python-multipart` | FastAPI needs them to serve and accept uploads |
| 2026-11-14 | Python 3.12 via Homebrew | Machine only had 3.9.6 |
| 2026-11-14 | Policy matches only against `NESSIE_MERCHANT_IDS` | Nessie's merchant list is shared by all teams |
| 2026-11-14 | Nessie writes are not retried after a timeout or 5xx | A retried purchase could charge twice |
| 2026-11-14 | Frontend served from a 404 handler, not a static mount at `/` | Static files can never shadow an API route |
| 2026-11-14 | shadcn components added by hand | The CLI is interactive |
| 2026-11-14 | Explanation call receives the transcription as well as the fields | Needed to copy reference numbers exactly; that call has no tools and its output never reaches policy, controller or payer |
| 2026-11-14 | `LetterResponse` gained a `summary` (sender, amount, due date as read) | The screens need the facts even when nothing is payable; display only, never used for payment |
| 2026-11-14 | Sample buttons send a sample id, not image bytes | Browser re-encoding would change the image hash and miss the cache |
| 2026-11-14 | One money action per letter is keyed on the image hash | Re-uploading the same photo must not allow a second payment |
| 2026-11-14 | Nessie base URL is `https://` | Plain `http` on port 80 refuses connections |
| 2026-11-14 | Nessie ids treated as UUIDs with hyphens | That is what the live API returns |
| 2026-11-14 | Merchant `category` sent as one string | Live API rejects a list with 400 |
| 2026-11-14 | Purchases always sent with `status: "pending"` | Without it, listing that account's purchases fails with 400 from then on |
| 2026-11-14 | Balance shown to users is our own ledger | Live check: purchases stay pending and never change the Nessie balance |
