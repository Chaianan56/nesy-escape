"""Conservative offline commands; other free-form or ambiguous text goes to Neural."""
import re
from app.schemas import ActionType, ParsedCommand


def parse_typed_command(text, state, world):
    value = text.strip()
    def command(action, target, **extra):
        return ParsedCommand(
            action=action,
            target=target,
            raw_text=text,
            confidence=1.0,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0.05,
            parser_mode="typed",
            **extra,
        )
    def resolve(label, groups):
        clean = label.strip().lower()
        matches = set()
        for group in groups:
            for key, entity in world.get(group, {}).items():
                name = entity.get('name_th', '')
                en_name = ""
                if '(' in name and ')' in name:
                    en_name = name.split('(')[1].split(')')[0].strip().lower()
                aliases = {
                    key.lower(),
                    key.lower().replace('_', ' '),
                    name.lower(),
                    name.split(' (')[0].lower(),
                    *[str(a).lower() for a in entity.get('aliases', [])],
                }
                if en_name:
                    aliases.add(en_name)
                if group == 'suspects':
                    aliases.add(name.split(' (')[0].replace('ดร. ', '').split()[0].lower())
                    if en_name:
                        aliases.add(en_name.replace('dr. ', '').split()[0].lower())
                if clean in aliases:
                    matches.add(key)
        return next(iter(matches)) if len(matches) == 1 else None
    def resolve_carried_key(label):
        instrument = resolve(label, ['objects'])
        if instrument:
            return instrument
        if label.strip() not in ('กุญแจ', 'key'):
            return None
        carried_keys = [key for key in state.inventory
                        if world.get('objects', {}).get(key, {}).get('type') == 'key']
        return carried_keys[0] if len(carried_keys) == 1 else None
    def resolve_local_key_to_take(label):
        # Resolve a generic reference only when exactly one takeable key is
        # present in the current location. If there are multiple keys (or
        # visibility depends on hidden requirements), leave it to the model
        # rather than guessing.
        if label.strip() not in {'กุญแจ', 'กุญแจดอกนั้น', 'กุญแจที่วางอยู่'}:
            return None
        candidates = [key for key, entity in world.get('objects', {}).items()
                      if entity.get('type') == 'key'
                      and entity.get('location') == state.current_location
                      and 'take' in entity.get('supports', [])
                      and key not in state.inventory
                      and key not in state.burned_objects
                      and not entity.get('visible_requirements')]
        return candidates[0] if len(candidates) == 1 else None
    if value.lower() in ('ดูรอบๆ', 'ดูรอบ ๆ', 'มองรอบๆ', 'สำรวจห้อง', 'look around', 'look', 'search room', 'examine room'):
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
    match = re.fullmatch(r'(?:ไป|ไปที่|เดินไป|เดินไปที่|go to|move to|walk to)\s*(?:car|ตู้)\s*([1-6])', value, re.IGNORECASE)
    if match:
        locations = list(world['locations'])
        return command(ActionType.MOVE, locations[int(match[1])-1])
    # คำสั่งไปหาบุคคลที่รู้จักแปลเป็นการเดินทางไปยังตู้ที่บุคคลนั้นอยู่
    # คำว่า "หมอ" เป็นชื่อเรียกของดร. ลิโอราในเรื่อง จึงไม่ต้องเรียก Gemini
    match = re.fullmatch(r'(?:ไปหา|ไปพบ|go to|visit)\s*(.+)', value, re.IGNORECASE)
    if match:
        person_label = match[1].strip()
        person = resolve(person_label, ['suspects'])
        if person is None and person_label.lower() in {'หมอ', 'แพทย์', 'คุณหมอ', 'doctor', 'dr', 'dr.', 'dr. liora'}:
            person = 'dr_liora_venn' if 'dr_liora_venn' in world['suspects'] else None
        if person:
            destination = world['suspects'][person].get('location')
            if destination in world.get('locations', {}):
                return command(ActionType.MOVE, destination)
    match = re.fullmatch(r'(?:ถาม|สอบปากคำ|คุยกับ)\s*(.+?)\s+เรื่อง\s*(.+)', value)
    if not match:
        match = re.fullmatch(r'(?:ask|talk to|interrogate)\s*(.+?)\s+(?:about|on)\s*(.+)', value, re.IGNORECASE)
    if match:
        person = resolve(match[1], ['suspects'])
        if person:
            topics = {node.get('topic'): node for node in world['suspects'][person].get('dialogue_nodes', [])}
            topic = next((key for key, node in topics.items() if match[2].strip().lower() in {key.lower(), str(node.get('label', '')).lower(), str(node.get('name_th', '')).lower()}), None)
            if topic:
                return command(ActionType.INTERROGATE, person, topic=topic)
    match = re.fullmatch(r'(?:ปลดล็อก|เปิด|unlock|open)\s*(.+?)\s+(?:(?:รหัส|code)\s*)?(\d+)', value, re.IGNORECASE)
    if match:
        target = resolve(match[1], ['objects'])
        if target:
            return command(ActionType.UNLOCK, target, code=match[2])
    match = re.fullmatch(r'ใช้\s*(.+?)\s*(?:กับ|เพื่อเปิด)\s*(.+)', value)
    if match:
        instrument, target = resolve_carried_key(match[1]), resolve(match[2], ['objects'])
        if instrument and target:
            return command(ActionType.USE, target, instrument=instrument)
    # “ใช้กุญแจเปิดประตู...” เป็นรูปแบบธรรมชาติที่ไม่มีคำว่า “กับ” คั่น
    # จับคู่จากกุญแจที่ผู้เล่นพกอยู่เท่านั้น และไม่เดาเมื่อมีกุญแจหลายดอก
    if value.startswith('ใช้'):
        remainder = value[len('ใช้'):].lstrip()
        carried_keys = [key for key in state.inventory
                        if world.get('objects', {}).get(key, {}).get('type') == 'key']
        candidates = []
        for key in carried_keys:
            entity = world['objects'][key]
            candidates.extend((label, key) for label in {
                key, entity.get('name_th', ''), entity.get('name_th', '').split(' (')[0],
                *entity.get('aliases', []),
            } if label)
        if len(carried_keys) == 1:
            candidates.append(('กุญแจ', carried_keys[0]))
        for label, instrument in sorted(candidates, key=lambda pair: len(pair[0]), reverse=True):
            if not remainder.startswith(label):
                continue
            target_text = remainder[len(label):].lstrip()
            if target_text.startswith('เปิด'):
                target = resolve(target_text[len('เปิด'):].strip(), ['objects'])
                if target:
                    return command(ActionType.USE, target, instrument=instrument)
    prefixes = [
        ('สอบปากคำ', ActionType.INTERROGATE, ['suspects']),
        ('คุยกับ', ActionType.INTERROGATE, ['suspects']),
        ('กล่าวหา', ActionType.ACCUSE, ['suspects']),
        ('ปลดล็อก', ActionType.UNLOCK, ['objects']),
        ('หยิบ', ActionType.TAKE, ['objects']),
        ('เก็บ', ActionType.TAKE, ['objects']),
        ('ตรวจสอบ', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
        ('ตรวจดู', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
        ('ตรวจ', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
        ('ไปที่', ActionType.MOVE, ['locations']),
        ('ไป', ActionType.MOVE, ['locations']),
        ('interrogate', ActionType.INTERROGATE, ['suspects']),
        ('talk to', ActionType.INTERROGATE, ['suspects']),
        ('accuse', ActionType.ACCUSE, ['suspects']),
        ('unlock', ActionType.UNLOCK, ['objects']),
        ('take', ActionType.TAKE, ['objects']),
        ('pick up', ActionType.TAKE, ['objects']),
        ('examine', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
        ('inspect', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
        ('check', ActionType.EXAMINE, ['objects', 'suspects', 'locations']),
        ('go to', ActionType.MOVE, ['locations']),
        ('move to', ActionType.MOVE, ['locations']),
        ('walk to', ActionType.MOVE, ['locations']),
    ]
    val_lower = value.lower()
    for prefix, action, groups in prefixes:
        pref_lower = prefix.lower()
        if not val_lower.startswith(pref_lower):
            continue
        pref_len = len(prefix)
        if prefix.isascii() and len(val_lower) > pref_len and not val_lower[pref_len].isspace():
            continue
        target_text = value[pref_len:].strip()
        if target_text.lower().startswith('the '):
            target_text = target_text[4:].strip()
        elif target_text.lower().startswith('a '):
            target_text = target_text[2:].strip()
        target = resolve(target_text, groups)
        if target is None and action == ActionType.TAKE:
            target = resolve_local_key_to_take(target_text)
        if target:
            return command(action, target)
    return None


def interpret_game(text, state, **kwargs):
    from app.neural.gemini_client import STORY_DATA, interpret
    from app.neural.repair import repair_parsed_command
    parsed = parse_typed_command(text, state, STORY_DATA)
    if parsed:
        repaired, repair_note = repair_parsed_command(parsed, STORY_DATA, state=state, raw_text=text)
        if repair_note and not repaired.repair_note:
            repaired = repaired.model_copy(update={"repair_note": repair_note})
        return repaired
    return interpret(text, state, **kwargs)
