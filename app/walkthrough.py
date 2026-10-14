"""Decode the authored walkthrough for reproducible offline play checks."""
from app.schemas import ParsedCommand


def parse_step(step, walkthrough):
    if isinstance(step, dict):
        fields = dict(step)
    else:
        fields = {'action': step[0], 'target': step[1]}
        if len(step) > 2:
            key = 'topic' if step[0] == 'interrogate' else ('code' if str(step[2]).isdigit() else 'instrument')
            fields[key] = str(step[2])
    if fields['action'] == 'infer':
        fields.setdefault('evidence', walkthrough['inference_evidence'])
    fields.setdefault('raw_text', 'walkthrough')
    return ParsedCommand(**fields)
