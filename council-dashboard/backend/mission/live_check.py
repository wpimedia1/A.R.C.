"""Real Meta Model API check. Run from council-dashboard/backend:

    python -m mission.live_check

For each model: one tool-calling request, then one follow-up using previous_response_id.
Prints every response_id, created_at, model and token usage so each request can be matched
in the Meta developer dashboard. Exits non-zero on any failure. No database, no fallbacks.
"""
import json
import sys
import time
from pathlib import Path
import httpx
from .provider import (ENDPOINT, DIRECTOR_MODEL, SPECIALIST_MODEL, ProviderConfigError,
                       credential, fingerprint, cost_usd, send)

TOOL = {'type': 'function', 'name': 'record_sum', 'strict': True,
        'description': 'Record the sum of two integers.',
        'parameters': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}, 'sum': {'type': 'integer'}},
                       'required': ['a', 'b', 'sum'], 'additionalProperties': False}}
LOG_DIR = Path(__file__).resolve().parents[1] / 'data' / 'live-checks'


def check(model, key):
    steps = []
    first, corr1 = send({'model': model, 'input': 'Add 17 and 25. Call record_sum with a, b and sum.',
                         'tools': [TOOL], 'tool_choice': 'auto', 'max_output_tokens': 2048}, key)
    calls = [o for o in first.get('output', []) if o.get('type') == 'function_call']
    steps.append({'step': 'tool request', 'response_id': first.get('id'), 'model': first.get('model'), 'created_at': first.get('created_at'),
                  'status': first.get('status'), 'usage': first.get('usage'), 'cost_usd': cost_usd(model, first['usage']),
                  'tool_calls': [{'name': c['name'], 'arguments': c['arguments'], 'call_id': c.get('call_id')} for c in calls], **corr1})
    if not first.get('id'):
        raise RuntimeError(model + ': response has no id')
    if len(calls) != 1 or calls[0]['name'] != 'record_sum':
        raise RuntimeError(model + ': expected exactly one record_sum call, got ' + json.dumps([c.get('name') for c in calls]))
    args = json.loads(calls[0]['arguments'])
    correct = args.get('sum') == 42
    second, corr2 = send({'model': model, 'previous_response_id': first['id'], 'tools': [TOOL], 'tool_choice': 'auto', 'max_output_tokens': 2048,
                          'input': [{'type': 'function_call_output', 'call_id': calls[0]['call_id'],
                                     'output': json.dumps({'recorded': True, 'sum_correct': correct})}]}, key)
    text = ''.join(part.get('text', '') for o in second.get('output', []) if o.get('type') == 'message'
                   for part in o.get('content', []) if part.get('type') == 'output_text')
    steps.append({'step': 'follow-up via previous_response_id', 'previous_response_id': first['id'], 'response_id': second.get('id'),
                  'model': second.get('model'), 'created_at': second.get('created_at'), 'status': second.get('status'),
                  'usage': second.get('usage'), 'cost_usd': cost_usd(model, second['usage']), 'output_text': text[:500], **corr2})
    return {'model': model, 'arithmetic_correct': correct, 'steps': steps}


def main():
    try:
        key, source = credential()
    except ProviderConfigError as exc:
        print('FAIL:', exc, file=sys.stderr)
        return 2
    report = {'checked_at': time.time(), 'endpoint': ENDPOINT, 'key_source': source,
              'key_fingerprint': fingerprint(key), 'key_last4_local_only': key[-4:], 'results': [], 'failures': []}
    print(f'endpoint: {ENDPOINT}\nkey source: {source}\nkey ends with: …{key[-4:]}  fingerprint: {fingerprint(key)}')
    for model in (SPECIALIST_MODEL, DIRECTOR_MODEL):
        print(f'\n=== {model} ===')
        try:
            result = check(model, key)
            report['results'].append(result)
            for step in result['steps']:
                print(f"  {step['step']}: response_id={step['response_id']} http={step['http_status']} model={step['model']} "
                      f"created_at={step['created_at']} tokens in/out={step['usage']['input_tokens']}/{step['usage']['output_tokens']} "
                      f"cost=${step['cost_usd']:.6f} headers={step['response_headers']}")
            print(f"  arithmetic correct: {result['arithmetic_correct']}")
        except httpx.HTTPStatusError as exc:
            body = exc.response.text.replace(key, '[redacted]')[:800]
            report['failures'].append({'model': model, 'http_status': exc.response.status_code, 'body': body})
            print(f'  FAIL HTTP {exc.response.status_code}: {body}', file=sys.stderr)
        except Exception as exc:
            report['failures'].append({'model': model, 'error': f'{type(exc).__name__}: {exc}'.replace(key, '[redacted]')})
            print(f'  FAIL {type(exc).__name__}: {exc}'.replace(key, '[redacted]'), file=sys.stderr)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f'live-check-{int(report["checked_at"])}.json'
    report_public = {k: v for k, v in report.items() if k != 'key_last4_local_only'}
    path.write_text(json.dumps(report_public, indent=2), encoding='utf-8')
    print(f'\nlog: {path}')
    print('Verify: each response_id above must appear in your Meta developer dashboard.')
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    sys.exit(main())
