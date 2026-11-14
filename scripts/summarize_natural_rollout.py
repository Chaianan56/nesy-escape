"""Rebuild full-run metrics from append-only logs, including resumed requests."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


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
