"""Fail early on malformed rule references instead of failing during play."""
import math
import re


def validate_world(rules, world, checkers, actions):
    def require(ok, message):
        if not ok:
            raise ValueError("Invalid game data: " + message)

    def unique(values, label):
        require(isinstance(values, list) and all(isinstance(x, str) for x in values), label + " must be a list of IDs")
        require(len(values) == len(set(values)), label + " contains duplicate IDs")
        return values

    def refs(values, known, label):
        require(set(unique(values, label)) <= known, label + " contains unknown IDs")

    require(isinstance(world, dict), "world must be an object")
    for group in ("locations", "objects", "suspects", "deductions", "endings"):
        require(isinstance(world.get(group), dict), group + " must be an object")
        require(all(isinstance(v, dict) for v in world[group].values()), group + " entries must be objects")
    locations, objects, suspects = (set(world[g]) for g in ("locations", "objects", "suspects"))
    require(not (locations & objects or objects & suspects or locations & suspects), "entity IDs must be unique across groups")
    evidence = {k for k, v in world['objects'].items() if v.get('type') == 'evidence'}
    deductions = set(world['deductions'])
    require(isinstance(world.get('claims', {}), dict), 'claims must be an object')
    claims = set(world.get('claims', {}))
    scenes = world.get('narrative_scenes', {})
    require(isinstance(scenes, dict), 'narrative_scenes must be an object')
    cap = world.get('max_submitted_evidence', 15)
    require(type(cap) is int and cap > 0, 'max_submitted_evidence must be a positive integer')

    def requirements(cond, label):
        require(isinstance(cond, dict), label + ' must be an object')
        for name, known in [('evidence', evidence), ('deductions', deductions),
                            ('unlocked', objects), ('inventory', objects), ('claims', claims)]:
            refs(cond.get('requires_' + name, []), known, label + '.requires_' + name)

    limit = world.get('time_limit_seconds', 3600)
    require(isinstance(limit, (int, float)) and not isinstance(limit, bool) and math.isfinite(limit) and limit > 0, "time_limit_seconds must be positive")
    for group in ('objects', 'suspects'):
        for key, entity in world[group].items():
            require(entity.get('location') is None or entity['location'] in locations, key + ': unknown location')
            refs(entity.get('supports', []), actions, key + '.supports')
            refs(entity.get('grants_evidence', []), evidence, key + '.grants_evidence')
            requirements(entity.get('visible_requirements', {}), key + '.visible_requirements')
            if 'unlock_requirements' in entity:
                gate = entity['unlock_requirements']
                requirements(gate, key + '.unlock_requirements')
                require('code' in gate or 'key' in gate, key + ': unlock needs code or key')
                require('code' not in gate or isinstance(gate['code'], str), key + ': code must be a string')
                require('key' not in gate or gate['key'] in objects, key + ': unknown key')
            if group == 'suspects':
                require(type(entity.get('accusable', True)) is bool, key + ': accusable must be boolean')
                refs(entity.get('exculpatory_evidence', []), evidence, key + '.exculpatory_evidence')
                refs(entity.get('exculpatory_deductions', []), deductions, key + '.exculpatory_deductions')
                nodes = entity.get('dialogue_nodes', [])
                require(isinstance(nodes, list) and all(isinstance(n, dict) for n in nodes), key + ': dialogue_nodes must be objects')
                unique([n.get('id') for n in nodes], key + '.dialogue node IDs')
                for node in nodes:
                    label = key + ':' + node['id']
                    require(isinstance(node.get('topic'), str) and isinstance(node.get('text'), str) and bool(node['text']), label + ': missing topic/text')
                    requirements(node, label)
                    refs(node.get('grants_evidence', []), evidence, label + '.grants_evidence')
                    refs(node.get('grants_inventory', []), objects, label + '.grants_inventory')
                    require('scene_id' not in node or (isinstance(node['scene_id'], str) and node['scene_id'] in scenes),
                            label + ': unknown narrative scene')
            require(not entity.get('grants_object') or entity['grants_object'] in objects, key + ': unknown grants_object')
            owner = entity.get('from_testimony')
            if owner:
                require(owner in suspects, key + ': unknown testimony owner')
                person = world['suspects'][owner]
                grants = set(person.get('grants_evidence', []))
                for node in person.get('dialogue_nodes', []):
                    grants.update(node.get('grants_evidence', []))
                require(key in grants, key + ': testimony owner does not grant evidence')
    graph = {}
    for key, cond in world['deductions'].items():
        refs(cond.get('requires_evidence', []), evidence, key + '.requires_evidence')
        refs(cond.get('requires_deductions', []), deductions, key + '.requires_deductions')
        pool = cond.get('of', [])
        refs(pool, evidence | deductions, key + '.of')
        if 'at_least' in cond:
            need = cond['at_least']
            require(type(need) is int and 0 <= need <= len(pool), key + ': invalid at_least')
        else:
            require(not pool, key + ': of needs at_least')
        graph[key] = set(cond.get('requires_deductions', [])) | (set(pool) & deductions)
    visiting, done = set(), set()
    def visit(key):
        require(key not in visiting, 'deduction cycle at ' + key)
        if key in done:
            return
        visiting.add(key)
        for dependency in graph[key]:
            visit(dependency)
        visiting.remove(key)
        done.add(key)
    for key in graph:
        visit(key)
    pillars = world.get('pillar_order') or ['timeline', 'motive', 'opportunity', 'corroboration']
    unique(pillars, 'pillar_order')
    for sid, spec in world.get('pillars', {}).items():
        require(sid in suspects, 'unknown pillar suspect ' + sid)
        require(set(spec) <= set(pillars), 'unknown pillar name')
        for name, cond in spec.items():
            refs(cond.get('requires_deductions', []), deductions, sid + '.' + name)
            refs(cond.get('requires_claims', []), claims, sid + '.' + name + '.requires_claims')
    for cid, claim in world.get('claims', {}).items():
        requirements(claim, cid)
        require(type(claim.get('supported')) is bool, cid + ': supported must be boolean')
        require(isinstance(claim.get('name_th'), str), cid + ': missing name_th')
        require(isinstance(claim.get('feedback'), str), cid + ': missing feedback')
    for scene_id, scene in scenes.items():
        require(isinstance(scene_id, str) and re.fullmatch(r'[a-z][a-z0-9_]*', scene_id) is not None,
                'invalid narrative scene ID')
        require(isinstance(scene, dict) and isinstance(scene.get('title'), str) and bool(scene['title'].strip()),
                scene_id + ': missing scene title')
        pages = scene.get('pages')
        require(isinstance(pages, list) and bool(pages) and all(isinstance(page, dict) for page in pages),
                scene_id + ': pages must be a nonempty list of objects')
        unique([page.get('id') for page in pages], scene_id + '.page IDs')
        for page in pages:
            label = scene_id + '.' + page['id']
            require(re.fullmatch(r'[a-z][a-z0-9_]*', page['id']) is not None, label + ': invalid page ID')
            for field in ('speaker', 'time_label', 'text'):
                require(isinstance(page.get(field), str) and bool(page[field].strip()), label + ': missing ' + field)
            require(isinstance(page.get('art'), str) and re.fullmatch(r'[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*', page['art']) is not None,
                    label + ': art must be an asset ID, not a path or URL')
            requirements(page, label)
            refs(page.get('evidence_ids', []), evidence, label + '.evidence_ids')
    questions = world.get('inference_questions', [])
    require(isinstance(questions, list) and all(isinstance(q, dict) for q in questions), 'inference_questions must contain objects')
    unique([q.get('id') for q in questions], 'question IDs')
    for q in questions:
        requirements(q, q['id'])
        choices = q.get('choices', [])
        require(isinstance(choices, list) and bool(choices) and all(isinstance(c, dict) for c in choices), q['id'] + ': choices required')
        unique([c.get('id') for c in choices], q['id'] + '.choice IDs')
        for choice in choices:
            require(choice.get('target') in claims and isinstance(choice.get('label'), str), q['id'] + ': invalid choice')
    for key, ending in world['endings'].items():
        require(ending.get('on_timeout') or ending.get('accuse') in suspects | {'*'}, key + ': invalid accuse')
        for prefix in ('requires_', 'denies_'):
            for name, known in [('evidence', evidence), ('deductions', deductions), ('pillars', set(pillars)), ('claims', claims)]:
                refs(ending.get(prefix + name, []), known, key + '.' + prefix + name)
    order = world.get('ending_order', list(world['endings']))
    refs(order, set(world['endings']), 'ending_order')
    require(set(order) == set(world['endings']), 'ending_order must include every ending')
    require(any(e.get('on_timeout') for e in world['endings'].values()), 'missing timeout ending')
    require(isinstance(rules, list), 'rules must be a list')
    seen = set()
    for rule in rules:
        require(isinstance(rule, dict), 'rule must be an object')
        for field in ('id', 'description', 'check', 'message_fail'):
            require(isinstance(rule.get(field), str), 'rule needs ' + field)
        require(rule['id'] not in seen, 'duplicate rule ' + rule['id'])
        seen.add(rule['id'])
        require(rule['check'] in checkers, 'unknown checker ' + rule['check'])
        refs(rule.get('applies_to', []), actions | {'*'}, rule['id'] + '.applies_to')
        require(isinstance(rule.get('params', {}), dict), 'params must be an object')
        require(type(rule.get('blocking', True)) is bool, 'blocking must be boolean')
        override = rule.get('params', {}).get('limit_seconds')
        if override is not None:
            require(isinstance(override, (int, float)) and not isinstance(override, bool) and math.isfinite(override) and override > 0, 'limit_seconds must be positive')
    time_rules = [r for r in rules if r['check'] == 'within_time_limit']
    require(len(time_rules) == 1, 'exactly one time limit rule is required')
    require(time_rules[0].get('applies_to') == ['*'] and time_rules[0].get('blocking', True),
            'time limit must block every action')
