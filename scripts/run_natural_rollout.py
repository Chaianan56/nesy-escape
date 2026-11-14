"""Live natural-language case A rollout; independent API parsers and persistent states."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.neural.game_master import GeminiGameProvider, NeuralGameError, digest
from scripts.run_natural_comparison import parse_once
from scripts.run_case_rollout_benchmark import prepare, save, run_episode, CompleteStateGameMaster, report


def natural_commands(commands, world):
    result = []
    for c in commands:
        obj = next(world[k][c.target] for k in ('objects', 'locations', 'suspects') if c.target in world[k])
        name = obj['name_th']
        action = c.action.value
        if action == 'interrogate':
            label = next(n['label'] for n in obj['dialogue_nodes'] if n['topic'] == c.topic)
            text = f'ขอถาม{name}เรื่อง{label}หน่อยครับ'
        elif action == 'unlock':
            detail = f'รหัส {c.code}' if c.code else world['objects'][c.instrument]['name_th']
            text = f'ช่วยปลดล็อก{name}ด้วย{detail}'
        else:
            text = {'move': 'ขอเดินไปที่', 'examine': 'ขอตรวจสอบ',
                    'take': 'ขอหยิบ', 'accuse': 'ขอกล่าวหาว่าเป็นคนร้าย: '}[action] + name
        result.append(c.model_copy(update={'raw_text': text}))
    return result


class LoggedProvider:
    """Retry transient transport/server failures only, logging every request."""
    def __init__(self, base, log, limit=150, pause=0):
        self.base, self.log, self.limit = base, log, limit
        self.model = base.model
        self.calls = 0
        self.context = {}
        self.pause = pause

    def __call__(self, system, content, schema):
        for attempt in range(1, 3):
            if self.calls >= self.limit:
                raise RuntimeError('provider_call_budget_exhausted')
            self.calls += 1
            if self.pause:
                time.sleep(self.pause)
            row = dict(self.context, call=self.calls, attempt=attempt,
                       system_prompt=system, content=content, schema=schema.model_json_schema())
            start = time.perf_counter()
            try:
                reply = self.base(system, content, schema)
            except Exception as exc:
                code = getattr(exc, 'code', None)
                transient = (type(exc).__name__ in {'ServerError', 'ReadTimeout', 'ConnectTimeout',
                                                   'RemoteProtocolError', 'ConnectError'} or code == 429)
                row.update(status='error', exception_type=type(exc).__name__, code=code,
                           retry_scheduled=transient and attempt == 1)
                self.write(row, start)
                if transient and attempt == 1:
                    time.sleep(35 if code == 429 else 2)
                    continue
                raise
            row.update(status='ok', raw_response=reply.text, usage=reply.usage, model_version=reply.model_version)
            self.write(row, start)
            return reply

    def write(self, row, start):
        row['latency_ms'] = round((time.perf_counter()-start)*1000, 3)
        self.log.write(json.dumps(row, ensure_ascii=False)+'\n')
        self.log.flush()


class NaturalActor:
    def __init__(self, mode, actor, provider, world, parser_log):
        self.mode, self.actor, self.provider, self.world = mode, actor, provider, world
        self.parser_log = parser_log
        self.step = 0

    def adjudicate(self, expected, state):
        self.step += 1
        self.provider.context = dict(mode=self.mode, step=self.step, stage='parser')
        parsed, record = parse_once(self.provider, expected.raw_text, state, self.world)
        record.update(mode=self.mode, step=self.step)
        if parsed is not None:
            fields = ['action', 'target', 'topic', 'instrument', 'code', 'evidence']
            record['expected_field_matches'] = {k: getattr(parsed,k)==getattr(expected,k) for k in fields}
        self.parser_log.write(json.dumps(record, ensure_ascii=False)+'\n')
        self.parser_log.flush()
        if parsed is None:
            raise NeuralGameError('parser_'+record['error_kind'], {'latency_ms':record['latency_ms']})
        self.provider.context = dict(mode=self.mode, step=self.step, stage='adjudication')
        turn = self.actor.adjudicate(parsed, state)
        turn.executed_command = parsed
        return turn


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--live', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--pause-seconds', type=float, default=5)
    args = p.parse_args(argv)
    cid, initial, commands, refs, oracle, bundle = prepare('A')
    commands = natural_commands(commands, bundle['world'])
    if not 0 <= args.pause_seconds <= 30: p.error('pause must be between 0 and 30 seconds')
    if args.resume and (not args.live or not (args.output/'manifest.json').exists()):
        p.error('Resume requires --live and existing manifest')
    if args.output.exists() and not args.resume: p.error('Choose a new output folder')
    if args.resume:
        old = json.loads((args.output/'inputs.json').read_text(encoding='utf-8'))
        if digest(old['bundle']) != digest(bundle) or old['commands'] != [c.model_dump(mode='json') for c in commands]:
            p.error('Cannot resume changed input data')
    args.output.mkdir(parents=True,exist_ok=args.resume)
    save(args.output/'inputs.json', dict(case_id=cid, initial_state=initial.model_dump(mode='json'),
         commands=[c.model_dump(mode='json') for c in commands], bundle=bundle))
    save(args.output/'reference.json', [r.model_dump(mode='json') for r in refs])
    manifest = dict(live=args.live, design='independent API parsers; same texts; persistent own states',
                    planned_calls=len(commands)*3, maximum_calls=len(commands)*6, planned_turns=len(commands),
                    retry='one retry for transient service failures only',
                    fallback=False, semantic_repair=False, reference='same-engine; not independent truth',
                    input_origin='Thai templates from development walkthrough; not held-out human participants',
                    clock='fixed elapsed_seconds=0; no wall-clock game timeout',
                    parser='zero-shot, full entities, no fast-path, no symbolic repair',
                    status='running' if args.live else 'validated_not_run',pause_seconds=args.pause_seconds)
    if args.resume:
        manifest=json.loads((args.output/'manifest.json').read_text(encoding='utf-8'))
        manifest['resumptions']=manifest.get('resumptions',[])+[dict(reason='service interruption',pause_seconds=args.pause_seconds)]
    sources = ['scripts/run_natural_rollout.py', 'scripts/run_case_rollout_benchmark.py',
               'scripts/run_natural_comparison.py', 'scripts/evaluate_modes.py',
               'app/neural/game_master.py', 'app/neural/prompts.py', 'app/symbolic/engine.py', 'app/schemas.py']
    manifest['hashes'] = {}
    for source in sources:
        contents = (ROOT/source).read_text(encoding='utf-8')
        dest = args.output/('resume-code-snapshot' if args.resume else 'code-snapshot')/source
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(contents, encoding='utf-8')
        manifest['hashes'][source] = digest(contents)
    save(args.output/'manifest.json', manifest)
    if not args.live:
        print(f'Validated {len(commands)} commands; no API calls.')
        return 0
    summary = dict(status='running', live=True, episodes=[])
    prior_requests = [json.loads(l) for l in (args.output/'requests.jsonl').read_text(encoding='utf-8').splitlines()] if args.resume else []
    with (args.output/'requests.jsonl').open('a' if args.resume else 'w', encoding='utf-8') as requests:
        provider = LoggedProvider(GeminiGameProvider(timeout_ms=30000), requests,pause=args.pause_seconds)
        provider.calls=len(prior_requests)
        manifest['model'] = provider.model
        save(args.output/'manifest.json', manifest)
        for mode in ['neural', 'neuro-symbolic']:
            folder = args.output/mode
            folder.mkdir(exist_ok=args.resume)
            prior_rows=[json.loads(l) for l in (folder/'turns.jsonl').read_text(encoding='utf-8').splitlines()] if args.resume else []
            prior_ok=[r for r in prior_rows if r['status']=='ok']
            offset=len(prior_ok)
            if prior_ok and prior_ok[-1]['output']['new_state']['ending_id'] is not None:
                summary['episodes'].append(json.loads((folder/'summary.json').read_text(encoding='utf-8')))
                continue
            from app.schemas import GameState
            current=GameState.model_validate(prior_ok[-1]['output']['new_state']) if prior_ok else initial
            rows=list(prior_rows)
            with (folder/'parser.jsonl').open('a' if args.resume else 'w',encoding='utf-8') as parsers, \
                 (folder/'turns.jsonl').open('a' if args.resume else 'w',encoding='utf-8') as turns:
                base = CompleteStateGameMaster(bundle=bundle,provider=provider,model=provider.model) if mode=='neural' else oracle
                actor = NaturalActor(mode,base,provider,bundle['world'],parsers)
                actor.step=offset
                def record(row):
                    row['step']+=offset
                    rows.append(row)
                    turns.write(json.dumps(row,ensure_ascii=False)+'\n');turns.flush()
                    print(mode,row['step'],row['status'],flush=True)
                before = provider.calls
                result = run_episode(mode,'A',1,current,commands[offset:],refs[offset:],actor,oracle,record)
                valid=[r for r in rows if r['status']=='ok']
                audits=[r['own_state_rule_audit'] for r in valid if r['own_state_rule_audit'] is not None]
                total_commands = len(commands)
                result.update(planned_turns=total_commands,attempted_turns=len(rows),valid_responses=len(valid),
                              unexecuted_turns=total_commands-len({r['step'] for r in rows}),
                              completed_reference_solution=len(valid)==total_commands and result['final_state_matches_reference'],
                              service_interruptions=sum(r['status']=='error' for r in rows),
                              trajectory_state_matches=sum(r['reference_trajectory']['state'] for r in valid),
                              trajectory_allowed_matches=sum(r['reference_trajectory']['allowed'] for r in valid),
                              trajectory_visible_object_matches=sum(r['reference_trajectory']['visible_objects'] for r in valid),
                              first_state_divergence_step=next((r['step'] for r in valid if not r['reference_trajectory']['state']),None),
                              own_state_auditable_turns=len(audits),
                              own_state_permission_disagreements=sum(not a['allowed'] for a in audits),
                              own_state_transition_disagreements=sum(not a['state'] for a in audits))
                result['provider_attempts_including_parser_and_retries'] = provider.calls-before
                save(folder/'summary.json',result)
                summary['episodes'].append(result)
                save(args.output/'summary.json',summary)
        summary.update(status='finished',actual_provider_calls=provider.calls)
    save(args.output/'summary.json',summary)
    manifest.update(status='finished',actual_provider_calls=provider.calls)
    save(args.output/'manifest.json',manifest)
    total_commands = len(commands)
    lines=['# Natural-language continuous rollout: case A', '',
           f'Same {total_commands} Thai texts; each mode uses its own persistent state and an independent Gemini parse.',
           'Neural uses Gemini for adjudication. NeSy uses Symbolic rules. No fast-path or semantic repair.',
           'One retry allowed only for transient service failures; all attempts in requests.jsonl.', '',
           '| Mode | Valid turns | Ending claimed | Final state matches reference | Own-state transition disagreements |',
           '|---|---:|---|---|---:|']
    for e in summary['episodes']:
        lines.append(f"| {e['mode']} | {e['valid_responses']}/{total_commands} | {e['ending_id']} | {e['final_state_matches_reference']} | {e['own_state_transition_disagreements']} |")
    lines += ['', 'Reference uses the same Symbolic engine, not independent ground truth.',
              'Development walkthrough, one run, no prose leakage assessment or statistical claim.',
              'Own-state audit uses the actual API-parsed command; trajectory comparison uses the intended walkthrough.',
              'The intended command is never substituted for a parser mistake. Neither mode receives the reference.',
              'Ending claimed is model output; inspect final state and final rule audit before claiming valid completion.']
    (args.output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved:',args.output.resolve())
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
