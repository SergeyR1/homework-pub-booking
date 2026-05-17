# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In my Ex7 run (`session sess_8f3378c46281`) the bridge closed with
`rounds=2, summary: structured confirmed in round 2`. That means the
planner correctly split the work: the research subgoal stayed on the
loop half, while the "commit the booking under venue policy" decision
went to the structured half — exactly where `ActionValidateBooking`
deterministically checks `party_size ≤ 8` and `deposit_gbp ≤ 300`. The
signal that drove `DefaultPlanner` toward this routing is visible in
the loop task itself: phrases like "policy rules", "commit", "under
the deposit cap" are the triggers that the planner's system prompt
maps to `assigned_half: "structured"`.

What hooked me here is the *advisory* nature of the decision. The
planner only recommends who should execute a subgoal. If the
structured half were absent in my setup (the way the `research_assistant`
scenario from week 3 ships), such a subgoal would fall into the void,
and the orchestrator would hit failure mode #4 from the lectures.
Round 1 in my run is exactly that story: the loop first proposed a
booking with a formally-shaped but business-illegal deposit; the
bridge bounced it through `build_reverse_task` with a reason, and only
in round 2, after the deposit was corrected, did the structured side
respond `committed=True, BK-7D401E9E`.

The take-away that stuck with me: LLM prose interpretation is an
unreliable architectural seam. Rules cannot live in task wording —
they have to be encoded in the structured half's Python
(`validator.py`, `ActionValidateBooking`). Then even if the planner
mis-assigns the subgoal, the booking *physically cannot pass*
validation with bad numbers. That's the "defense in depth" idea from
the hybrid-agent lecture.

### Citation

- `sessions/sess_8f3378c46281/logs/trace.jsonl` — events `planner.plan`,
  `bridge.round`
- `sessions/sess_8f3378c46281/handoffs_audit/` — two forward handoffs
  (round 1 rejected, round 2 committed)
- `rasa_project/actions/actions.py:ActionValidateBooking`

---

## Q2 — Dataflow integrity catch

### Your answer

In my final Ex5 run (`session sess_a7be4330d569`) the integrity check
returned `dataflow OK: verified 4 fact(s) against tool outputs` —
confirmed `cloudy`, `12` (°C), `£540`, `£0`. So that I'm not describing
the happy path in the abstract, I deliberately seeded a noisy negative
case during debugging: I hand-edited the generated `workspace/flyer.html`
and replaced `£540` with `£9999` (the exact example the course README
recommends), then re-ran `verify_dataflow` against the modified file.

The result: `ok=False`, `unverified_facts=['9999']`,
`summary: dataflow FAIL: 1 unverified fact(s): ['9999']`. What's
genuinely interesting here is *why* this check catches what a human
skips. `verify_dataflow` does not ask whether a number "looks
plausible" — it compares against ground truth in `_TOOL_CALL_LOG`,
which is exactly what every one of the four tools wrote into via
`record_tool_call`. If a value was never produced by any tool — even
if it "looks" right and the arithmetic happens to match — it is, by
definition, a fabrication.

This is the direct answer to the risk emphasised in the agent-systems
lectures: LLMs generate *plausible* numbers, and a human reviewer
cannot tell them apart from real ones on a quick read. The only
reliable filter is comparison against the tool journal. That is why in
all four of my tool implementations I call `record_tool_call(...)`
*before* `return`, on both branches — `success=True` and
`success=False`. Otherwise a recovery attempt (e.g. a bad date in
`get_weather`) would drop out of the trace, and the LLM could later
cite "data it received" that the log never witnessed.

### Citation

- `sessions/sess_a7be4330d569/logs/trace.jsonl` —
  `dataflow_check_passed`
- `starter/edinburgh_research/integrity.py:99`
  (`fact_appears_in_log`) — recursive scan of both `output` and
  `arguments`
- `README.md` — the canonical `£540 → £9999` example used as the
  negative test

---

## Q3 — Removing one framework primitive

### Your answer

If I had to drop one of the five architectural decisions of
sovereign-agent and rebuild the rest, **session directories** are the
one I would leave untouched. They are the framework's git commit:
from a session directory you can recover anything else; from anything
else you cannot recover the session.

The argument in reverse. The forward-only state machine (Decision 2)
matters, but is useless without a place to store the transitions — and
that place is `session.directory`. Tickets (Decision 3) I can
reconstruct as `.jsonl` inside `session/tickets/` without breaking
the contract. The atomic-rename IPC (Decision 5) is replaceable by
polling `session/ipc_input/` with `os.rename` — slower, same
semantics. The tool registry (Decision 4) is the most algorithmic of
the five, and its core fits in a single file; I'd rewrite it in an
evening, the way I rewrote `build_tool_registry` for Ex5.

Now consider removing session directories. First — isolation: today
`Session.path()` physically blocks escape via `SessionEscapeError`;
without that encapsulating layer, sibling sessions start to see each
other because workspaces merge. Second — debugging turns into SQL
archaeology: today the answer to "how did this booking reach commit"
is `cd sessions/sess_8f3378c46281 && cat handoffs_audit/*`, and I see
all three rounds at a glance; without directories those events smear
across a single central log with cursor navigation. Third — the Ex5
integrity check falls apart: `_TOOL_CALL_LOG` lives in process memory,
but the flyer *workspace* is on disk under the session, and the whole
meaning of "fact-in-file equals entry-in-log" depends on both sides
sharing one path.

So session directories are the commit hash for the rest of the system.
From a commit you can recover diff, blame, merge; from the rest you
cannot recover the commit. If I had to sacrifice something, I'd
sacrifice the atomic-rename IPC (Decision 5) — the "directory-indicator
+ polling" pattern is fine without atomicity wherever eventual
consistency is enough.

### Citation

- `sessions/sess_a7be4330d569/` — session directory layout the
  integrity check relies on
- `sessions/sess_8f3378c46281/handoffs_audit/` — example of how the
  directory makes round-trips debuggable
- `starter/edinburgh_research/tools.py` — `session.workspace_dir` as
  the flyer's write target
