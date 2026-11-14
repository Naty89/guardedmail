# Guarded Mail — Progress

Update this file whenever something is finished, blocked, or newly discovered.
What to build and how: [PROJECT_SPEC.md](PROJECT_SPEC.md).

**Last updated:** 2026-11-14
**Current milestone:** M9 (eval script) — not started
**Backend tests:** 598 passing
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
| M5 | Confirm flow, payer, receipt, ledger (demo beat 1) | Done, checked in a browser and with one live Nessie payment |
| M6 | `scam.py` + Scam blocked screen (demo beat 2) | Done, checked in a browser |
| M7 | Audit log, audit screen, judge panel | Done with the local file; MongoDB path untested |
| M8 | TTS + languages wired | Done; 2 of 12 sample audio files still to generate (daily quota) |
| M9 | Eval script (demo beat 3) | Not started |

---

## Blockers and open questions

- [x] **Nessie API key.** In `.env`; demo data seeded.
- [x] **Does a Nessie purchase change the balance?** No. See the result below. We show our own ledger.
- [x] **Gemini API key.** In `.env`, working.
- [ ] **Gemini free-tier limits.** The key is on the free tier. Daily caps seen: `gemini-3.8-flash` 20 requests, `gemini-3.8-flash-tts` **10 requests**. `gemini-3.5-flash-lite` has a per-minute cap plus occasional 503s. Each new letter costs 3 text calls and 1 speech call. `.env` sets `GEMINI_MODEL=gemini-3.5-flash-lite`. The two sample letters are fully cached, but a NEW photo during the demo will get speech only until the 10 daily speech calls run out, then the browser voice. Enable billing on the key before judging.
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
- [x] First git commit (`a113fa5`, M0–M4)

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
- [x] Used tokens are restored from the audit log on startup (M7)

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

## M5 — Pay (demo beat 1)

- [x] `payer.py`: only app module importing the Nessie write client (enforced by a test)
- [x] Token checked before any bank call; single use; proposal id in the purchase description as the idempotency key
- [x] After an unclear bank failure, looks for the purchase before reporting failure (no double charge)
- [x] `POST /proposals/{id}/confirm` (token only; extra fields rejected with 422) and `/reject`
- [x] Own ledger; `GET /account` (our balance, bank bills, our payments)
- [x] One payment per letter image, even with a fresh proposal
- [x] `GET /letters/{id}/image` thumbnail for the confirm dialog
- [x] Confirm dialog: focus starts on "No", equal-size buttons, closing pays nothing
- [x] Receipt screen
- [x] `scripts/reset_demo.py` sets the demo bills back to pending
- [x] Live check against real Nessie: paid $84.12, bill marked completed, second confirm blocked (bill then reset)
- [x] Ledger, paid letters and used tokens survive a restart (rebuilt from the audit log, M7). Open proposals do not: after a restart, read the letter again.

## M6 — Scam (demo beat 2)

- [x] `scam.py`: rule signals on the transcription plus the reader model's own signals; stricter wins
- [x] Gift card, wire, crypto or payment app alone = high
- [x] Text aimed at software ("ignore previous instructions", "AI assistant", "without asking the user") = high
- [x] Threats, pressure, prizes = medium; agency names and missing account number only reported alongside a stronger sign
- [x] Each reason has a reason ID and a short quote from the letter
- [x] Scam blocked screen shows reasons with quotes and has no pay button
- [x] Test: a letter with an embedded instruction to pay a different account ends in Block, even when the fake reader model obeys the letter and reports a clean, payable bill
- [x] Control test: the same reading without the injected text is payable
- [ ] No separate model call for the scam judgement: it reuses the two extraction passes' signals (saves Gemini quota)
- [ ] Rules are English keywords only

## M7 — Audit

- [x] `audit.py`: append-only log; each event carries `prev_hash` and `hash`; `verify_chain` finds the first altered, removed or reordered event
- [x] Local JSONL storage in `backend/data/` (gitignored)
- [x] Events: `letter_read`, `read_failed`, `scam_checked`, `policy_decided`, `confirm_requested`, `proposal_rejected`, `payment_executed`, `payment_blocked`
- [x] Transcriptions go to a separate quarantine file; the log refuses any event containing `raw_text`
- [x] `GET /audit?letter_id=` returns events plus `chain_ok`
- [x] On startup the ledger, paid letters and used tokens are rebuilt from the log (a restart no longer resets the balance)
- [x] Activity log screen in plain words, in all 9 languages, reachable from Explanation, Scam blocked and Receipt
- [x] Judge panel (`?debug=1`): step timings, model ids, policy verdict and reason IDs, bank calls, audit events with hash links
- [x] `scripts/reset_demo.py` now also archives the local audit log
- [ ] MongoDB backend is written but has never been run against a real cluster (no `MONGODB_URI` set)
- [ ] Nessie request ID: shown if Nessie sends an `x-request-id` header; not yet seen whether it does

## M8 — Voice and languages

- [x] `tts.py`: Gemini speech with a disk cache in `backend/fixtures/audio`; needs API version `v1alpha` (the default rejects `speech_config`); returns WAV
- [x] `GET /letters/{id}/audio`: WAV, or 204 so the browser voice is used
- [x] Audio generation starts in the background when a letter is read
- [x] Play/pause button on the Explanation and Scam blocked screens (no autoplay; hidden for zh, ar, am)
- [x] Browser check (English and Telugu): Play starts the audio, Pause stops it, nothing plays by itself; no button in Amharic
- [x] Telugu and Tamil end to end through the live server: correct payee and amount, explanation in the language, 22s of audio each
- [x] Generated Telugu and Tamil audio transcribed back by Gemini: recognised as Telugu / Tamil and matching the text
- [x] Explanations now write dates with the month as a word, so they read well aloud
- [x] `scripts/warm_fixtures.py`: both sample letters are cached in all 9 languages (18 readings), so the demo letters do not call Gemini
- [ ] Audio cached for 10 of 12 sample/language pairs. Missing: suspicious letter in Tamil and Portuguese. Rerun `python -m scripts.warm_fixtures` after the daily quota resets.
- [ ] Not yet heard by a person, and not yet tried on a real phone
- [ ] Telugu and Tamil wording needs a native speaker's review (the Tamil sample has spelling slips)

## M9 — Eval (demo beat 3) (next)

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
| 2026-11-14 | Scam "model judgement" is the two extraction passes' signals, not a fourth call | Free-tier Gemini quota; each letter already costs 3 calls |
| 2026-11-14 | Added scam reason IDs `payment_app`, `prize`, `impersonation`, `no_account_number`, `embedded_instruction` | The spec's signal list is wider than the reader's 7 signals |
| 2026-11-14 | Nessie base URL is `https://` | Plain `http` on port 80 refuses connections |
| 2026-11-14 | Nessie ids treated as UUIDs with hyphens | That is what the live API returns |
| 2026-11-14 | Merchant `category` sent as one string | Live API rejects a list with 400 |
| 2026-11-14 | Purchases always sent with `status: "pending"` | Without it, listing that account's purchases fails with 400 from then on |
| 2026-11-14 | Balance shown to users is our own ledger | Live check: purchases stay pending and never change the Nessie balance |
