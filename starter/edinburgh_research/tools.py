"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking.

Each tool:
  1. Reads its fixture from sample_data/ (DO NOT modify the fixtures).
  2. Logs its arguments and output into _TOOL_CALL_LOG (see integrity.py).
  3. Returns a ToolResult with success=True/False, output=dict, summary=str.

The grader checks for:
  * Correct parallel_safe flags (reads True, generate_flyer False).
  * Every tool's results appear in _TOOL_CALL_LOG.
  * Tools fail gracefully on missing fixtures or bad inputs (ToolError,
    not RuntimeError).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from sovereign_agent.errors import ToolError
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

from starter.edinburgh_research.integrity import record_tool_call

_SAMPLE_DATA = Path(__file__).parent / "sample_data"


def _load_fixture(name: str) -> object:
    """Load a JSON fixture from sample_data/.

    Raises ToolError(SA_TOOL_DEPENDENCY_MISSING) if the file is missing
    or unreadable — that's a configuration problem, not a tool bug.
    """
    path = _SAMPLE_DATA / name
    if not path.exists():
        raise ToolError(
            code="SA_TOOL_DEPENDENCY_MISSING",
            message=f"fixture {name!r} not found at {path}",
            context={"fixture": name, "path": str(path)},
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError(
            code="SA_TOOL_DEPENDENCY_MISSING",
            message=f"fixture {name!r} is not valid JSON: {exc}",
            context={"fixture": name, "path": str(path)},
            cause=exc,
        ) from exc


# ---------------------------------------------------------------------------
# TODO 1 — venue_search
# ---------------------------------------------------------------------------
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search for Edinburgh venues near <near> that can seat the party."""
    venues = _load_fixture("venues.json")

    near_lc = (near or "").strip().lower()
    results: list[dict] = []
    for v in venues:
        if not v.get("open_now"):
            continue
        area = str(v.get("area", "")).lower()
        if near_lc and near_lc not in area:
            continue
        if v.get("seats_available_evening", 0) < party_size:
            continue
        floor = v.get("hire_fee_gbp", 0) + v.get("min_spend_gbp", 0)
        if floor > budget_max_gbp:
            continue
        results.append(v)

    output = {
        "near": near,
        "party_size": party_size,
        "budget_max_gbp": budget_max_gbp,
        "results": results,
        "count": len(results),
    }
    summary = f"venue_search({near}, party={party_size}): {len(results)} result(s)"

    record_tool_call(
        "venue_search",
        {"near": near, "party_size": party_size, "budget_max_gbp": budget_max_gbp},
        output,
    )
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 2 — get_weather
# ---------------------------------------------------------------------------
def get_weather(city: str, date: str) -> ToolResult:
    """Look up the scripted weather for <city> on <date> (YYYY-MM-DD)."""
    weather = _load_fixture("weather.json")

    city_key = (city or "").strip().lower()
    args = {"city": city, "date": date}

    if city_key not in weather:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"no weather data for city {city!r}",
            context={"city": city, "available_cities": sorted(weather.keys())},
        )
        output = {"city": city, "date": date, "error": err.message}
        record_tool_call("get_weather", args, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"get_weather({city}, {date}): unknown city",
            error=err,
        )

    city_data = weather[city_key]
    if date not in city_data:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"no weather data for {city!r} on {date!r}",
            context={"city": city, "date": date, "available_dates": sorted(city_data.keys())},
        )
        output = {"city": city, "date": date, "error": err.message}
        record_tool_call("get_weather", args, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"get_weather({city}, {date}): unknown date",
            error=err,
        )

    record = city_data[date]
    output = {
        "city": city,
        "date": date,
        "condition": record["condition"],
        "temperature_c": record["temperature_c"],
        "precip_mm": record.get("precip_mm"),
        "wind_kph": record.get("wind_kph"),
    }
    summary = f"get_weather({city}, {date}): {record['condition']}, {record['temperature_c']}C"
    record_tool_call("get_weather", args, output)
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 3 — calculate_cost
# ---------------------------------------------------------------------------
def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    """Compute the total cost for a booking."""
    catering = _load_fixture("catering.json")
    venues = _load_fixture("venues.json")

    args = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
    }

    base_rates = catering["base_rates_gbp_per_head"]
    if catering_tier not in base_rates:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"unknown catering_tier {catering_tier!r}",
            context={"catering_tier": catering_tier, "available": sorted(base_rates.keys())},
        )
        output = {"venue_id": venue_id, "error": err.message}
        record_tool_call("calculate_cost", args, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"calculate_cost({venue_id}): bad catering_tier",
            error=err,
        )

    venue_mods = catering["venue_modifiers"]
    if venue_id not in venue_mods:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"unknown venue_id {venue_id!r}",
            context={"venue_id": venue_id, "available": sorted(venue_mods.keys())},
        )
        output = {"venue_id": venue_id, "error": err.message}
        record_tool_call("calculate_cost", args, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"calculate_cost({venue_id}): unknown venue",
            error=err,
        )

    venue_row = next((v for v in venues if v["id"] == venue_id), None)
    if venue_row is None:
        err = ToolError(
            code="SA_TOOL_DEPENDENCY_MISSING",
            message=f"venue_id {venue_id!r} listed in catering modifiers but missing from venues.json",
            context={"venue_id": venue_id},
        )
        output = {"venue_id": venue_id, "error": err.message}
        record_tool_call("calculate_cost", args, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"calculate_cost({venue_id}): venue not found",
            error=err,
        )

    base_per_head = base_rates[catering_tier]
    venue_mult = venue_mods[venue_id]
    eff_hours = max(1, int(duration_hours))
    subtotal = base_per_head * venue_mult * party_size * eff_hours

    service_pct = catering.get("service_charge_percent", 10)
    service = subtotal * service_pct / 100.0

    floor = venue_row.get("hire_fee_gbp", 0) + venue_row.get("min_spend_gbp", 0)
    total = subtotal + service + floor

    # Deposit policy thresholds.
    if total < 300:
        deposit = 0
    elif total <= 1000:
        deposit = total * 0.20
    else:
        deposit = total * 0.30

    # Round to whole £ (sample expected output uses ints).
    subtotal_i = int(round(subtotal))
    service_i = int(round(service))
    total_i = int(round(total))
    deposit_i = int(round(deposit))

    output = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
        "subtotal_gbp": subtotal_i,
        "service_gbp": service_i,
        "hire_fee_gbp": venue_row.get("hire_fee_gbp", 0),
        "min_spend_gbp": venue_row.get("min_spend_gbp", 0),
        "total_gbp": total_i,
        "deposit_required_gbp": deposit_i,
    }
    summary = f"calculate_cost({venue_id}, {party_size}): total £{total_i}, deposit £{deposit_i}"
    record_tool_call("calculate_cost", args, output)
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 4 — generate_flyer
# ---------------------------------------------------------------------------
def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    """Produce an HTML flyer and write it to workspace/flyer.html."""
    if not isinstance(event_details, dict):
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message="event_details must be a dict",
            context={"got_type": type(event_details).__name__},
        )
        output = {"error": err.message}
        record_tool_call("generate_flyer", {"event_details": event_details}, output)
        return ToolResult(
            success=False, output=output, summary="generate_flyer: bad input", error=err
        )

    def _g(key: str, default: str = "") -> str:
        v = event_details.get(key, default)
        return "" if v is None else str(v)

    venue_name = _g("venue_name", "Edinburgh Venue")
    venue_address = _g("venue_address")
    date_s = _g("date")
    time_s = _g("time")
    party_size = _g("party_size")
    condition = _g("condition")
    temperature_c = _g("temperature_c")
    total_gbp = _g("total_gbp")
    deposit_gbp = _g("deposit_required_gbp")

    e = html.escape

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{e(venue_name)} — Booking Flyer</title>
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 640px;
         margin: 2em auto; color: #222; line-height: 1.45; }}
  h1   {{ color: #6b1d3a; margin-bottom: 0.2em; }}
  h2   {{ color: #6b1d3a; margin-top: 1.5em; font-size: 1.1em; }}
  dl   {{ display: grid; grid-template-columns: max-content 1fr;
          gap: 0.3em 1em; }}
  dt   {{ font-weight: 600; color: #555; }}
  dd   {{ margin: 0; }}
  .footer {{ margin-top: 2em; font-size: 0.85em; color: #888; }}
</style>
</head>
<body>
  <h1 data-testid="venue_name">{e(venue_name)}</h1>
  <p><span data-testid="venue_address">{e(venue_address)}</span></p>

  <h2>Event</h2>
  <dl>
    <dt>Date</dt><dd><span data-testid="date">{e(date_s)}</span></dd>
    <dt>Time</dt><dd><span data-testid="time">{e(time_s)}</span></dd>
    <dt>Party size</dt><dd><span data-testid="party_size">{e(party_size)}</span></dd>
  </dl>

  <h2>Weather</h2>
  <dl>
    <dt>Condition</dt><dd><span data-testid="condition">{e(condition)}</span></dd>
    <dt>Temperature</dt><dd><span data-testid="temperature_c">{e(temperature_c)}C</span></dd>
  </dl>

  <h2>Cost</h2>
  <dl>
    <dt>Total</dt><dd><span data-testid="total">£{e(total_gbp)}</span></dd>
    <dt>Deposit</dt><dd><span data-testid="deposit">£{e(deposit_gbp)}</span></dd>
  </dl>

  <p class="footer">Generated by sovereign-agent for the Edinburgh research scenario.</p>
</body>
</html>
"""

    workspace = session.workspace_dir
    workspace.mkdir(parents=True, exist_ok=True)
    flyer_path = workspace / "flyer.html"
    bytes_written = flyer_path.write_text(html_doc, encoding="utf-8")

    output = {
        "path": "workspace/flyer.html",
        "absolute_path": str(flyer_path),
        "bytes_written": bytes_written,
    }
    summary = f"generate_flyer: wrote workspace/flyer.html ({bytes_written} chars)"
    record_tool_call("generate_flyer", {"event_details": event_details}, output)
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# Registry builder — DO NOT MODIFY the name, signature, or registration calls.
# The grader imports and calls this to pick up your tools.
# ---------------------------------------------------------------------------
def build_tool_registry(session: Session) -> ToolRegistry:
    """Build a session-scoped tool registry with all four Ex5 tools plus
    the sovereign-agent builtins (read_file, write_file, list_files,
    handoff_to_structured, complete_task).

    DO NOT change the tool names — the tests and grader call them by name.
    """
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session)

    # venue_search
    reg.register(
        _RegisteredTool(
            name="venue_search",
            description="Search Edinburgh venues by area, party size, and max budget.",
            fn=venue_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "budget_max_gbp": {"type": "integer", "default": 1000},
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )

    # get_weather
    reg.register(
        _RegisteredTool(
            name="get_weather",
            description="Get scripted weather for a city on a YYYY-MM-DD date.",
            fn=get_weather,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    # calculate_cost
    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description="Compute total cost and deposit for a booking.",
            fn=calculate_cost,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "catering_tier": {
                        "type": "string",
                        "enum": ["drinks_only", "bar_snacks", "sit_down_meal", "three_course_meal"],
                        "default": "bar_snacks",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # pure compute, no shared state
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    # generate_flyer — parallel_safe=False because it writes a file
    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description="Write an HTML flyer for the event to workspace/flyer.html.",
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {"event_details": {"type": "object"}},
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,  # writes a file — MUST be False
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "date": "2026-04-25",
                            "party_size": 6,
                        }
                    },
                    "output": {"path": "workspace/flyer.html"},
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
