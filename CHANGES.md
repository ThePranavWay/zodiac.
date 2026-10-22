# Changes from the supplied repository

## 21 October 2026 organizer update

- Deleted the four level HTML files and level-session.js; removed their
  Vercel headers, clean-URL mapping, build-check entries and preservation
  hashes; tests now assert those routes are 404. Backend level-verification
  API, progress/podium tables and existing records were intentionally kept.
- Launch page: larger Poppins/responsive hero title, full-screen layout,
  removed the "Four levels. One investigation." line, added glowing orange
  VIEW BROCHURE button serving public/zodiac-seeker-brochure.pdf.
- /play: added Mission Briefing, Objectives and Initial Evidence sidebar tabs
  (new public/mission.css; minimal app.js tab routing update with refreshed
  preservation hash). Case overview, notebook and leaderboard retained.
- Added public/initial-evidence-reddit-post.png. See UPDATE-2026-10-21.md.
- Launch date moved from 24 October to 1 November 2026 (still 12:00 AM IST);
  the 13 November 2026 noon closing is unchanged.
- Registration fixes: the register button now states when registration is
  closed, form errors scroll into view, and post-registration tab routing
  is guarded against stale/mismatched cached page scripts.
- Login cookie fix: session-cookie SameSite mode is now configurable via
  SESSION_COOKIE_SAMESITE (default Lax for production top-level browsing;
  set to None only for trusted cross-site iframe embedding such as hosted
  previews — it forces Secure). Fixes correct-credential logins appearing
  to fail with "Please log in to your investigator account." when the site
  runs inside a cross-site iframe and the browser rejects the Lax cookie.
  Login/token forms now reset only after the /api/me session check succeeds,
  so typed credentials are kept if the session cannot be established.

Source commit: c2122feaa6b661a629c2dcf1b433cf47cb37002c.

## Theme integration

Added public/zodiac-theme.css, public/zodiac-theme.js and locally bundled reference font families/licenses. Added the two theme tags at the end of the head of index.html, play.html, organizer.html and event-ended.html. Their original page content, form IDs, scripts, dates and existing closing gate remain in place.

## Backend consistency repair

The supplied app.py imported `advanced`, but advanced.py was absent. The supplied frontend app.js and schema.sql were already the separate four-level/podium versions. The complete package therefore restores the matching four-level backend (version 4), retains the supplied /play route and scheduled event-ending hook, and does not add any extra levels or advanced module.

## Preserved byte-for-byte

- All four original level HTML files and level-session.js.
- public/app.js, public/organizer.js, public/style.css and public/event-redirect.js.
- storage.py, schema.sql and vercel.json.
- Original images/fonts/assets from the supplied repository.

preservation-sha256.json records the protected public-file hashes. The main case image source is retained.

## Tests and documentation

Added four-level podium regressions and integrated theme/launch/ending tests. Main-page assertions now check play.html, because index.html is the launch landing. Build validation now includes play/end inline scripts plus the new theme/closing scripts. Updated the outdated v2/new-event deployment documents so installation does not instruct a reset.

Only the additive four-level podium SQL migration is supplied. The obsolete destructive legacy reset SQL file is intentionally omitted; no database operations were performed.

## Not changed or performed

No live repository push, Vercel deployment, database migration, account deletion, signing-key/password rotation, real participant export or public winner publication. No .git directory, real .env, local database, signing key or test-browser state is included in the archive.
