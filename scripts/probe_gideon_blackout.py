"""One direct Gemini parser request; no fast path, repair, retries or fallback."""
import json
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.cases import get_engine
from app.game_setup import new_game_state
from app.neural.gemini_client import DEFAULT_MODEL, get_genai_client, types
from app.neural.prompts import build_interpret_system_prompt
from app.schemas import ParsedCommand


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['case_01_gideon', 'case_02_vincent', 'case_03_liora'],
                        default='case_01_gideon')
    args = parser.parse_args()
    question = 'คุณอยู่ที่ไหนตอนไฟดับ'
    engine = get_engine(args.case)
    state = new_game_state(engine.world, args.case)
    system = build_interpret_system_prompt(engine.world, state=state, user_text=question,
                                          prune=True, use_knn=True, use_mmr=True)
    content = (
        f"ข้อความผู้เล่น (Raw Input): '{question}'\n"
        f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
        f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
        f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
    )
    now = datetime.now(timezone.utc)
    output = ROOT / 'logs/research' / f"gideon-blackout-api-{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    record = {'created_at_utc': now.isoformat(), 'case_id': args.case, 'question': question, 'model': DEFAULT_MODEL,
              'state': state.model_dump(mode='json'), 'system_prompt': system, 'content': content,
              'fast_path': False, 'repair': False, 'fallback': False, 'max_calls': 1}
    client = get_genai_client()
    if client is None:
        raise RuntimeError('Gemini is not configured')
    start = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL, contents=content,
            config=types.GenerateContentConfig(
                system_instruction=system, response_mime_type='application/json',
                response_schema=ParsedCommand, temperature=0.0,
                http_options=types.HttpOptions(timeout=15000,
                    retry_options=types.HttpRetryOptions(attempts=1)),
            ),
        )
        record['raw_response'] = response.text
        record['model_version'] = getattr(response, 'model_version', None)
        usage = getattr(response, 'usage_metadata', None)
        record['usage'] = usage.model_dump(mode='json') if usage else {}
        parsed = ParsedCommand.model_validate_json(response.text)
        record['parsed'] = parsed.model_dump(mode='json')
        # Audit the unmodified parse; never repair the model's output.
        record['symbolic_decision'] = engine.decide(parsed, state).model_dump(mode='json')
        record['status'] = 'ok'
    except Exception as exc:
        record['status'] = 'error'
        record['exception_type'] = type(exc).__name__
        message = str(getattr(exc, 'message', '') or '')
        message = re.sub(r'AIza[0-9A-Za-z_-]+', '[REDACTED]', message)
        message = re.sub(r'(?i)(key|token|authorization)([=:\s]+)[^\s&,]+',
                         r'\1\2[REDACTED]', message)
        record['error_message'] = message[:1200]
        code = getattr(exc, 'code', None)
        if isinstance(code, int):
            record['status_code'] = code
    record['latency_ms'] = round((time.perf_counter() - start) * 1000, 2)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('case_id', 'status', 'model', 'model_version', 'parsed',
          'symbolic_decision', 'latency_ms', 'exception_type', 'status_code', 'error_message') if k in record},
          ensure_ascii=False, indent=2))
    print(f'Saved: {output}')


if __name__ == '__main__':
    main()
