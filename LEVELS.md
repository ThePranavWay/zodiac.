# Level files — removed (21 October 2026 update)

Per the organizer's instruction, the four standalone level pages and their
browser helper have been **deleted from this repository**:

- `public/attacks.html` (formerly Level 1, `/attacks`)
- `public/investigate.html` (formerly Level 2, `/investigate`)
- `public/next.html` (formerly Level 3, `/next`)
- `public/later.html` (formerly Level 4, `/later`)
- `public/level-session.js`

Those URLs now return 404. They are no longer linked or served by this website.

**What was intentionally kept:** the backend accounts/timer/notebook/leaderboard,
the level-verification API (`/api/levels/<n>/submit`, `/api/progress`), the
completions/finishes database tables and the podium logic. Existing accounts,
progress and finish records already stored in the production database are not
deleted or renumbered by removing the HTML files. No participant can submit a
level through this website unless/until new level pages are added again.

**GitHub upload warning:** dragging files into GitHub's web uploader does NOT
delete files that are missing from the upload. To remove the levels from the
live site you must also delete the five files above individually on GitHub
(open each file → ⋯ / trash → Delete file → Commit). See
`UPDATE-2026-10-21.md`.
