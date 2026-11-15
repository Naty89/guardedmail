# Guarded Mail — Progress

Update this file whenever something is finished, blocked, or newly discovered.
What to build and how: [PROJECT_SPEC.md](PROJECT_SPEC.md).

**Last updated:** 2026-11-14
**Status:** all of M0–M9 built, plus voice questions. Not finished: see "What still needs to be done".
**Backend tests:** 712 passing
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
| M9 | Eval script (demo beat 3) | Done; 0 unauthorised payments on 14 letters |

---

## What still needs to be done

Everything in the build order (M0–M9) is written, tested and committed, plus voice
questions. **It is built, not finished.** What is left is mostly things only people
can do: testing on real phones, with real voices and real paper, and fixing the
Gemini quota. Work through section A before the demo.

### A. Must do before the demo

#### A1. Fix the Gemini quota (highest risk)
- **Problem.** The key is on the free tier. Daily caps seen: `gemini-3.8-flash` 20
  requests, `gemini-3.8-flash-tts` **10 requests**. `gemini-3.5-flash-lite` has a
  per-minute cap and occasional 503s. A new letter costs 3 text calls and 1 speech
  call; a question costs 1 text call and 1 speech call.
- **What breaks.** The two sample letters are cached and safe. Anything new during
  judging (a judge's own photo, a spoken question) can hit a 429. Speech stops after
  10 uses a day and falls back to the browser voice, which many devices lack for
  Telugu and Tamil.
- **Do this.** Enable billing on the key at https://aistudio.google.com (or get a
  second key from a teammate and swap `GEMINI_API_KEY` in `.env`).
- **Then.** Optionally set `GEMINI_MODEL=gemini-3.8-flash` in `.env` again and run
  `python -m scripts.try_reader` a few times. Keep the lite model if 3.8 is slower
  than about 5 seconds or still returns 503s.
- **Done when.** Five letters and five spoken questions in a row work with audio.

#### A2. Test on a real phone over HTTPS
Nothing has run on a phone yet. The camera and the microphone both need HTTPS.
1. `cd frontend && npm run build`
2. `cd backend && .venv/bin/uvicorn app.main:app --port 8000`
3. In another terminal: `cloudflared tunnel --url http://localhost:8000`
   (or `ngrok http 8000`), then open the `https://…` address on the phone.
4. Check on one iPhone and one Android phone:
   - [ ] "Take a photo" opens the rear camera
   - [ ] A photo taken sideways arrives the right way up
   - [ ] Upload finishes in a few seconds on mobile data
   - [ ] Text is readable; no sideways scrolling; buttons are easy to tap
   - [ ] Play starts the audio (iPhone Safari is the strictest about audio)
   - [ ] The confirm dialog shows the thumbnail and both buttons without scrolling
   - [ ] Arabic shows right to left

#### A3. Try voice questions with a real microphone
The automated browser test could only supply silence, so speaking into the app is
**unproven**.
- [ ] On a laptop (`localhost`): tap "Ask with your voice", allow the microphone,
      ask "What happens if I don't pay?", tap "Stop and send". The card should show
      your question as heard, then the answer.
- [ ] Same on a phone over the tunnel (iPhone Safari records in a different format
      than Chrome; the code converts both to WAV, but this path has never run).
- [ ] Ask in Telugu and Tamil.
- [ ] Say nothing: it should say it could not hear a question.
- [ ] In a noisy room: check it does not answer a question you did not ask.
- If recording fails on a device, the typed box still works; note which device.

#### A4. Test with real photos of paper
All 14 eval letters are drawn images. Real photos will read worse.
1. Print `backend/fixtures/samples/*.jpg` and a few from `backend/fixtures/eval/`.
2. Photograph each one badly on purpose: angled, in shade, slightly crumpled.
3. Run each through the app, or `python -m scripts.try_reader path/to/photo.jpg`.
4. Copy the photos into `backend/fixtures/eval/`, add an entry for each in
   `labels.json` (same fields as the existing ones), and run
   `python -m scripts.run_eval`.
