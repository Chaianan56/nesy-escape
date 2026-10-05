# Main integration — 2026-10-05

Integration branch: `codex/integrate-main`.
Saved timeout fixes: `775d435` on `codex/stylized-backgrounds`.
Merged source: `origin/main` at `94944f00fbaac643317a79e4ecf756f38a13fd2d`.

## Reconciled behavior

- Backend executes ordinary sequence steps once, in order, with a maximum of four. Invalid or oversized lists are rejected before executing any step.
- Before accuse/burn, the response returns `pending_steps`; the frontend offers confirmation and sends those commands through the normal command endpoint. Accusation still requires explicit submitted evidence and records that submission in the server session.
- Both canonical `action=sequence` and legacy `action=ambiguous, sequence=true` are accepted. Backend results use canonical sequence with `sequence=false` so old frontend execution logic cannot replay completed steps.
- Expiration is checked before interpretation, after interpretation, and between sequence steps. Prior successful progress is retained when expiration closes the case; later steps are skipped.
- Main's dynamic prompt pruning is retained with the branch's bounded timeout/retry behavior and exact typed-command shortcuts.
- `instrument` remains the canonical single ID. Incoming legacy `items` is accepted as an alias; IDs are never indexed as lists or shortened to one character.
- Terminal command handling understands sequence, retains filtering for ambiguous choices, and asks before queued irreversible actions.
- Manual pruning benchmark client initialization is deferred so test discovery does not require credentials.

## Validation

- Python non-LLM suite: 147 passed, 5 deselected.
- Frontend Node suite: 31 passed.
- Covers both sequence wire formats, successful multi-step execution, early denial, no partial execution of malformed lists, pending confirmation, actual evidence submission, persistent server state, timeout between steps, no frontend replay, prompt pruning with bounded API requests, and schema alias compatibility.
- Existing timeout UI, image mappings, dialogue, symbolic validation, and server-session tests remain passing.
- Live Gemini and browser visual testing were not run. Mobile testing is outside the current requested scope.

No merge into local/remote main and no deployment or production session changes.
