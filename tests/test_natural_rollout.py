import io
import json
from app.neural.game_master import ProviderReply
from app.schemas import ParsedCommand, GameState
from scripts import run_natural_rollout as runner
from scripts.summarize_natural_rollout import summarize


def test_complete_offline_pipeline(monkeypatch, tmp_path):
    _, _, commands, _, oracle, bundle = runner.prepare('A')
    commands = runner.natural_commands(commands, bundle['world'])
    lookup = {c.raw_text:c for c in commands}
    calls = []
    class Fake:
        model = 'test-double-not-research'
        def __init__(self, **kwargs): pass
        def __call__(self, system, content, schema):
            data = json.loads(content)
            calls.append(data)
            if 'player_text' in data:
                return ProviderReply(lookup[data['player_text']].model_dump_json(), {})
            out = oracle.adjudicate(ParsedCommand.model_validate(data['command']),
                                   GameState.model_validate(data['state'])).output
            return ProviderReply(out.model_dump_json(), {})
    monkeypatch.setattr(runner, 'GeminiGameProvider', Fake)
    out = tmp_path/'run'
    runner.main(['--live','--pause-seconds','0','--output',str(out)])
    summary=json.loads((out/'summary.json').read_text())
    assert len(calls)==len(commands) * 3
    assert all(e['completed_reference_solution'] for e in summary['episodes'])
    assert all(e['own_state_transition_disagreements']==0 for e in summary['episodes'])
    for mode in ['neural','neuro-symbolic']:
        rows=[json.loads(l) for l in (out/mode/'turns.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(rows)==len(commands)
        assert all(rows[i]['state_before']==rows[i-1]['output']['new_state'] for i in range(1,len(commands)))


def test_transient_retry_logs_same_request(monkeypatch):
    class ServerError(Exception): pass
    class Fake:
        model='fake'
        calls=0
        def __call__(self,*args):
            self.calls+=1
            if self.calls==1: raise ServerError()
            return ProviderReply('{}',{})
    monkeypatch.setattr(runner.time,'sleep',lambda _:None)
    log=io.StringIO()
    provider=runner.LoggedProvider(Fake(),log)
    provider('system','content',ParsedCommand)
    rows=[json.loads(x) for x in log.getvalue().splitlines()]
    assert len(rows)==2 and rows[0]['retry_scheduled']
    assert rows[0]['content']==rows[1]['content']


def test_resume_preserves_states_and_error_logs(monkeypatch,tmp_path):
    _,_,commands,_,oracle,bundle=runner.prepare('A')
    total_steps = len(commands)
    total_calls = total_steps * 3 + 2
    lookup={c.raw_text:c for c in runner.natural_commands(commands,bundle['world'])}
    calls=[]
    class Fake:
        model='offline-resume-test'
        def __init__(self,**kwargs):pass
        def __call__(self,system,content,schema):
            data=json.loads(content);calls.append(data)
            if len(calls) in [5,7]:raise RuntimeError('simulated interruption')
            if 'player_text' in data:return ProviderReply(lookup[data['player_text']].model_dump_json(),{})
            return ProviderReply(oracle.adjudicate(ParsedCommand.model_validate(data['command']),
                GameState.model_validate(data['state'])).output.model_dump_json(),{})
    monkeypatch.setattr(runner,'GeminiGameProvider',Fake)
    output=tmp_path/'resume'
    args=['--live','--pause-seconds','0','--output',str(output)]
    runner.main(args)
    first=json.loads((output/'summary.json').read_text())
    assert [e['valid_responses'] for e in first['episodes']]==[2,1]
    runner.main(args+['--resume'])
    final=json.loads((output/'summary.json').read_text())
    assert final['actual_provider_calls']==total_calls
    assert all(e['completed_reference_solution'] for e in final['episodes'])
    assert all(e['service_interruptions']==1 for e in final['episodes'])
    rebuilt=summarize(output)
    assert rebuilt['actual_provider_calls']==total_calls
    assert rebuilt['provider_errors']==2
    assert all(e['state_matches']==total_steps for e in rebuilt['episodes'])
    assert sum(e['provider_calls'] for e in rebuilt['episodes'])==total_calls
    for mode in ['neural','neuro-symbolic']:
        rows=[json.loads(l) for l in (output/mode/'turns.jsonl').read_text(encoding='utf-8').splitlines()]
        ok=[r for r in rows if r['status']=='ok']
        assert [r['step'] for r in ok]==list(range(1,total_steps + 1))
        assert all(ok[i]['state_before']==ok[i-1]['output']['new_state'] for i in range(1,total_steps))


def test_texts_file_matches_walkthrough(tmp_path):
    _, _, commands, _, _, _ = runner.prepare('A')
    path = runner.ROOT/'data/research/natural-rollout-texts-A-v3.json'
    texts = runner.load_texts(path, commands)
    assert len(texts) == len(commands)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['cases'][3]['expected_command']['target'] = 'wall_clock'
    bad = tmp_path/'bad.json'
    bad.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    try:
        runner.load_texts(bad, commands)
    except ValueError as exc:
        assert 'step 4' in str(exc)
    else:
        raise AssertionError('mismatched expected_command was accepted')

