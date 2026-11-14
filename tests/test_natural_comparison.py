import json
from pathlib import Path

from app.neural.game_master import ProviderReply, NeuralGameError
from app.schemas import GameState, ParsedCommand
from scripts import run_natural_comparison as benchmark


SUITE = benchmark.ROOT / 'data/research/natural-commands-pilot.json'


def test_six_fixtures_and_key_pair():
    _, fixtures, _, _ = benchmark.load_suite(SUITE)
    assert len(fixtures) == 6
    no_key, with_key = fixtures[2:4]
    assert no_key[0]['text'] == with_key[0]['text']
    assert 'staff_key' not in no_key[1].inventory
    assert 'staff_key' in with_key[1].inventory
    assert not no_key[2].allowed and with_key[2].allowed
    assert not fixtures[4][2].new_state.discovered_evidence == fixtures[5][2].new_state.discovered_evidence


def test_each_arm_gets_an_independent_copy_and_error_does_not_skip_other_arm():
    _, fixtures, oracle, _ = benchmark.load_suite(SUITE)
    spec, state, ref = fixtures[0]
    command = ParsedCommand(**spec['expected_command'],raw_text=spec['text'])

    class Broken:
        def adjudicate(self, cmd, current):
            current.inventory.append('invented')
            raise NeuralGameError('provider', {'attempts':1})

    result = benchmark.run_pair(spec,state,ref,command,{'neural':Broken(),'neuro-symbolic':oracle})
    assert result['neural']['status']=='error'
    assert result['neuro-symbolic']['checks']['state']
    assert 'invented' not in state.inventory


def test_shared_parser_is_not_retried():
    _, fixtures, _, bundle = benchmark.load_suite(SUITE)
    calls=[]

    def broken(*args):
        calls.append(args)
        raise RuntimeError('provider offline')

    parsed, record=benchmark.parse_once(broken,fixtures[0][0]['text'],fixtures[0][1],bundle['world'])
    assert parsed is None and record['error_kind']=='provider'
    assert len(calls)==1


def test_one_suite_writes_two_separate_result_sets_without_network(monkeypatch,tmp_path):
    _, fixtures, oracle, _=benchmark.load_suite(SUITE)
    calls=[]
    specs={s['text']:s for s,_,_ in fixtures}

    class FakeProvider:
        def __init__(self,**kwargs): self.model='offline-test-double'
        def __call__(self,system,content,schema):
            data=json.loads(content);calls.append(data)
            if 'player_text' in data:
                parsed=ParsedCommand(**specs[data['player_text']]['expected_command'],raw_text=data['player_text'])
                return ProviderReply(parsed.model_dump_json(),{})
            parsed=ParsedCommand.model_validate(data['command'])
            state=GameState.model_validate(data['state'])
            return ProviderReply(oracle.adjudicate(parsed,state).output.model_dump_json(),{})

    monkeypatch.setattr(benchmark,'GeminiGameProvider',FakeProvider)
    output=tmp_path/'run'
    assert benchmark.main(['--live','--output',str(output)])==0
    assert len(calls)==12
    for mode in ['neural','neuro-symbolic']:
        rows=[json.loads(l) for l in (output/mode/'results.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(rows)==6
        assert all(r['checks']['state'] for r in rows)
        summary=json.loads((output/mode/'summary.json').read_text(encoding='utf-8'))
        assert summary['paired_cases']==6
    assert len((output/'parser.jsonl').read_text(encoding='utf-8').splitlines())==6
