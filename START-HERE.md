> **October 2026 update:** parts of this guide (the four level pages) are superseded — read `UPDATE-2026-10-21.md` first.

# Final complete website — upload guide

This is the **whole Zodiac Seeker website**, not a theme-only patch. All theme tags, fonts, launch/play pages and scheduled ending are already combined. You do not need the earlier theme installer.

Built from your repository `ThePranavWay/zodiac-s`, commit `c2122feaa6b661a629c2dcf1b433cf47cb37002c`.

## Included

- Dyatlov-reference dark theme, glass forms and original amber SVG cursor on the non-level pages.
- Launch page: **1 November 2026, 12:00 AM IST**; redirects to `/play` with query/hash preserved.
- `/play`: solo/team registration, secure admission/password login, dashboard, shared notebook and leaderboard.
- Four-level-only backend; immutable registration start, permanently frozen timer after all four levels, and first-three server finish-order podium.
- Organizer desk and private activation/password recovery.
- Ending page: **13 November 2026, 12:00 PM (noon) IST**; server closing guard plus launch/play browser gate.
- Original four level HTML files, their integration script, main application/organizer scripts, base styles and supplied image assets unchanged from your repository.

## Important repair in this final build

Your repository already had the four-level frontend and schema, but its `app.py` was the older v3 closing-only backend and imported `advanced.py`, a file absent from the repository. That combination could not start correctly.

This package uses the matching four-level backend and retains your repository's `/play` route and scheduled closing code. Your `storage.py`, `schema.sql`, Vercel configuration and frontend game logic remain unchanged. No live data was accessed or altered. See `CHANGES.md`.

## Upload using GitHub — no terminal

1. **Back up your current repository** with Code → Download ZIP.
2. Extract `Zodiac-Seeker-Final-Complete-Website.zip`.
3. Open the extracted `Zodiac-Seeker-Final` folder. You should see `app.py`, `vercel.json`, `requirements.txt`, `schema.sql`, and the `public` folder together.
4. Open your website repository on GitHub **at its root**, not inside `public/`.
5. Choose **Add file → Upload files**. Drag the **contents** of the extracted `Zodiac-Seeker-Final` folder into the upload area, including the `public`, `tests`, `scripts` and `migrations` folders. Do not upload the ZIP itself or create an extra outer folder in the repository.
6. Commit. Your existing Vercel project should deploy normally from the connected repository.
7. Check Vercel's deployment logs and test the pages below.

Do not delete your Vercel project, switch databases, reset the event, or change credentials to install this package.

## Preserve your Vercel environment variables

Keep the same existing values of:

- `DATABASE_URL`
- `SIGNING_KEY` — changing it can invalidate existing sessions/private links.
- `ORGANIZER_PASSWORD`
- Any `LEVEL_1_PASSWORD_SHA256` through `LEVEL_4_PASSWORD_SHA256` values you already use.

`.env.example` is only a placeholder template; it contains no live secrets. Do not upload a real `.env` or paste private values into source files.

## Database: no reset or destructive migration

The final `schema.sql` is byte-identical to the schema already in the supplied repository. If that schema is already installed in the database used by your current `DATABASE_URL`, **no new database migration is required**.

If your actual database still lacks `zs_finishes`, use only the included **additive** `migrations/04-four-level-podium.sql` in the SQL editor for the exact branch/database used by your app. Back up first, temporarily close new submissions/arrange a maintenance window, and run it before deploying this backend. It creates the finish ledger and imports existing four-level completions without deleting accounts, progress or notes. Previously assigned places are not renumbered.

For an entirely new empty database, install `schema.sql`. Never run a fresh-event reset or a legacy delete migration as part of this update. The obsolete destructive legacy migration is intentionally not in this ZIP. If it still exists in your GitHub repository after upload, leave it unexecuted (or delete that obsolete SQL file from the repository separately).

No migration has been run on your database by preparing this package.

## After deployment

- `/`: dark launch page and countdown. Launch is 1 November at midnight IST, not noon.
- `/play`: dark glass registration/login; test an existing account without re-registering it.
- Confirm existing start time/progress, shared notebook saving and leaderboard remain correct.
- `/organizer`: organizer sign-in, roster and private recovery controls. Never click the destructive reset merely to test deployment.
- `/event-ended`: themed preview before closing; concluded state after 13 November noon IST.
- Open each original level directly and confirm its old design and cursor remain unchanged.
- Hard-refresh if your browser still displays cached light styles.

The final theme is active on launch, play, organizer and ending only. Native select popups can vary by OS. Touch devices use their native pointer behavior; reduced-motion preferences disable decorative animation.

## Scheduling and privacy notes

- The launch landing is a countdown/redirect; it is not a new server-side pre-launch registration lock. Keep registration closed through the organizer controls if you require that restriction.
- At closing, new registration/answer submissions are rejected. Existing authenticated notebook, login, organizer and results functions remain available; an already accepted in-flight request may complete.
- Ending-page podium data uses the authenticated leaderboard. It does not publish school-player records publicly or invent winners. Signed-out visitors see a private-results fallback.
- No automatic live GitHub/Vercel deployment is performed by supplying this ZIP.

## Validation

See `TEST-REPORT.md` for this combined build's checks. Tests use isolated local SQLite, not your production database. No new production/PostgreSQL end-to-end claim is made.
