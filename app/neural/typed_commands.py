"""Exact typed shortcuts only; free-form or ambiguous text still goes to Neural."""
import re
from app.schemas import ActionType, ParsedCommand


def parse_typed_command(text, state, world):
    value = text.strip()
    def command(action, target, **extra):
        return ParsedCommand(action=action, target=target, raw_text=text, confidence=1.0, **extra)
    def resolve(label, groups):
        matches = set()
        for group in groups:
            for key, entity in world.get(group, {}).items():
                name = entity.get('name_th', '')
                aliases = {key, name, name.split(' (')[0], *entity.get('aliases', [])}
                if group == 'suspects':
                    aliases.add(name.split(' (')[0].replace('ดร. ', '').split()[0])
                if label.strip() in aliases:
                    matches.add(key)
        return next(iter(matches)) if len(matches) == 1 else None
    if value in ('ดูรอบๆ', 'ดูรอบ ๆ', 'มองรอบๆ', 'สำรวจห้อง'):
        return command(ActionType.EXAMINE, state.current_location)
    # "<action> <id>" ที่หน้าเว็บส่งมาทีละขั้นของคำสั่งพ่วง ไม่ต้องถาม Gemini ซ้ำ
    parts = value.split()
    if len(parts) == 2 and parts[0] == 'infer' and parts[1] in world.get('claims', {}):
        return command(ActionType.INFER, parts[1])
    if len(parts) == 3:
        action, target, argument = parts
        if action == 'interrogate' and target in world['suspects']:
            return command(ActionType.INTERROGATE, target, topic=argument)
        if action == 'unlock' and target in world['objects']:
            return command(ActionType.UNLOCK, target, **({'code': argument} if argument.isdigit() else {'instrument': argument}))
        if action == 'use' and target in world['objects'] and argument in world['objects']:
            return command(ActionType.USE, target, instrument=argument)
    if (len(parts) == 2 and parts[0] in {'examine', 'take', 'move', 'interrogate', 'accuse', 'burn', 'unlock'}
            and any(parts[1] in world[g] for g in ('objects', 'suspects', 'locations'))):
        return command(ActionType(parts[0]), parts[1])
    match = re.fullmatch(r'(?:ไป|ไปที่|เดินไป|เดินไปที่)\s*ตู้\s*([1-6])', value)
    if match:
        locations = list(world['locations'])
        return command(ActionType.MOVE, locations[int(match[1])-1])
    match = re.fullmatch(r'(?:ถาม|สอบปากคำ|คุยกับ)\s*(.+?)\s+เรื่อง\s*(.+)', value)
    if match:
        person = resolve(match[1], ['suspects'])
        if person:
            topics = {node.get('topic'): node for node in world['suspects'][person].get('dialogue_nodes', [])}
            topic = next((key for key, node in topics.items() if match[2].strip() in {key, node.get('label'), node.get('name_th')}), None)
            if topic:
                return command(ActionType.INTERROGATE, person, topic=topic)
    match = re.fullmatch(r'(?:ปลดล็อก|เปิด)\s*(.+?)\s+(?:รหัส\s*)?(\d+)', value)
    if match:
        target = resolve(match[1], ['objects'])
        if target:
            return command(ActionType.UNLOCK, target, code=match[2])
    match = re.fullmatch(r'ใช้\s*(.+?)\s*(?:กับ|เพื่อเปิด)\s*(.+)', value)
    if match:
        instrument, target = resolve(match[1], ['objects']), resolve(match[2], ['objects'])
        if instrument and target:
            return command(ActionType.USE, target, instrument=instrument)
    prefixes = [('สอบปากคำ', ActionType.INTERROGATE, ['suspects']),
                ('คุยกับ', ActionType.INTERROGATE, ['suspects']),
                ('กล่าวหา', ActionType.ACCUSE, ['suspects']),
                ('ปลดล็อก', ActionType.UNLOCK, ['objects']),
                ('หยิบ', ActionType.TAKE, ['objects']),
                ('เก็บ', ActionType.TAKE, ['objects']),
                ('ตรวจสอบ', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
                ('ตรวจดู', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
                ('ตรวจ', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
                ('ไปที่', ActionType.MOVE, ['locations']),
                ('ไป', ActionType.MOVE, ['locations'])]
    for prefix, action, groups in prefixes:
        if not value.startswith(prefix):
            continue
        target_text = value[len(prefix):].strip()
        target = resolve(target_text, groups)
        if target:
            return command(action, target)
    return None


def interpret_game(text, state):
    from app.neural.gemini_client import STORY_DATA, interpret
    return parse_typed_command(text, state, STORY_DATA) or interpret(text, state)
