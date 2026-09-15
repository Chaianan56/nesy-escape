"""Fail early on malformed rule references instead of failing during play."""
import math


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
    limit = world.get('time_limit_seconds', 3600)
    require(isinstance(limit, (int, float)) and not isinstance(limit, bool) and math.isfinite(limit) and limit > 0, "time_limit_seconds must be positive")
    for group in ('objects', 'suspects'):
        for key, entity in world[group].items():
            require(entity.get('location') is None or entity['location'] in locations, key + ': unknown location')
            refs(entity.get('supports', []), actions, key + '.supports')
            refs(entity.get('grants_evidence', []), evidence, key + '.grants_evidence')
            require(not entity.get('grants_object') or entity['grants_object'] in objects, key + ': unknown grants_object')
            owner = entity.get('from_testimony')
            if owner:
                require(owner in suspects, key + ': unknown testimony owner')
                require(key in world['suspects'][owner].get('grants_evidence', []), key + ': testimony owner does not grant evidence')
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
    for key, ending in world['endings'].items():
        require(ending.get('on_timeout') or ending.get('accuse') in suspects | {'*'}, key + ': invalid accuse')
        for prefix in ('requires_', 'denies_'):
            for name, known in [('evidence', evidence), ('deductions', deductions), ('pillars', set(pillars))]:
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
