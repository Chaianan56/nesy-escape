# Neural connectivity diagnosis — 2026-09-29

The natural-language command path is not ready for comparison experiments.

## Observed results

- Original local server on port 8004: WinError 10013 while opening the external connection. This process was launched with restricted network access.
- Server on port 8005: launched with external network permission; this does not fix upstream failures.
- Authenticated model listing succeeded and included the configured gemini-3.5-flash-lite. Listing is not proof that inference works.
- Full game system prompt and ParsedCommand JSON schema, one SDK attempt, 15-second timeout, same Thai input and lounge location:
  - gemini-3.5-flash-lite: HTTP 504 DEADLINE_EXCEEDED after 14.32 seconds.
  - gemini-2.5-flash-lite: HTTP 404 after 0.23 seconds; service says unavailable to new users.
  - gemini-3.5-flash: HTTP 503 after 1.46 seconds; service reports high demand.
  - gemini-3.1-flash-lite: HTTP 504 after 14.09 seconds.
- Earlier minimal inference request also returned HTTP 504. Prompt length alone does not explain the failures.

No model change or rule-parser fallback was applied. A temporary increase to the game's timeout was reverted after it did not resolve the problem. No secrets were printed or stored in this report.

## Next steps

1. Check the same project/model in Google AI Studio to distinguish the app path from account/service availability. Do not start comparative measurements until a real inference succeeds.
2. If inference still fails there, resolve provider/project availability or explicitly select another available provider/model. Record any change as a separate experimental configuration.
3. Once healthy, run repeated real requests with the game's prompt and schema before the experiment. Report latency and service failure rate separately from parsing accuracy.
4. Audit experimental routing: app/main.py currently imports interpret_game from typed_commands. A strict Neural comparison arm must not silently bypass Neural for locally recognized commands. Both arms should use identical input/state fixtures and the same symbolic engine.

Local offline Neural tests passed (12 tests, 5 live tests deselected). This is not evidence of working live inference.
