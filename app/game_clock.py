"""Wall-clock time belongs to the interaction layer, not the rule engine."""
import time

from app.schemas import GameState


def sync_clock(state: GameState) -> GameState:
    if state.ending_id or state.started_at is None:
        return state
    elapsed = max(state.elapsed_seconds, int(time.time() - state.started_at), 0)
    return state.model_copy(update={"elapsed_seconds": elapsed})
