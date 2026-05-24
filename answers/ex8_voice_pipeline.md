# Ex8 — Voice pipeline

## Your answer

I ran Ex8 in `--text` mode (no Speechmatics, no Rime — both are paid
keys, and the voice contract does not actually depend on them).
Architecturally the pipeline has two modes sharing a single
trace-event contract: `voice` (microphone → Speechmatics STT →
ManagerPersona → Rime TTS → speaker) and `text` (stdin →
ManagerPersona → stdout). Both push the same events through
`session.append_trace_event()`: `user_input`, `manager_thinking`,
`manager_response`, `handoff_to_loop` — which is what
`test_text_mode_appends_trace_events` enforces.

`ManagerPersona` is a thin wrapper around an LLM (on Nebius the target
is `Llama-3.3-70B-Instruct`; my fallback is Yandex `yandexgpt`). Its
system prompt frames it as a venue manager running a short dialogue to
collect booking parameters — venue, date, time, party size, budget —
and *not* doing any math itself, but handing off to the loop half as
soon as it has enough. `test_manager_system_prompt_mentions_rules`
checks that those rules are actually baked into the prompt. This is a
clean separation: the LLM dialogue owns UX, loop+structured own facts
and validation, and voice is just a transport layer on top.

The key defensive piece is
`voice_mode_falls_back_when_no_speechmatics_key`. If the key is
missing, the pipeline does not crash — it silently downgrades to text
mode and writes `voice_unavailable` to the trace with a cause. That
matters both for passing CI without secrets, and personally for me —
I have no PortAudio on WSL at home, and without that fallback half the
tests would have been red on my box.

What I observed in text mode: the `_PLANNER_PROMPT` /
`_EXECUTOR_PROMPT` trick from the chat thread (the FabianTheFab fork)
genuinely helps the LLM avoid endless re-confirmation. Without it the
model over-clarifies obvious booking parameters on long sessions — the
same spiraling effect I hit with `make ex5-real`. In a voice scenario
that's especially visible because each extra manager turn is another
TTS call plus real latency for the user — so "chattiness" is not
cosmetic, it's a direct UX bug. On the rubric, text mode tops out at
16/20; the full 20/20 only opens up with real STT/TTS keys, and that
is a conscious trade-off on my side.

## Citations

- `sessions/sess_*_ex8/logs/trace.jsonl` — `user_input`,
  `manager_thinking`, `manager_response`, `handoff_to_loop` events
- `starter/voice_pipeline/manager_persona.py` — Nebius/Yandex
  provider switch and the persona prompt
- `tests/public/test_ex8_voice_pipeline.py` —
  `voice_mode_falls_back_when_no_speechmatics_key`
