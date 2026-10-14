"""Create a fresh state from the authored opening, without sharing mutable lists."""
import json
from pathlib import Path

from app.schemas import GameState


def new_game_state(world=None):
    if world is None:
        world = json.loads((Path(__file__).resolve().parents[1] / "data/story.json").read_text(encoding="utf-8"))
    return GameState.model_validate(world.get("initial_state", {})).model_copy(deep=True)
