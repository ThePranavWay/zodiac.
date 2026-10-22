# Final integrated build — validation report

Source repository commit: `c2122feaa6b661a629c2dcf1b433cf47cb37002c`.

## Automated build

`npm run build` passed JavaScript syntax checks and **64 isolated local Python tests**. The final test run completed in 23.114 seconds.

Coverage includes secure solo/team accounts, password hashing, multi-device login, private activation/recovery, immutable registration starts, concurrent notebook saves, four-level-only progress, idempotent verification, frozen completed clocks, first-three finish order, migration idempotency, organizer controls, original level preservation, launch/play routes, theme tags, exact closing boundary, closed-submission rejection and authenticated post-event notes/results.

## Actual combined-build browser checks

```text
PASS All four actual combined-build non-level pages load with theme and local fonts
PASS Actual local solo registration/login, leading zeros, four-member form controls, shared notebook autosave and leaderboard; start time unchanged
PASS All four test-only level verifications create first-place podium and permanently freeze the displayed timer
PASS Original full-size case-image modal still opens and closes
PASS Organizer authenticates against the repaired backend; no reset/recovery mutations used
PASS No horizontal overflow at 320/390/768px on all four non-level pages
PASS All four original levels remain unthemed, including accidental-asset-inclusion guard
PASS Reduced-motion users see visible forms without decorative particles
PASS Actual launch redirect at midnight IST preserves query/hash
PASS Closing browser gate redirects to themed ending; signed-out results stay private
PASS Zero uncaught page errors in the primary integrated browser journey
```

Test level passwords and dummy accounts existed only in the isolated local test process/database. They are not production passwords or player records and are not shipped in the website package.

## Preserved source files

The original four HTML level files, level-session.js, app.js, organizer.js, style.css, event-redirect.js, storage.py, schema.sql and vercel.json remain byte-identical to the supplied repository. Existing image/font assets are retained. `preservation-sha256.json` records protected public-file checksums.

## Limitations / scope

- These are local Chromium/Flask/SQLite tests, not a production deployment or a new PostgreSQL service end-to-end test.
- The pre-test browser initially required missing sandbox system libraries; these were installed locally and the browser suite then passed.
- Native OS select popups differ from the reference's Radix dropdowns; the closed controls retain the glass theme without rewriting form logic.
- Launch is a landing-page redirect, not a new server-side pre-launch authorization gate. Existing registration controls remain available to the organizer.
- Authenticated ending results remain private. No real player data, credentials or fake official winners are published.
- No GitHub push, Vercel deployment, database change or destructive production operation was performed.
