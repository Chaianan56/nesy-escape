"""Exact typed shortcuts only; free-form or ambiguous text still goes to Neural."""
import re
from app.schemas import ActionType, ParsedCommand


def parse_typed_command(text, state, world):
    value = text.strip()
    def command(action, target):
        return ParsedCommand(action=action, target=target, raw_text=text, confidence=1.0)
    if value in ('ดูรอบๆ', 'ดูรอบ ๆ', 'มองรอบๆ', 'สำรวจห้อง'):
        return command(ActionType.EXAMINE, state.current_location)
    # "<action> <id>" ที่หน้าเว็บส่งมาทีละขั้นของคำสั่งพ่วง ไม่ต้องถาม Gemini ซ้ำ
    parts = value.split()
    if (len(parts) == 2 and parts[0] in {'examine', 'take', 'move', 'interrogate', 'accuse', 'burn', 'unlock'}
            and any(parts[1] in world[g] for g in ('objects', 'suspects', 'locations'))):
        return command(ActionType(parts[0]), parts[1])
    match = re.fullmatch(r'(?:ไป|ไปที่|เดินไป|เดินไปที่)\s*ตู้\s*([1-6])', value)
    if match:
        locations = list(world['locations'])
        return command(ActionType.MOVE, locations[int(match[1])-1])
    prefixes = [('สอบปากคำ', ActionType.INTERROGATE, ['suspects']),
                ('กล่าวหา', ActionType.ACCUSE, ['suspects']),
                ('ตรวจสอบ', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
                ('ตรวจดู', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
                ('ตรวจ', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
                ('ไปที่', ActionType.MOVE, ['locations']),
                ('ไป', ActionType.MOVE, ['locations'])]
    for prefix, action, groups in prefixes:
        if not value.startswith(prefix):
            continue
        target_text = value[len(prefix):].strip()
        matches = set()
        for group in groups:
            for key, entity in world[group].items():
                name = entity.get('name_th', '')
                aliases = {key, name, name.split(' (')[0]}
                if group == 'suspects':
                    aliases.add(name.split(' (')[0].replace('ดร. ', '').split()[0])
                if target_text and target_text in aliases:
                    matches.add(key)
        if len(matches) == 1:
            return command(action, matches.pop())
    return None


def interpret_game(text, state):
    from app.neural.gemini_client import STORY_DATA, interpret
    return parse_typed_command(text, state, STORY_DATA) or interpret(text, state)
