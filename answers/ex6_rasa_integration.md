# Ex6 — Rasa structured half

## Your answer

In my run of `make ex6` (`session sess_6ed8a66a7f78`, tier 1 — stdlib
mock on `127.0.0.1:5905/webhooks/rest/webhook`), `RasaStructuredHalf`
built a clean booking payload and handed it to the mock server, which
returned `Booking confirmed. Reference: BK-7D401E9E.` The final object
from the trace: `committed=True`, `booking={venue_id: haymarket_tap,
date: 2026-04-25, time: 19:30, party_size: 6, deposit_gbp: 200,
duration_hours: 3, catering_tier: bar_snacks}`,
`booking_reference=BK-7D401E9E`.

Structurally `structured_half.py` does three things. First — input
normalisation for whatever the loop half throws at it: `parse_currency_gbp`
accepts `"£540"`, `"540"`, `"540.00"` but rejects negatives via the
`SA_VAL` error code; `parse_time_24h` collapses `"19:30"`, `"7:30 PM"`,
and `"19.30"` to a single `HH:MM`; `parse_party_size` drops zero and
negatives; `canonicalise_venue_id` maps both `"Haymarket Tap"` and
`"haymarket-tap"` to `haymarket_tap`. After that
`normalise_booking_payload` assembles the dict exactly in the shape
Rasa expects — which is what
`test_normalise_booking_payload_produces_rasa_shape` enforces.

Second — the actual Rasa call. A `POST` to `/webhooks/rest/webhook`
with `{"sender": <session_id>, "message": "/start_booking" + payload}`,
parsing of the response, search for `custom.action` ∈ `{committed,
rejected, needs_clarification}`, and a boolean
`committed=True/False` returned upward. The bot side lives in
`rasa_project/`: `flows.yml` declares a `confirm_booking` flow, and the
custom action `ActionValidateBooking` does the final business check —
`party_size ≤ 8` (that's `maximum_party_size_for_auto_booking` from
`catering.json`) and `deposit_gbp ≤ 300`. Anything that fails either
rule comes back as `rejected` with a human-readable reason — large
parties and expensive deals escalate to a manager instead of
auto-confirming.

Third — and this is the part I like most — the separation of concerns.
The loop half (LLM) is free to "imagine" what to book; the structured
half (Rasa) deterministically checks that the booking sits inside the
rules and only then commits. The LLM proposes, the deterministic layer
disposes. Fabrications like `party=20` or `deposit=£900` are bounced at
`validate_booking` and never reach `committed=True` — exactly the
contract that closes the failure modes from Ex5.

## Citations

- `sessions/sess_6ed8a66a7f78/logs/trace.jsonl` — rasa.request, the
  custom action payload, and the final `committed=True`
- `rasa_project/actions/actions.py` — `ActionValidateBooking` with the
  party-size and deposit caps
- `starter/rasa_half/structured_half.py` — payload normalisation and
  the `/webhooks/rest/webhook` call
