# Stylized artwork integration

Branch: `codex/stylized-backgrounds`. The HUD now uses the existing 28-image collection in `assets/nocturne-stylized-v2`. FastAPI serves it at `/game-art`; the original collection is preserved.

`frontend/art.js` maps server-approved commands to illustrations. Travel to first class shows the corridor; looking around shows the crime room; interrogating Liora shows the medical room. Inspecting evidence shows its close-up. Asking to enter the restricted locomotive shows only the entrance and does not move the player. All six server ending IDs override room imagery, including timeout and resumed closed sessions.

The journal loads an illustration only when an already discovered entry is expanded. Descriptions remain readable text. Related clues sometimes share an illustration, so small visual details may be visible before their individual evidence entries are discovered; images never grant those entries or replace the server rules.

No image hotspots, navigation buttons, or automatic clue collection are introduced. The train diagram remains read-only. Image failures display a message and do not block typed commands. A new scene loads one image at a time; no ending gallery is loaded during investigation.

Validation: `node --test frontend/art.test.mjs frontend/chat.test.mjs` and `python -m pytest -m "not llm"`. Browser smoke checks cover scene changes, evidence inspection, journal artwork and layout.
