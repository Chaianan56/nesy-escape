# Game sessions

Serve the frontend from FastAPI and open it through HTTP, not `file://`.
`GET /scene` creates an HttpOnly, SameSite=Strict session cookie on the first visit.
Reloading resumes the same game and does not reset its clock.
The end-of-game restart button calls `POST /new-game` to explicitly reset it.

`POST /command` accepts `{ "text": "..." }`. Legacy `state` snapshots are ignored.
`POST /clock`, `/journal`, and `/pillars` use the cookie and need no request body.
Only the server updates evidence, position, time and endings. Requests for the same
game are serialized so overlapping commands cannot overwrite progress.

This prototype stores sessions in memory for one server process. Run one worker.
Restarting loses games; inactive sessions expire after 24 hours. An expired session
returns HTTP 401 until the page loads `/scene` again. There is a 1,000-session cap.
Use a shared transactional store before deploying multiple workers or requiring
persistent saves. HTTPS enables the cookie's Secure flag.

Tests that need intermediate game states install them directly in the server-side
test session; production HTTP requests cannot install arbitrary states.
