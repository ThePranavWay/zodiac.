# Zodiac Seeker — final complete website

Read **START-HERE.md** for browser-only GitHub/Vercel upload instructions.

This complete Flask/Vercel project includes the source-based Dyatlov dark/glass theme and amber native SVG cursor, launch/play separation, mission briefing/objectives/initial-evidence pages, frozen timers/top-three podium, shared team notebook, organizer tools and the scheduled ending. **October 2026 update: the four standalone level HTML files were removed at the organizer's request — see LEVELS.md and UPDATE-2026-10-21.md.**

- Launch: 1 November 2026, 12:00 AM IST.
- Close: 13 November 2026, 12:00 PM (noon) IST.
- Source: ThePranavWay/zodiac-s at c2122feaa6b661a629c2dcf1b433cf47cb37002c.

The repository's mismatched v3 backend (requiring an absent advanced module) was repaired with its matching four-level implementation, while retaining its closing hook. See CHANGES.md and TEST-REPORT.md. No live deployment, database change or credential is included.

## Optional local development

Use Python 3.11+ in a virtual environment, install requirements.txt, then run `python app.py`. Without DATABASE_URL/VERCEL, the app uses local SQLite. Local setup does not read a .env file automatically. New events start with registration closed; configure a private organizer password and open registration through the organizer desk.

`npm run build` validates JavaScript and runs isolated Python tests; it requires Python with Flask installed. Set PYTHON to your environment's Python path if needed. Node is not required by the production Flask runtime. Never run destructive tests against a production database.

Keep the existing production DATABASE_URL, SIGNING_KEY, ORGANIZER_PASSWORD and optional level hash overrides. Never commit real secrets.
