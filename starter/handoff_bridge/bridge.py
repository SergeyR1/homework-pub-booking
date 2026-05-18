"""Ex7 — handoff bridge.

Routes between the loop half and the Rasa-backed structured half,
supporting REVERSE handoffs (structured → loop) when the structured
half rejects.

The base sovereign-agent LoopHalf only knows how to request a handoff
FORWARD. The bridge you're building here is the thing that decides
what to do when the structured half says "no, go back and try again".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sovereign_agent.halves import HalfResult
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.halves.structured import StructuredHalf
from sovereign_agent.handoff import Handoff
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc

BridgeOutcome = Literal["completed", "failed", "max_rounds_exceeded"]


@dataclass
class BridgeResult:
    outcome: BridgeOutcome
    rounds: int
    final_half_result: HalfResult | None
    summary: str


class HandoffBridge:
    """Orchestrates round-trips between LoopHalf and a StructuredHalf.

    Not a sovereign-agent Half itself — it lives one level up, deciding
    which half should run next.
    """

    def __init__(
        self,
        *,
        loop_half: LoopHalf,
        structured_half: StructuredHalf,
        max_rounds: int = 3,
    ) -> None:
        self.loop_half = loop_half
        self.structured_half = structured_half
        self.max_rounds = max_rounds

    # ------------------------------------------------------------------
    # TODO — the main run method
    # ------------------------------------------------------------------
    async def run(self, session: Session, initial_task: dict) -> BridgeResult:
        """Run the bridge until the session completes, fails, or hits max_rounds."""
        from sovereign_agent.handoff import write_handoff

        rounds = 0
        current_input: dict = initial_task
        last_loop: HalfResult | None = None
        last_struct: HalfResult | None = None

        while rounds < self.max_rounds:
            rounds += 1

            # --- ROUND START ---
            session.append_trace_event(
                {
                    "event_type": "bridge.round_start",
                    "actor": "bridge",
                    "payload": {"round": rounds, "half": "loop"},
                }
            )

            # --- RUN LOOP HALF ---
            loop_result = await self.loop_half.run(session, current_input)
            last_loop = loop_result

            if loop_result.next_action == "complete":
                session.mark_complete(loop_result.output)
                session.append_trace_event(
                    {
                        "event_type": "session.state_changed",
                        "actor": "bridge",
                        "payload": {
                            "from": "executing",
                            "to": "complete",
                            "via": "loop",
                            "round": rounds,
                        },
                    }
                )
                return BridgeResult(
                    outcome="completed",
                    rounds=rounds,
                    final_half_result=loop_result,
                    summary=loop_result.summary,
                )

            if loop_result.next_action != "handoff_to_structured":
                session.mark_failed(
                    {
                        "reason": f"loop half returned unexpected next_action={loop_result.next_action!r}"
                    }
                )
                return BridgeResult(
                    outcome="failed",
                    rounds=rounds,
                    final_half_result=loop_result,
                    summary=loop_result.summary,
                )

            # --- FORWARD HANDOFF ---
            handoff = build_forward_handoff(session, loop_result)
            write_handoff(session, "structured", handoff)
            session.append_trace_event(
                {
                    "event_type": "session.state_changed",
                    "actor": "bridge",
                    "payload": {
                        "from": "loop",
                        "to": "structured",
                        "round": rounds,
                    },
                }
            )

            # --- RUN STRUCTURED HALF ---
            struct_result = await self.structured_half.run(session, {"data": handoff.data})
            last_struct = struct_result

            if struct_result.next_action == "complete":
                session.mark_complete(struct_result.output)
                session.append_trace_event(
                    {
                        "event_type": "session.state_changed",
                        "actor": "bridge",
                        "payload": {
                            "from": "structured",
                            "to": "complete",
                            "via": "structured",
                            "round": rounds,
                        },
                    }
                )
                return BridgeResult(
                    outcome="completed",
                    rounds=rounds,
                    final_half_result=struct_result,
                    summary=struct_result.summary,
                )

            if struct_result.next_action == "escalate":
                current_input = build_reverse_task(loop_result, struct_result)
                rejection_reason = struct_result.output.get("reason") or struct_result.summary
                session.append_trace_event(
                    {
                        "event_type": "session.state_changed",
                        "actor": "bridge",
                        "payload": {
                            "from": "structured",
                            "to": "loop",
                            "round": rounds,
                            "rejection_reason": rejection_reason,
                        },
                    }
                )

                # Archive the consumed forward handoff so the next round
                # starts with a clean ipc_input_dir.
                forward_file = session.ipc_input_dir / "handoff_to_structured.json"
                if forward_file.exists():
                    archive_dir = session.handoffs_audit_dir
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    archive_path = archive_dir / f"round_{rounds}_forward.json"
                    forward_file.replace(archive_path)

                continue

            # Unknown structured action — fail.
            session.mark_failed(
                {
                    "reason": f"structured half returned unexpected next_action={struct_result.next_action!r}"
                }
            )
            return BridgeResult(
                outcome="failed",
                rounds=rounds,
                final_half_result=struct_result,
                summary=struct_result.summary,
            )

        # --- LOOP EXHAUSTION ---
        session.mark_failed({"reason": f"max_rounds={self.max_rounds} exceeded"})
        return BridgeResult(
            outcome="max_rounds_exceeded",
            rounds=rounds,
            final_half_result=last_struct or last_loop,
            summary=f"bridge exhausted max_rounds={self.max_rounds}",
        )


# ---------------------------------------------------------------------------
# Helper constructors — you may use these or write your own
# ---------------------------------------------------------------------------
def build_forward_handoff(session: Session, loop_result: HalfResult) -> Handoff:
    """Package a loop result into a forward-handoff payload for structured."""
    return Handoff(
        from_half="loop",
        to_half="structured",
        written_at=now_utc(),
        session_id=session.session_id,
        reason="loop-half requested confirmation",
        context=loop_result.summary,
        data=(loop_result.handoff_payload or {}).get("data") or loop_result.output,
        return_instructions=(
            "If you cannot confirm (party too large, deposit too high, etc.), "
            "respond with next_action=escalate and include a human-readable "
            "'reason' in output so the loop half can adapt."
        ),
    )


def build_reverse_task(loop_result: HalfResult, struct_result: HalfResult) -> dict:
    """Build the task dict to pass back to the loop half after a reject."""
    reason = struct_result.output.get("reason") or struct_result.summary
    return {
        "task": (
            "The structured half rejected the previous proposal. "
            f"Reason: {reason}. Produce an alternative."
        ),
        "context": {
            "prior_result": loop_result.output,
            "rejection_reason": reason,
            "retry": True,
        },
    }


__all__ = [
    "BridgeOutcome",
    "BridgeResult",
    "HandoffBridge",
    "build_forward_handoff",
    "build_reverse_task",
]