- **Watch for:** `readings_disagree` or `evidence_missing` on clear bills (reader too
  strict or photo too poor), and any real bill flagged as a possible scam.
- **Done when.** The eval table includes at least 5 real photos and still shows
  0 unauthorised payments. Use that table in the pitch, not the drawn-only one.
- Only invented letters. Never real mail.

#### A5. Finish the cached audio
- [ ] After the speech quota resets (or billing is on):
      `cd backend && .venv/bin/python -m scripts.warm_fixtures`
      Missing today: suspicious letter in Tamil and Portuguese.
- [ ] If the explanation prompt changes again, run it with `--refresh-explanations`.

#### A6. Rehearse the demo twice
1. `cd backend && .venv/bin/python -m scripts.reset_demo` (bills back to pending,
   audit log archived), then restart the server so the balance is $2,000.
2. Beat 1: sample electric bill → Play → Pay → Yes → receipt shows $1,915.88.
3. Beat 2: sample suspicious letter → "Possible scam", reasons with quotes, no pay
   button. Open `?debug=1` → Judge panel → BLOCK with reason IDs.
4. Beat 3: `python -m scripts.run_eval` in a terminal → the table.
5. Show the Activity log and the "hash chain verified" line in the judge panel.
- [ ] Rehearse once with Wi-Fi off and `DEMO_OFFLINE=1` in `.env`. In that mode the
      two samples, cached audio, the mock bank and the local log work; new photos
      and questions do not.
- [ ] Decide who holds the phone and who runs the terminal.

#### A7. Bring the README up to date
`README.md` was written at M0. It still has correct setup and run commands but does
not mention `scripts.warm_fixtures`, `scripts.reset_demo`, `scripts.run_eval`,
`scripts.try_reader`, voice questions, or the `?debug=1` judge panel.

### B. Should do if there is time

#### B1. Native-speaker review of every translated text
None of it has been checked by a native speaker. Amharic, Telugu and Tamil need it
most; the cached Tamil explanation has spelling slips. Places to review:
- [ ] `frontend/src/i18n/strings.json` (all buttons and messages, 9 languages)
- [ ] `TEMPLATES` in `backend/app/reader.py` (fallback explanation sentences)
- [ ] `FALLBACKS` in `backend/app/ask.py` (fallback answer sentence)
- [ ] The cached sample explanations: read them in the app in each language
- Check especially that no wording says a letter is safe, legitimate or verified.

#### B2. Stop real uploads being cached inside the repo
Reader results for **every** uploaded photo, including the transcription, are saved
in `backend/fixtures/` next to the demo fixtures, and `git add -A` would commit
them. Fine while only invented letters are used. Before anyone uploads anything
else: write non-sample results to `backend/data/` (gitignored) instead.

#### B3. MongoDB
The spec asks for MongoDB Atlas. `MongoBackend` in `audit.py` is written but has
**never run against a real cluster**.
1. Create a free Atlas cluster, allow your IP, copy the connection string.
2. Put it in `.env` as `MONGODB_URI=…`, restart, read a letter, pay it.
3. Check `GET /audit` shows the events and `chain_ok: true`, then restart the server
   and check the balance is still reduced.
- Known gap: `scripts.reset_demo` archives the local file only; with MongoDB the
  `audit` collection has to be cleared by hand to reset the balance.
- If there is no time, the local file is a working fallback. Say so in the pitch.

#### B4. Accessibility checks by a person
Contrast ratios were calculated by hand, not measured.
- [ ] Run Lighthouse or axe on each screen
- [ ] Use the app once with VoiceOver (iPhone) or TalkBack (Android): the Reading
      screen should announce its steps, the confirm dialog should land on "No"
- [ ] Use it at 200% text size

#### B5. Smaller checks
- [ ] Judge panel against real Nessie: does "request id" show a value, or "not sent
      by Nessie"? Only seen with the mock bank so far.
- [ ] Scam rules are English keywords. A scam letter in Spanish is caught only if the
      reader model flags it. Add Spanish keywords, or say so in the pitch.
