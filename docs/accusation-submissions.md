# Player-selected accusation evidence

The web accusation dialog lists discovered evidence and testimony, with nothing selected initially. Players can return to investigation or confirm their submission. A confirmation may end the case. Draft selections survive closing the dialog within the current page; reloading clears drafts.

`POST /command` accepts optional `submitted_evidence`. An accusation without a nonempty, unique subset of server-discovered evidence is rejected with `R_SUBMITTED_EVIDENCE`; the web client then opens the dialog. Other commands ignore this field. The existing session lock, command lock, and server clock remain authoritative.

The symbolic submission check first validates the full known case, so removing known exculpatory facts cannot bypass ending exclusions. It then evaluates the submitted subset under the existing rules. The original journal inventory is preserved. End-of-case deductions and pillar summaries use the submitted evidence; starting a new game clears it. CLI engine calls retain their existing behavior.

No new ending conditions or image integrations are introduced by this change.
