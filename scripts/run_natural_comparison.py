"""One natural-language suite, shared neural parsing, separate adjudication outputs.

Default: validate fixtures offline. --live: at most two Gemini calls per case.
Each case resets to its declared fixture; this is NOT a continuous rollout.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.neural.game_master import GeminiGameProvider, NeuralGameError, digest
from app.neural.prompts import build_interpret_system_prompt
from app.schemas import ParsedCommand
from scripts.run_case_rollout_benchmark import CompleteStateGameMaster, compare, prepare, save


def load_suite(filename):
    suite = json.loads(filename.read_text(encoding='utf-8'))
    cid, initial, commands, refs, oracle, bundle = prepare(suite['case'])
    fixtures = []
    ids = set()
    for spec in suite['cases']:
        if spec['id'] in ids:
            raise ValueError('Duplicate test ID')
        ids.add(spec['id'])
        if 'before_command' in spec:
            matches = [i+1 for i, c in enumerate(commands)
                       if all(c.model_dump(mode='json').get(k) == v for k,v in spec['before_command'].items())]
            if len(matches) != 1:
                raise ValueError(f"Fixture anchor must match one command: {spec['id']}")
            step = matches[0]
        else:
            step = spec['before_walkthrough_step']
        if not isinstance(step, int) or not 1 <= step <= len(commands):
            raise ValueError('Invalid walkthrough fixture step')
        state = (initial if step == 1 else refs[step-2].new_state).model_copy(deep=True)
        for item in spec.get('remove_inventory', []):
            if item not in state.inventory:
                raise ValueError(f'Fixture does not hold {item}')
            state.inventory.remove(item)
        expected_command = ParsedCommand(**spec['expected_command'], raw_text=spec['text'])
        reference = oracle.adjudicate(expected_command, state.model_copy(deep=True)).output
        if reference.allowed != spec['expected_allowed']:
            raise ValueError(f"Authored allow/deny differs from engine: {spec['id']}")
        fixtures.append((spec, state, reference))
    if not fixtures:
        raise ValueError('Empty suite')
    return suite, fixtures, oracle, bundle


def parse_once(provider, text, state, world):
    # Same neural parser for both arms. No fast path, symbolic repair, examples
    # retrieved from training data, automatic retry, or provider fallback.
    system = build_interpret_system_prompt(world, state=state, user_text=text,
                                           prune=False, use_knn=False, zero_shot=True)
    content = json.dumps({'player_text': text, 'state': state.model_dump(mode='json')}, ensure_ascii=False)
    record = {'system_prompt': system, 'content': content, 'status': 'error'}
    begin = time.perf_counter()
    try:
        reply = provider(system, content, ParsedCommand)
    except Exception as exc:
        record.update(error_kind='provider', exception_type=type(exc).__name__)
        record['latency_ms'] = round((time.perf_counter()-begin)*1000, 3)
        return None, record
    record.update(raw_response=reply.text, usage=reply.usage, model_version=reply.model_version,
                  latency_ms=round((time.perf_counter()-begin)*1000, 3))
    try:
        parsed = ParsedCommand.model_validate_json(reply.text)
    except ValueError:
        record['error_kind'] = 'schema'
        return None, record
    # raw_text is the actual user input, not a field the model may rewrite.
    parsed.raw_text = text
    record.update(status='ok', parsed=parsed.model_dump(mode='json'))
    return parsed, record


def evaluate_case(spec, state, reference, parsed, actor):
    row = {'id': spec['id'], 'text': spec['text'], 'state_before': state.model_dump(mode='json'),
           'parsed': parsed.model_dump(mode='json')}
    try:
        turn = actor.adjudicate(parsed.model_copy(deep=True), state.model_copy(deep=True))
    except NeuralGameError as exc:
        row.update(status='error', error_kind=exc.kind, metadata=exc.metadata, raw_response=exc.raw_response)
        return row
    row.update(status='ok', output=turn.output.model_dump(mode='json'),
               checks=compare(turn.output, reference), metadata=turn.metadata, raw_response=turn.raw_response)
    return row


CHECK_LABELS = {'allowed': 'ผลอนุญาต/ปฏิเสธ', 'state': 'สถานะเกม', 'visible_objects': 'วัตถุที่มองเห็น',
                'visible_people': 'คนที่มองเห็น', 'deductions': 'ข้อสรุป', 'pillar_status': 'สถานะเสาหลักฐาน'}


def case_reason(spec, parser_record, row):
    """One CSV row per case and mode: did it pass, which stage failed, and why."""
    out = {'id': spec['id'], 'text': spec['text'], 'mode': row.get('mode', ''),
           'result': 'ผ่าน', 'problem_at': '', 'reason': ''}
    reasons, stages = [], []
    if parser_record['status'] != 'ok':
        stages.append('parser')
        reasons.append(f"parser ล้มเหลว ({parser_record.get('error_kind')}"
                       f"{': ' + parser_record['exception_type'] if parser_record.get('exception_type') else ''})")
    else:
        got = parser_record['parsed']
        wrong = [f"{k} ได้ {got.get(k)!r} คาดว่า {v!r}" for k, v in spec['expected_command'].items() if got.get(k) != v]
        if wrong:
            stages.append('parser')
            reasons.append('parser ตีความผิด: ' + ', '.join(wrong))
    if row['status'] == 'not_run':
        out['result'] = 'ไม่ได้รัน'
    elif row['status'] == 'error':
        out['result'] = 'error'
        stages.append('adjudication')
        meta = row.get('metadata') or {}
        detail = meta.get('exception_type') or ', '.join(meta.get('missing_fields', []))
        reasons.append(f"ส่วนตัดสินล้มเหลว ({row.get('error_kind')}{': ' + detail if detail else ''})")
    else:
        checks = row['checks']
        failed = [k for k in CHECK_LABELS if not checks.get(k, True)]
        if failed:
            stages.append('adjudication')
        for k in failed:
            if k == 'allowed':
                reasons.append(f"ผลอนุญาตผิด: ได้ {row['output']['allowed']} คาดว่า {spec['expected_allowed']}")
            elif k == 'state':
                reasons.append('สถานะเกมต่าง: ' + ', '.join(checks.get('state_differences', [])))
            else:
                reasons.append(f'{CHECK_LABELS[k]}ไม่ตรง reference')
    if reasons and out['result'] == 'ผ่าน':
        out['result'] = 'ไม่ผ่าน'
    out['problem_at'] = ' + '.join(dict.fromkeys(stages))
    out['reason'] = '; '.join(reasons)
    return out


def run_pair(spec, state, reference, parsed, actors):
    return {mode: evaluate_case(spec, state, reference, parsed, actor) for mode, actor in actors.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, default=ROOT/'data/research/natural-commands-pilot.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--model')
    parser.add_argument('--max-provider-calls', type=int, default=12)
    args = parser.parse_args(argv)
    suite, fixtures, oracle, bundle = load_suite(args.suite)
    if args.output.exists():
        parser.error('Use a new output folder; existing results will not be overwritten')
    if args.live and 2*len(fixtures) > args.max_provider_calls:
        parser.error('Planned calls exceed --max-provider-calls')
    args.output.mkdir(parents=True)
    save(args.output/'suite.json', suite)
    save(args.output/'bundle.json', bundle)
    save(args.output/'fixtures.json', [dict(id=s['id'], state=st.model_dump(mode='json'),
        expected=r.model_dump(mode='json')) for s,st,r in fixtures])
    provider = GeminiGameProvider(model=args.model, timeout_ms=15000) if args.live else None
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'running' if args.live else 'validated_not_run', 'suite_sha256': digest(suite),
                'bundle_sha256': digest(bundle), 'model': provider.model if provider else None,
                'planned_max_calls': 2*len(fixtures) if args.live else 0,
                'design': 'independent cases; shared neural parse then separate adjudication',
                'parser': 'zero-shot full entities; no fast-path, repair, retry or fallback',
                'reference': 'same-engine reference plus authored allow/deny; not independently reviewed',
                'prose_review': 'not performed',
                'source_hashes': {p: digest((ROOT/p).read_text(encoding='utf-8')) for p in [
                    'scripts/run_natural_comparison.py','scripts/run_case_rollout_benchmark.py',
                    'scripts/evaluate_modes.py','app/neural/prompts.py','app/neural/game_master.py',
                    'app/symbolic/engine.py','app/schemas.py']}}
    save(args.output/'manifest.json', manifest)
    if not args.live:
        (args.output/'report.md').write_text(
            '# ตรวจชุดทดสอบแล้ว\n\nตรวจสถานะและผลอนุญาต/ปฏิเสธที่คาดหวังครบ '
            f'{len(fixtures)} กรณี ยังไม่ได้เรียก Gemini และยังไม่มีผลเปรียบเทียบสองระบบ\n', encoding='utf-8')
        print(f'Validated {len(fixtures)} cases offline; no API calls. Saved: {args.output.resolve()}')
        return 0
    actors = {'neural': CompleteStateGameMaster(bundle=bundle, provider=provider, model=provider.model),
              'neuro-symbolic': oracle}
    logs = {}
    all_rows = {m: [] for m in actors}
    parser_rows = []
    case_rows = []
    try:
        for mode in actors:
            folder = args.output/mode
            folder.mkdir()
            logs[mode] = (folder/'results.jsonl').open('w', encoding='utf-8')
        with (args.output/'parser.jsonl').open('w', encoding='utf-8') as log:
            for spec, state, reference in fixtures:
                parsed, record = parse_once(provider, spec['text'], state, bundle['world'])
                record['id'] = spec['id']
                if parsed is not None:
                    record['expected_field_matches'] = {k: parsed.model_dump(mode='json')[k] == v
                                                         for k,v in spec['expected_command'].items()}
                parser_rows.append(record)
                log.write(json.dumps(record, ensure_ascii=False)+'\n');log.flush()
                if parsed is None:
                    pair = {m: {'id':spec['id'], 'text':spec['text'], 'status':'not_run',
                                'reason':'shared_parser_error'} for m in actors}
                else:
                    pair = run_pair(spec, state, reference, parsed, actors)
                for mode,row in pair.items():
                    all_rows[mode].append(row)
                    logs[mode].write(json.dumps(row, ensure_ascii=False)+'\n');logs[mode].flush()
                    case_rows.append(case_reason(spec, record, {**row, 'mode': mode}))
                    c = case_rows[-1]
                    print(f"{spec['id']} [{mode}] {c['result']}" + (f" — {c['reason']}" if c['reason'] else ''), flush=True)
    finally:
        for log in logs.values():
            log.close()
    paired_ids = {r['id'] for r in all_rows['neural'] if r['status']=='ok'} & {
        r['id'] for r in all_rows['neuro-symbolic'] if r['status']=='ok'}
    comparison = []
    for mode, rows in all_rows.items():
        valid = [r for r in rows if r['status']=='ok']
        paired = [r for r in valid if r['id'] in paired_ids]
        summary = {'mode':mode, 'planned_cases':len(fixtures), 'valid_outputs':len(valid),
                   'errors':sum(r['status']=='error' for r in rows),
                   'not_run':sum(r['status']=='not_run' for r in rows), 'paired_cases':len(paired),
                   **{f'paired_{k}_matches':sum(r['checks'][k] for r in paired)
                      for k in ['allowed','state','visible_objects']}}
        save(args.output/mode/'summary.json', summary)
        comparison.append(summary)
    with (args.output/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(comparison[0]));writer.writeheader();writer.writerows(comparison)
    with (args.output/'cases.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(case_rows[0]));writer.writeheader();writer.writerows(case_rows)
    manifest['status']='finished'
    save(args.output/'manifest.json',manifest)
    text = ['# เปรียบเทียบข้อความชุดเดียวกัน', '',
            '| ระบบ | คำตอบใช้ได้ | กรณีคู่กัน | อนุญาตตรง | สถานะตรง | วัตถุตรง |',
            '|---|---:|---:|---:|---:|---:|']
    for s in comparison:
        text.append(f"| {s['mode']} | {s['valid_outputs']} | {s['paired_cases']} | "
                    f"{s['paired_allowed_matches']} | {s['paired_state_matches']} | {s['paired_visible_objects_matches']} |")
    text += ['', 'ตัวหารของคะแนนเปรียบเทียบคือกรณีที่มีคำตอบทั้งคู่ ไม่รวมข้อผิดพลาดบริการ',
             'ใช้ parser ของ Gemini ร่วมกันหนึ่งครั้งต่อกรณี ไม่มี Fast-path หรือการซ่อมคำตอบ',
             'แต่ละกรณีตั้งสถานะใหม่ ไม่ใช่การเล่นต่อเนื่องและไม่วัดการจบคดี',
             'reference สถานะสร้างจาก engine ของเรา จึงไม่ใช่เฉลยจากผู้ตรวจอิสระ',
             'ตรวจรายการวัตถุ แต่ยังไม่ตรวจความหมายของข้อความบรรยาย',
             'เวลาและ usage ของ parser อยู่ใน parser.jsonl แยกจากการตัดสิน ไม่ควรนับรวมซ้ำ',
             'คะแนนตีความดู expected_field_matches ใน parser.jsonl; คะแนนผลลัพธ์เทียบกับเจตนาที่กำหนดไว้ก่อนทดลอง',
             'ถ้า parser ผิด ทั้งสองฝั่งอาจผิดพร้อมกัน ห้ามตีความว่าเป็นความผิดของส่วนตัดสินเพียงอย่างเดียว']
    (args.output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(f'Saved: {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