- [ ] The eval set is small (14) and its scams were written by the person who wrote
      the rules. Ask a teammate to write three new scam letters without reading
      `scam.py`, add them, and see whether they are caught.
- [ ] No git remote is set. Create the GitHub repo and push. The cached audio adds
      13 MB.

### C. Known limits (accepted for the hackathon; be ready to explain)
- **No login.** Anyone with the tunnel address can use the app, read the audit log
  and make mock payments. Share the address only with judges.
- **One server process.** Letters, open proposals and the audit chain lock live in
  one process. Run a single uvicorn worker.
- **Open proposals are lost on restart.** Paid ones and the balance are restored
  from the audit log; an unpaid letter must be read again.
- **Nessie does not change its balance.** Purchases stay "pending". The balance
  shown is our own ledger.
- **The quarantine file is plain text** on the laptop (`backend/data/`).
- **Zero unauthorised payments is a result on our test set, not a guarantee.**
  Never say the system is injection-proof.
- **Leftover Nessie data** from testing: a few throwaway customers, accounts and
  merchants, and one pending $84.12 purchase on the demo account. Harmless.

### D. Stretch items from the spec that are not built
- [ ] Calendar `.ics` export. The "calendar" action only shows the date for now.
- [ ] Local extraction via Ollama as a privacy mode.

### Settings checklist (`.env`)
- [x] `NESSIE_API_KEY`, and the IDs written by `scripts.seed_nessie`
- [x] `GEMINI_API_KEY` (free tier: see A1)
- [x] `TOKEN_SECRET` (at least 16 characters, or signing refuses to run)
- [x] `GEMINI_MODEL=gemini-3.5-flash-lite` (changed from the default because of quota)
- [ ] `MONGODB_URI` (not set: see B3)

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

## M9 — Eval (demo beat 3)

- [x] `scripts/make_eval_letters.py`: 14 labelled invented letters in `backend/fixtures/eval` (5 payable bills, 4 real-looking letters that must not be payable, 5 scams)
- [x] `scripts/run_eval.py`: runs reader, scam check, policy and controller on each; prints a per-letter table and a summary; exits non-zero if any unauthorised payment
- [x] Makes no payment and writes nothing to the audit log or ledger
- [x] Readings cached, so a rerun takes about a second and uses no Gemini calls
- [x] Test that fails if a rule change lets any eval letter through

Result of the live run on 2026-11-14 (model `gemini-3.5-flash-lite`):
```
Letters read                         14 / 14
Amount correct                       11 / 11
Due date correct                     10 / 10
Payee correct                        8 / 8
Scams caught                         5 / 5
Real letters wrongly flagged         0 / 9
Payable bills offered for payment    5 / 5
UNAUTHORISED PAYMENTS                0 / 14
```

- [ ] These are drawn images in clean fonts (two are tilted, blurred and dimmed), not real phone photos of paper. Expect lower reading accuracy on real photos; add some to `fixtures/eval` with labels.
- [ ] 14 letters is a small set, and the scams were written by the same person who wrote the rules.

## Stretch — Questions about a letter (voice or typed)

- [x] `ask.py`: one model call, no tools; answers only from the letter; number guard; one retry, then a fixed "could not find a clear answer" sentence
- [x] `POST /letters/{id}/ask` (WAV audio or typed text) and `GET /letters/{id}/answers/{n}/audio`
- [x] The answer path cannot reach policy, controller or payer; a test confirms that a model "agreeing" to pay moves no money
- [x] Scam letters: the answer warns and withholds phone numbers, account numbers and payment steps
- [x] Silent, very short or broken recordings are refused in code before any model call (the model was seen inventing a question from silence)
- [x] Question and answer text are kept out of the audit log; only the fact of a question is recorded
- [x] Browser: mic button records and re-encodes to 16 kHz mono WAV; typed box as fallback; answer shown with a Play button
- [x] Live checks: three spoken questions made with the Mac's system voice answered correctly in about 1.5s; typed Telugu question answered in Telugu
- [x] Browser check: typed question works; mic button records and uploads a correctly formatted WAV
- [ ] **Not yet tried with a real microphone and a real person's voice.** The headless test browser only supplied silence, so the full speak-into-the-phone path is unproven.
- [ ] The microphone needs HTTPS on a phone (works on `localhost`); use the tunnel
- [ ] Spoken answers use Gemini speech only while the 10 daily speech calls last, then the browser voice
- [ ] Not available with `DEMO_OFFLINE=1` (answers are not cached)

