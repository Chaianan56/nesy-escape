"""Gemini must know what an examined object revealed, or "ไอนั่นจากศพ" grounds to the body itself."""
from app.cases import get_engine
from app.game_setup import new_game_state
from app.neural.prompts import build_interpret_system_prompt

CASE = 'case_01_gideon'


def _object_line(prompt, oid):
    return next(line for line in prompt.splitlines() if f"ID: '{oid}'" in line)


def _prompt(examined):
    world = get_engine(CASE).world
    state = new_game_state(world, CASE).model_copy(
        update={'current_location': 'first_class_car', 'examined_objects': examined})
    return build_interpret_system_prompt(world, state=state, user_text='เก็บไอนั่นจากศพขึ้นมาดู', use_knn=False)


def test_items_revealed_by_the_body_say_where_they_were_found():
    prompt = _prompt(['cassian_reed'])
    for oid in ('pocket_watch', 'obsidian_cufflink'):
        assert "พบที่: 'cassian_reed'" in _object_line(prompt, oid)


def test_repair_keeps_a_real_choice_between_two_items_in_the_room():
    """Gemini answers ambiguous [watch, button]; repair must not collapse it to the body
    just because the sentence says "ศพ"."""
    from app.neural.repair import repair_parsed_command
    from app.schemas import ActionType, ParsedCommand
    world = get_engine(CASE).world
    state = new_game_state(world, CASE).model_copy(
        update={'current_location': 'first_class_car', 'examined_objects': ['cassian_reed']})
    text = 'เก็บไอนั่นจากศพขึ้นมาดู'
    parsed = ParsedCommand(action=ActionType.AMBIGUOUS, raw_text=text,
                           alternatives=['pocket_watch', 'obsidian_cufflink'])
    repaired, _ = repair_parsed_command(parsed, world, state=state, raw_text=text)
    assert repaired.action == ActionType.AMBIGUOUS
    assert repaired.alternatives == ['pocket_watch', 'obsidian_cufflink']


def test_prompt_tells_the_model_what_players_call_car_4():
    """From car 6, "พาผมไปห้องคุณรีด" came back ambiguous: nothing linked Reed's room to car 4."""
    for case in ('case_01_gideon', 'case_02_vincent', 'case_03_liora'):
        world = get_engine(case).world
        state = new_game_state(world, case).model_copy(update={'current_location': 'second_class_car'})
        prompt = build_interpret_system_prompt(world, state=state, user_text='พาผมไปห้องคุณรีด', use_knn=False)
        line = next(l for l in prompt.splitlines() if "ID: 'first_class_car'" in l)
        assert 'ห้องคุณรีด' in line, case


def test_found_on_stays_hidden_until_the_parent_is_examined():
    """Listing it earlier would tell the player what the body holds before they look."""
    prompt = _prompt([])
    assert 'พบที่' not in _object_line(prompt, 'pocket_watch')
