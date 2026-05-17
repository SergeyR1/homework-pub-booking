# Ex7 — Handoff bridge

## Your answer

In my run (`session sess_8f3378c46281`, `make ex7`) the bridge closed
with `outcome=completed`, `rounds=2`, and
`summary: structured confirmed in round 2`. That is — the structured
side honestly rejected in round 1, and only accepted in round 2 after
the loop half corrected the input.

`HandoffBridge` runs a bidirectional round-trip between loop and
structured. Flat loop view: the loop assembles a draft booking →
`build_forward_handoff` folds it into a handoff object carrying
`session_id`, `subgoal_id`, `payload`, and `attempt`, and drops it into
`session.handoffs_audit_dir/`. The structured side picks it up, runs
validation, and either commits (`committed=True` — the whole bridge
finishes) or replies `rejected` with a machine-readable `reason`. On
rejection `build_reverse_task` builds a reverse subgoal for the loop —
it pins down the specific field and the cause (e.g.
`"deposit_gbp=900 exceeds 300 cap"`), bumps `attempt`, and the loop
receives a follow-up subgoal of the form "fix this, retry". The loop
is capped at `max_rounds=3` — an explicit "correction budget", after
which the bridge returns `outcome=escalated_to_human`, writes a ticket
into `tickets_dir`, and `session.mark_escalated()` stamps the final
status.

What I like about the bridge as a pattern: it makes explicit the things
usually smeared across the trace — where the model hallucinated, where
the deterministic layer chopped it down, what exactly was chopped, and
how many recovery attempts the LLM has left. Without that budget a
weakly-grounded LLM can stall in an infinite correction loop (I saw
that effect in `make ex5-real` — without a custom `_PLANNER_PROMPT`,
the model spirals on subgoal #2). A hard cap of three rounds plus
explicit escalation is the "structural safety net" around the
non-deterministic component that the hybrid-agent lectures keep
emphasising.

One more detail that mattered to me: the integrity check propagates
into this layer too. `handoff_bridge/integrity.py` treats every value
inside the payload as something that must be verifiable against the
tool log from Ex5. If the loop tries to "add its own" field that no
`record_tool_call` ever produced, the bridge catches it *before* Rasa
ever sees the booking — fabrications are cut at the boundary between
the two halves of the agent, not on the way out the door.

## Citations

- `sessions/sess_8f3378c46281/handoffs_audit/` — two forward handoffs
  (round 1: rejected, round 2: committed) plus the reverse task
- `sessions/sess_8f3378c46281/logs/trace.jsonl` — `bridge.round`
  events with rounds counter
- `starter/handoff_bridge/bridge.py` — the `max_rounds=3` cap and
  `escalate_to_human` path