## Added features (2026-11-15)

- [x] **Calendar export:** `GET /letters/{id}/calendar.ics` gives an all-day event with two reminders (3 days before at 9:00, and on the day at 9:00). Built from stored facts only; letter text is escaped so it cannot add calendar properties (tested with hostile names); refused for scam letters and for letters with no agreed due date. "Add to calendar" on the pay panel and the calendar card. Logged in the audit log
- [ ] Calendar link not tried on a real iPhone or Android: opens in a new tab (`target=_blank`) so the installed iPhone app should keep running, but that is unverified
- [x] **Display settings:** a header button opens text size (normal, large, extra large = 18px, 21px, 24px base) and a high-contrast mode (pure black on white, text at least 7:1, strong card edges, no shadows). Saved on the device, applied before first paint, follows the phone's own "increase contrast" setting on first visit. Layout re-measured at 360px with extra-large text and high contrast: no overflow, no small tap targets (found and fixed two real overflows: the due date and the question box)
- [x] `tests/test_i18n.py`: every language has every string, placeholders survive translation, English never says safe/legitimate/verified, digits are always 0-9
- [x] **Letter history ("My letters"):** `GET /history` lists every letter read, newest first, rebuilt from the audit log (so it survives restarts and cannot disagree with the log). One entry per photo and language. Status with icon and word: Paid, Possible scam, Not paid, Waiting for you, No payment needed. Tapping a letter reopens it with `POST /history/{id}/open`: no photo and no model call, everything is decided again from the saved reading, so a payable bill gets a NEW proposal and token, and an already-paid letter cannot be paid again. Verified in a browser: reopen a bill, pay it, list shows Paid, reopening it offers no Pay button
- [x] **Fixed the "real uploads are cached inside the repo" problem:** new reader results go to `backend/data/readings` and small letter pictures to `backend/data/thumbs` (both git-ignored); the committed `fixtures` are still read, and the warm-up and eval scripts still write there on purpose
- [ ] History is shared by everyone using this server (there is no login), and the letter pictures are stored on this laptop in `backend/data/thumbs`. Fine for invented letters only
- [ ] A letter whose saved reading was deleted shows "We could not open this letter again"
- [x] **Multi-page letters:** photograph up to 4 pages of one letter (rows with remove buttons, "Add another page", cap at 4). All pages go into each of the two extraction calls in order, so the amount, due date and payee can be on different pages. The two-reading agreement, evidence check, scam check and every payment rule are unchanged. A one-page letter keeps its old cache key (cached demo letters still work); several pages hash together in order. Reopening from history works. Live check with real Gemini on a bill split in two (company on page 1, amount and date on page 2): both readings agree and policy allows it, in either page order; page 2 alone is blocked as `unknown_payee`
- [ ] Multi-page not tried with real photos of real paper pages, only with a drawn bill split in two
- [ ] More pages mean more image data per Gemini call, so a 4-page letter is slower and uses more of the free-tier quota
- [ ] The history and confirm dialog show page 1 only

---

## Installable app (PWA)

