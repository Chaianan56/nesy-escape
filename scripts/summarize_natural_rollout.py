"""Rebuild full-run metrics from append-only logs, including resumed requests."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


LABELS = {'allowed':'ผลอนุญาต','state':'สถานะเกม','visible_objects':'วัตถุที่มองเห็น',
          'visible_people':'คนที่มองเห็น','deductions':'ข้อสรุป','pillar_status':'สถานะเสาหลักฐาน'}


def turn_row(row, parser):
    """One readable CSV row per turn. result uses parser + allowed + state;
    other output mismatches are listed separately in other_mismatches."""
    cmd = (parser or {}).get('parsed') or row.get('command') or {}
    out = {'mode':row['mode'],'step':row['step'],'text':(row.get('command') or {}).get('raw_text',''),
           'parsed':' '.join(str(cmd.get(k)) for k in ['action','target','topic','code'] if cmd.get(k)),
           'allowed':(row.get('output') or {}).get('allowed',''),
           'ending_id':((row.get('output') or {}).get('new_state') or {}).get('ending_id') or '',
           'result':'ผ่าน','problem_at':'','reason':'','other_mismatches':'',
           'carried_over_divergence':'ใช่' if row.get('previous_state_divergence') else ''}
    stages, reasons, minor = [], [], []
    if parser and parser.get('expected_field_matches'):
        wrong = [f"{k}={cmd.get(k)!r}" for k,v in parser['expected_field_matches'].items() if not v]
        if wrong:
            stages.append('parser'); reasons.append('parser ตีความผิด: ' + ', '.join(wrong))
    if row['status'] != 'ok':
        meta = row.get('metadata') or {}
        out['result'] = 'error'
        stages.append('parser' if str(row.get('error_kind','')).startswith('parser') else 'adjudication')
        reasons.append(f"{row.get('error_kind')} {meta.get('exception_type') or ', '.join(meta.get('missing_fields',[]))}".strip())
    else:
        for name, checks in [('ขัดกฎจากสถานะของตัวเอง', row.get('own_state_rule_audit')),
                             ('ต่างจากเส้นทางอ้างอิง', row.get('reference_trajectory'))]:
            if not checks:
                continue
            bad = [LABELS[k] + (f" ({', '.join(checks['state_differences'])})" if k=='state' else '')
                   for k in ['allowed','state'] if not checks.get(k, True)]
            if bad:
                stages.append('adjudication'); reasons.append(f"{name}: " + '; '.join(bad))
            minor += [LABELS[k] for k in ['visible_objects','visible_people','deductions','pillar_status']
                      if not checks.get(k, True) and LABELS[k] not in minor]
        if row.get('audit_error'):
            reasons.append(f"ตรวจกฎไม่ได้: {row['audit_error']}")
    if reasons and out['result'] == 'ผ่าน':
        out['result'] = 'ไม่ผ่าน'
    out.update(problem_at=' + '.join(dict.fromkeys(stages)), reason=' | '.join(reasons),
               other_mismatches=', '.join(minor))
    return out


def write_turns_csv(folder):
    rows = []
    for mode in ['neural','neuro-symbolic']:
        parsers = {}
        for p in read_rows(folder/mode/'parser.jsonl'):
            parsers[p['step']] = p
        rows += [turn_row(r, parsers.get(r['step'])) for r in read_rows(folder/mode/'turns.jsonl')]
    with (folder/'turns.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return rows


def summarize(folder):
    requests = read_rows(folder/'requests.jsonl')
    metrics=[]
    manifest_file = folder / 'manifest.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8')) if manifest_file.exists() else {}
    planned_turns = manifest.get('planned_turns', 28)
    for mode in ['neural','neuro-symbolic']:
        rows=read_rows(folder/mode/'turns.jsonl')
        valid=[r for r in rows if r['status']=='ok']
        steps=[r['step'] for r in valid]
        assert steps == list(range(1,len(valid)+1)), 'Duplicate or missing successful turn'
        assert all(valid[i]['state_before']==valid[i-1]['output']['new_state'] for i in range(1,len(valid))), 'Broken state continuity'
        audits=[r['own_state_rule_audit'] for r in valid if r['own_state_rule_audit'] is not None]
        calls=[r for r in requests if r['mode']==mode]
        parsers=read_rows(folder/mode/'parser.jsonl')
        successful_parsers=[r for r in parsers if r['status']=='ok']
        parsers_for_turn={r['step']:r for r in successful_parsers}
        accepted_parsers=[parsers_for_turn[r['step']] for r in valid]
        usage=Counter()
        for r in calls:
            usage.update({k:v for k,v in r.get('usage',{}).items() if isinstance(v,(int,float)) and not isinstance(v,bool)})
        final=valid[-1] if valid else None
        metrics.append(dict(mode=mode,planned_turns=planned_turns,valid_turns=len(valid),
            ending_id=final['output']['new_state']['ending_id'] if final else None,
            final_state_matches_reference=final['reference_trajectory']['state'] if final else False,
            final_action_matches_rules=bool(final and final.get('own_state_rule_audit') and final['own_state_rule_audit']['allowed'] and final['own_state_rule_audit']['state']),
            allowed_matches=sum(r['reference_trajectory']['allowed'] for r in valid),
            state_matches=sum(r['reference_trajectory']['state'] for r in valid),
            visible_objects_matches=sum(r['reference_trajectory']['visible_objects'] for r in valid),
            own_state_auditable_turns=len(audits),
            own_state_permission_disagreements=sum(not a['allowed'] for a in audits),
            own_state_transition_disagreements=sum(not a['state'] for a in audits),
            parser_exact_field_matches=sum(all(r['expected_field_matches'].values()) for r in accepted_parsers),
            provider_calls=len(calls),provider_errors=sum(r['status']=='error' for r in calls),
            interrupted_turn_attempts=sum(r['status']=='error' for r in rows),
            request_latency_ms=round(sum(r['latency_ms'] for r in calls),3),usage=dict(usage)))
    result=dict(episodes=metrics,actual_provider_calls=len(requests),
                provider_errors=sum(r['status']=='error' for r in requests),
                limitations=['same-engine reference','development walkthrough','single run',
                             'no prose leakage review','independent parsers after state divergence'])
    (folder/'benchmark-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    flat=[{k:v for k,v in m.items() if k!='usage'} for m in metrics]
    with (folder/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    write_turns_csv(folder)
    lines=['# ผลทดลองเล่นคดี A ต่อเนื่องผ่าน Gemini API','',
           'ใช้ข้อความภาษาไทย 25 ข้อชุดเดียวกัน แต่ละระบบเริ่มจากสถานะเดียวกันและนำสถานะของตัวเองไปใช้ในตาถัดไป',
           'แต่ละฝั่งเรียก Gemini ตีความจากสถานะของตัวเอง จึงไม่ได้ใช้ผลตีความร่วมกันเหมือนชุดทดลอง 6 กรณี',
           'Neural ใช้ Gemini ตัดสิน ส่วน NeSy ใช้กฎ Symbolic ไม่มี Fast-path หรือการซ่อมคำตอบผิดกฎ',
           'เมื่อบริการขัดข้องเก็บข้อผิดพลาดไว้ และเล่นต่อจากสถานะล่าสุดโดยไม่รีเซ็ต', '',
           '| ระบบ | ตาที่มีผล | ฉากจบที่รายงาน | อนุญาตตรง | สถานะตรง | วัตถุตรง | เปลี่ยนสถานะขัดกฎจากสถานะของตัวเอง |',
           '|---|---:|---|---:|---:|---:|---:|']
    for m in metrics:
        n=m['valid_turns']
        lines.append(f"| {m['mode']} | {n}/{m['planned_turns']} | {m['ending_id']} | {m['allowed_matches']}/{n} | {m['state_matches']}/{n} | {m['visible_objects_matches']}/{n} | {m['own_state_transition_disagreements']}/{m['own_state_auditable_turns']} |")
    lines += ['',f"เรียก API รวม {len(requests)} ครั้ง รวมข้อผิดพลาดบริการ {result['provider_errors']} ครั้ง ไม่ได้นับข้อผิดพลาดบริการเป็นการตอบผิดกฎ",'',
              '## ตัวอย่างความแตกต่างของการเปลี่ยนสถานะ']
    for mode in ['neural','neuro-symbolic']:
        for r in read_rows(folder/mode/'turns.jsonl'):
            audit=r.get('own_state_rule_audit')
            if r['status']=='ok' and audit and not audit['state']:
                lines.append(f"- {mode} ตา {r['step']}: {r['command']['raw_text']} — ช่องที่เปลี่ยนไม่ตรงกฎ: {', '.join(audit['state_differences'])}")
    lines += ['', '## ข้อจำกัด',
              '- ผลอ้างอิงและตัวตรวจใช้ Symbolic engine เดียวกับ NeSy จึงยังไม่ใช่เฉลยจากผู้ตรวจอิสระ',
              '- ข้อความเขียนจากชื่อและหัวข้อใน walkthrough สำหรับพัฒนา ไม่ใช่ชุดใหม่จากผู้เล่นอิสระ',
              '- ความต่างหลายตาอาจสะสมจากข้อผิดพลาดครั้งเดียว ให้แยกจาก own-state audit',
              '- ฉากจบที่โมเดลรายงานไม่เท่ากับสถานะสุดท้ายตรงอ้างอิง ดู final_state_matches_reference และ final_action_matches_rules',
              '- ยังไม่ตรวจว่าข้อความบรรยายเปิดเผยข้อมูลก่อนเงื่อนไขครบหรือไม่',
              '- ทดลองหนึ่งรอบ เฉพาะคดี A ไม่ใช่ผลครบ A/B/C หรือผลเชิงนัยสำคัญทางสถิติ',
              '- latency ในตารางคือเวลาคำขอรวมข้อผิดพลาด ไม่รวมช่วงเว้นระยะหรือเวลาหยุดรอเล่นต่อ', '',
              'ไฟล์หลัก: inputs.json, requests.jsonl, neural/turns.jsonl, neuro-symbolic/turns.jsonl, benchmark-summary.json, comparison.csv']
    (folder/'report-th.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    print(json.dumps(summarize(p.parse_args().folder),ensure_ascii=True,indent=2))
