# Ex5 — Edinburgh research loop scenario

## Your answer

In my run (`session sess_a7be4330d569`, FakeLLMClient, offline mode) the
planner split the task into two subgoals: `sg_1` — collect the Haymarket
venue, weather, and cost facts; and `sg_2` — emit an HTML flyer from
those facts. The decomposition is visible in the trace as a sequence of
tickets — `planner.plan`, `executor.run_subgoal/sg_1`,
`executor.run_subgoal/sg_2` — and all three closed with `status=success`.

In `sg_1` the executor issued three read-only calls in a single parallel
batch: `venue_search`, `get_weather`, `calculate_cost`. That's exactly
right, because all three are registered with `parallel_safe=True` — they
only read JSON fixtures and do arithmetic, and they touch no shared
state. In `sg_2` the executor called `generate_flyer`, which is
deliberately serialised (`parallel_safe=False`) because it writes a file
into `session.workspace_dir`. That's a write op, and you cannot let it
race with itself or with another writer without risking a torn or
overwritten flyer.

Every one of the four tools calls
`record_tool_call(name, arguments, output)` from `integrity.py` before
it returns. That single contract is what the dataflow check stands on:
`verify_dataflow` walks the flyer text, extracts money figures,
temperatures, and weather labels with regexes, and for each fact asks
`fact_appears_in_log` whether some `_TOOL_CALL_LOG` entry already saw
it — in `output` or in `arguments`. My run came back clean:
`dataflow OK: verified 4 fact(s) against tool outputs` — `cloudy`, `12`
(°C), `£540`, `£0`. If I had written, say, `£9999` into the HTML,
`verify_dataflow` would have returned `ok=False` with that number in
`unverified_facts` — exactly the scenario covered by
`test_verify_dataflow_catches_obvious_fabrication`.

For robustness I separated two failure modes on purpose. A missing or
corrupted fixture file raises `ToolError(SA_TOOL_DEPENDENCY_MISSING)` —
that's a configuration bug, the executor should crash loudly. Unknown
city, date, venue, or catering tier is `success=False` with
`SA_TOOL_INVALID_INPUT`, no exception — the LLM gets a structured
message back and can retry with corrected arguments. Either way I still
call `record_tool_call` before returning, otherwise the recovery
attempt would silently drop out of the trace.

## Citations

- `sessions/sess_a7be4330d569/logs/trace.jsonl` — planner.plan,
  executor.run_subgoal, dataflow_check_passed
- `sessions/sess_a7be4330d569/workspace/flyer.html` — the verified
  output
- `starter/edinburgh_research/integrity.py:99` — `fact_appears_in_log`
  scans both `output` and `arguments` recursively