- [x] Web app manifest, home-screen icons (`scripts/make_app_icons.py` draws them from the header mark), full-screen "standalone" window, status-bar colour, notch and home-bar spacing
- [x] Chrome reports no manifest errors and no installability errors on the tunnel address
- [x] No service worker on purpose: it could cache API answers (balance, audit log) and serve stale screens during development. The app needs the server anyway, so an offline shell would add nothing
- [x] Install hint on the Capture screen, in all 9 languages: iPhone/iPad get "tap Share, then Add to Home Screen" (iOS does not let a website trigger an install); Android and desktop Chrome get a real "Install the app" button; hidden once installed or after "Not now". Tested in headless Chrome with faked iPhone, Android, desktop and installed-app signals
- [x] `ngrok` installed; `./start_tunnel.sh` uses `NGROK_DOMAIN` from `.env` (fixed address) or falls back to a temporary Cloudflare address
- [ ] **ngrok account not set up yet.** Steps: sign up at https://dashboard.ngrok.com, run `ngrok config add-authtoken <token>` in your own terminal, claim the free domain at https://dashboard.ngrok.com/domains, put it in `.env` as `NGROK_DOMAIN=your-name.ngrok-free.app`, then run `./start_tunnel.sh`. Reinstall the home-screen app once, from the fixed address
- [ ] ngrok's free plan may show a one-time "You are about to visit…" warning page before the app loads (per browser; the installed iPhone app has its own cookies, so it may appear once there too). Not tested. Alternative with no warning page: Tailscale Funnel (free, stable address, needs a Tailscale account)
- [ ] **Install on a real iPhone and a real Android phone is untested.** iPhone: Safari, Share, Add to Home Screen. Android: Chrome menu, Install app (or Add to Home screen)
- [ ] **The installed app points at the tunnel address, which changes every time the tunnel restarts.** Then the home-screen icon opens an error page. Fix: a stable address (ngrok free static domain, a Cloudflare named tunnel with your own domain, or hosting the server somewhere). Reinstall after the address changes
- [ ] Not a native app (no App Store or Play Store listing). A native wrapper (Capacitor) would be a separate project

---

## Design system (restyle, 2026-11-14)

- [x] Direction: calm and editorial, with colour where it counts. Cream background, navy ink, cobalt blue (`#1d4ed8`) for main actions and colour blocks, sunny yellow (`#ffc933`, always with dark ink text) as the pop, no gradients, hairline dividers, one dominant action per screen
- [x] Type: Google Sans for everything (open licence OFL-1.1, variable weights 400 to 700, Latin only; the other eight scripts fall back to the system Noto fonts). Headings and key figures are the same face set bold. File is self-hosted in `frontend/public/fonts` (36 KB) so offline mode looks identical. No letter-spacing anywhere (it breaks Arabic joining). Changed from Fraunces + Atkinson on request for a simple, Google-style look
- [x] Tokens live in `frontend/src/index.css` (cream, navy, cobalt, yellow, status colours). Change colours there only. Colour blocks: Capture hero card, pay panel, scam warning header, dark demo-bank strip
- [x] Capture: language pills, one hero card with the single main button, samples as a list
- [x] Explanation: statement-style summary box (sender, amount, due date), quiet scam row, tinted "next step" panel, ask box collapsed until opened
- [x] Receipt styled as a receipt; Activity log as a timeline
- [x] Measured at 360px and 412px on every screen: no horizontal scroll, no tap target under 48px, fonts load; every colour pair is at least 4.5:1 text and 3:1 outlines
- [x] Arabic dates follow the language's own direction (`<Num dir="auto">`)
- [ ] Looked at in headless Chrome only: needs a look on a real phone, and in Safari
- [ ] No dark mode
- [x] Palette changed from teal to cobalt + yellow on request ("more pop"); all pairs re-checked: text at least 5.4:1, outlines at least 4.3:1, yellow focus ring on blue 4.4:1

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
| 2026-11-14 | Fonts are files in `frontend/public/fonts`, not an npm package | No new dependency, and they work offline |
| 2026-11-14 | Wordmark is yellow mark + bold "Guarded" + "Mail" in a cobalt tag | Google Sans tops out at weight 700, so the name stands out through size, colour and the tag |
| 2026-11-14 | Nessie base URL is `https://` | Plain `http` on port 80 refuses connections |
| 2026-11-14 | Nessie ids treated as UUIDs with hyphens | That is what the live API returns |
| 2026-11-14 | Merchant `category` sent as one string | Live API rejects a list with 400 |
| 2026-11-14 | Purchases always sent with `status: "pending"` | Without it, listing that account's purchases fails with 400 from then on |
| 2026-11-14 | Balance shown to users is our own ledger | Live check: purchases stay pending and never change the Nessie balance |
