"""LLM worker for the AI research guide and paper summaries. Runs in a tmux session on a machine where the
Claude Code CLI is logged in, so no API key is needed:

    tmux new -d -s curri-llm 'python3 tools/llm_worker/worker.py --config .local/llm_worker.json'

It long-polls the service for a job, runs it as an isolated, tool-less `claude -p` call with the job's JSON schema,
and posts the structured result back. The service validates every answer before showing it.
Config: {"base_url": "https://3mincurri.duckdns.org", "token": "<same as server .local/llm_worker_token>"}
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

CALL_TIMEOUT = 420


def http(method, url, token, body=None, timeout=40):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b'{}')


def run_claude(job):
    cmd = ['claude', '-p', '--model', job.get('model', 'sonnet'), '--effort', job.get('effort', 'medium'), '--tools', '',
           '--no-session-persistence', '--system-prompt', job['system'], '--output-format', 'json',
           '--json-schema', json.dumps(job['schema'], separators=(',', ':'))]
    start = time.time()
    proc = subprocess.run(cmd, input=job['prompt'], text=True, capture_output=True, cwd='/tmp', timeout=CALL_TIMEOUT)
    parsed = json.loads(proc.stdout)
    value = parsed.get('structured_output')
    ok = proc.returncode == 0 and not parsed.get('is_error') and isinstance(value, dict)
    return {'ok': ok, 'result': value if ok else None, 'error': None if ok else str(parsed.get('result') or proc.stderr)[:300],
            'seconds': round(time.time() - start, 1), 'cost': parsed.get('total_cost_usd')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path('.local/llm_worker.json'))
    parser.add_argument('--once', action='store_true', help='한 작업만 처리하고 끝냄(점검용)')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    base, token = cfg['base_url'].rstrip('/'), cfg['token']
    print(f'LLM 워커 시작: {base}', flush=True)
    backoff = 5
    while True:
        try:
            job = http('GET', f'{base}/api/llm/poll?wait=25', token).get('job')
            backoff = 5
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            print(f'서버 연결 실패({type(exc).__name__}), {backoff}초 뒤 재시도', flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
            continue
        if not job:
            if args.once:
                return
            continue
        print(f"작업 {job['id']} ({job['kind']}) 처리 중…", flush=True)
        try:
            answer = run_claude(job)
        except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
            answer = {'ok': False, 'error': type(exc).__name__}
        try:
            reply = http('POST', f'{base}/api/llm/answer', token, {'job_id': job['id'], **answer})
            print(f"작업 {job['id']}: {'성공' if answer['ok'] else '실패 ' + str(answer.get('error'))[:80]} → {reply.get('status')} "
                  f"({answer.get('seconds', '?')}초)", flush=True)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"작업 {job['id']} 결과 전송 실패: {type(exc).__name__}", flush=True)
        if args.once:
            return


if __name__ == '__main__':
    main()
