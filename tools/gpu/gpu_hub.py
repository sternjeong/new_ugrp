"""Kaggle GPU 관제 센터: 노트북 제출·상태 추적·결과 회수·쿼터 현황을 한곳에서 다룬다.

사용법 (어느 레포에서든, install.sh로 `gpuhub`를 설치한 뒤):
    gpuhub serve                       # 대시보드 http://127.0.0.1:8765
    gpuhub submit path/to/note.ipynb   # 현재 디렉터리 기준 경로
    gpuhub sync                        # 상태 갱신 + 완료된 결과 내려받기
    gpuhub status

표준 라이브러리와 `kaggle` CLI만 사용한다. 상태·인증·결과는 `~/.gpu-hub/`(GPU_HUB_HOME)에 저장한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path(os.environ.get("GPU_HUB_HOME") or Path.home() / ".gpu-hub")
USER_HOME = Path.home()
RUNS_FILE = HOME / "runs.json"
DATASETS_FILE = HOME / "datasets.json"
CONFIG_FILE = HOME / "config.json"
OUTPUTS = HOME / "outputs"
STAGING = HOME / "staging"
PAGE = Path(__file__).with_name("dashboard.html")
BROWSER_SH = Path(__file__).with_name("browser.sh")
NOVNC_PORT = 6080   # browser.sh 가 띄우는 websockify(noVNC). /browser/ 아래로 프록시한다.
CDP_PORT = 9222     # 크롬 원격 디버깅(자동화용)

DEFAULTS = {
    "roots": ["~/repos"],         # 대시보드가 노트북을 찾아볼 폴더들
    "kaggle_user": "",            # 비우면 `kaggle config view`에서 찾는다.
    "weekly_gpu_hours": 30,       # 공식 쿼터를 못 읽을 때 쓰는 로컬 추정 한도
    "week_reset": "SAT 00:00 UTC",  # 표시용. 계산은 아래 week_start()가 한다.
    "default_timeout_min": 120,   # 실험 1회 상한. 쿼터 방어용.
    "accelerator": "NvidiaTeslaT4",
}
TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED", "CANCELED"}
KAGGLE = os.environ.get("KAGGLE_BIN") or str(HOME / "venv" / "bin" / "kaggle")
if not Path(KAGGLE).exists():
    KAGGLE = shutil.which("kaggle") or KAGGLE

LOCK = threading.RLock()


# ---------- 저장소 ----------
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def config() -> dict:
    return {**DEFAULTS, **load_json(CONFIG_FILE, {})}


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


# ---------- Kaggle CLI ----------
def kaggle(*args: str, timeout: int = 120) -> tuple[int, str]:
    try:
        p = subprocess.run([KAGGLE, *args], capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except FileNotFoundError:
        return 127, "kaggle CLI를 찾을 수 없습니다. tools/gpu/install.sh를 실행하세요."
    except subprocess.TimeoutExpired:
        return 124, "kaggle CLI 시간 초과"
    return p.returncode, (p.stdout + p.stderr).strip()


def kaggle_user() -> str:
    cfg = config()
    if cfg["kaggle_user"]:
        return cfg["kaggle_user"]
    if os.environ.get("KAGGLE_USERNAME"):
        return os.environ["KAGGLE_USERNAME"]
    creds = load_json(Path.home() / ".kaggle" / "kaggle.json", {})
    if creds.get("username"):
        return creds["username"]
    _, out = kaggle("config", "view")
    m = re.search(r"username:\s*([A-Za-z0-9_.-]+)", out)
    if m:
        return m.group(1)
    raise RuntimeError("Kaggle 사용자명을 알 수 없습니다. `kaggle auth login` 후 "
                       f"{CONFIG_FILE} 에 {{\"kaggle_user\": \"...\"}} 를 넣어 주세요.")


def authed() -> bool:
    code, out = kaggle("quota", "--format", "json", timeout=30)
    return code == 0 and "Authentication required" not in out


# ---------- 쿼터 ----------
def week_start(ref: datetime) -> datetime:
    """Kaggle GPU 주간 쿼터는 토요일 00:00 UTC에 갱신되는 것으로 알려져 있다(표시용 추정)."""
    d = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=(d.weekday() - 5) % 7)


def official_quota() -> dict:
    code, out = kaggle("quota", "--format", "json", timeout=30)
    if code != 0:
        return {"ok": False, "message": out.splitlines()[0] if out else "quota 조회 실패"}
    try:
        return {"ok": True, "data": json.loads(out), "raw": out}
    except ValueError:
        return {"ok": True, "data": None, "raw": out}  # 표 형식 등: 원문 그대로 보여준다.


def local_usage(runs: list[dict]) -> dict:
    cfg = config()
    start = week_start(now())
    used = 0.0
    for r in runs:
        if r.get("accelerator") in (None, "", "none"):
            continue
        s = datetime.fromisoformat(r["submitted_at"])
        e = datetime.fromisoformat(r["ended_at"]) if r.get("ended_at") else now()
        lo, hi = max(s, start), e
        if hi > lo:
            used += (hi - lo).total_seconds() / 3600
    limit = float(cfg["weekly_gpu_hours"])
    return {
        "week_start": iso(start), "next_reset": iso(start + timedelta(days=7)),
        "used_hours": round(used, 2), "limit_hours": limit,
        "remaining_hours": round(max(limit - used, 0), 2),
        "note": "제출~종료 벽시계 시간(대기열 포함) 기준의 상한 추정치입니다. 공식 값이 우선입니다.",
    }


# ---------- 실행 기록 ----------
def load_runs() -> list[dict]:
    return load_json(RUNS_FILE, [])


def repo_root(path: Path) -> Path:
    for d in path.parents:
        if (d / ".git").exists():
            return d
    return path.parent


def repo_name(path: Path) -> str:
    return repo_root(path).name


def notebook_inputs(nb: Path) -> list[Path]:
    """노트북 metadata.gpuhub.inputs(저장소 루트 기준 상대 경로)에 적힌 입력 파일."""
    try:
        meta = json.loads(nb.read_text(encoding="utf-8")).get("metadata", {}).get("gpuhub", {})
    except (OSError, ValueError):
        return []
    files = []
    for rel in meta.get("inputs", []):
        p = (repo_root(nb) / rel).resolve()
        if not p.is_file() or USER_HOME not in p.parents:
            raise ValueError(f"입력 파일을 찾을 수 없습니다: {rel}")
        files.append(p)
    if len({p.name for p in files}) != len(files):
        raise ValueError("입력 파일 이름이 겹칩니다(데이터셋은 한 폴더에 평평하게 올라갑니다).")
    return files


def ensure_dataset(user: str, files: list[Path]) -> str:
    """입력 파일을 비공개 Kaggle 데이터셋으로 올린다. 내용 해시가 같으면 이미 올린 것을 재사용한다."""
    h = hashlib.sha256()
    for p in sorted(files, key=lambda x: x.name):
        h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
    name = f"gpuhub-{h.hexdigest()[:10]}"
    ds_id = f"{user}/{name}"
    cache = load_json(DATASETS_FILE, {})
    if cache.get(name) == ds_id:
        return ds_id
    stage = STAGING / name
    stage.mkdir(parents=True, exist_ok=True)
    for p in files:
        shutil.copy2(p, stage / p.name)
    save_json(stage / "dataset-metadata.json", {"title": name, "id": ds_id, "licenses": [{"name": "CC0-1.0"}]})
    code, out = kaggle("datasets", "create", "-p", str(stage), "-t", "-q", timeout=600)
    if code != 0 and "already" not in out.lower():
        raise RuntimeError(f"데이터셋 업로드 실패: {out}")
    for _ in range(60):  # Kaggle 이 파일을 처리할 때까지 최대 5분
        code, out = kaggle("datasets", "status", ds_id, timeout=60)
        if code == 0 and "ready" in out.lower():
            break
        time.sleep(5)
    else:
        raise RuntimeError(f"데이터셋이 준비되지 않았습니다: {out}")
    save_json(DATASETS_FILE, {**cache, name: ds_id})
    return ds_id


def find_notebooks() -> list[dict]:
    skip = {".git", "node_modules", "__pycache__", ".ipynb_checkpoints", "venv", ".local", "outputs"}
    found = []
    for root in config()["roots"]:
        for dp, dns, fns in os.walk(Path(root).expanduser()):
            dns[:] = [d for d in dns if d not in skip and not d.startswith(".venv")]
            found += [Path(dp, f) for f in fns if f.endswith(".ipynb")]
    return [{"path": str(p), "repo": repo_name(p), "name": p.name} for p in sorted(set(found))]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "run"


def submit(notebook: str, accelerator: str | None = None, timeout_min: int | None = None,
           note: str = "") -> dict:
    cfg = config()
    nb = Path(notebook).expanduser().resolve()
    if not nb.is_file() or nb.suffix != ".ipynb":
        raise ValueError(f"노트북(.ipynb)을 찾을 수 없습니다: {notebook}")
    if USER_HOME not in nb.parents:
        raise ValueError("홈 디렉터리 밖의 노트북은 제출할 수 없습니다.")
    user = kaggle_user()
    accelerator = accelerator or cfg["accelerator"]
    timeout_min = int(timeout_min or cfg["default_timeout_min"])
    inputs = notebook_inputs(nb)
    dataset = ensure_dataset(user, inputs) if inputs else None
    with LOCK:
        runs = load_runs()
        left = local_usage(runs)["remaining_hours"]
        if accelerator != "none" and left * 60 < timeout_min:
            raise ValueError(f"남은 추정 GPU {left}시간이 상한 {timeout_min}분보다 적습니다. "
                             "상한을 낮추거나 갱신일을 기다려 주세요.")
        run_id = now().strftime("%Y%m%d-%H%M%S") + "-" + slugify(nb.stem)[:24]
        slug = slugify(f"ugrp-{nb.stem}-{run_id[-6:]}")
        stage = STAGING / run_id
        stage.mkdir(parents=True, exist_ok=True)
        shutil.copy2(nb, stage / nb.name)
        meta = {
            "id": f"{user}/{slug}", "title": slug, "code_file": nb.name, "language": "python",
            "kernel_type": "notebook", "is_private": True,
            "enable_gpu": accelerator != "none", "enable_internet": True,
            "dataset_sources": [dataset] if dataset else [], "competition_sources": [], "kernel_sources": [],
        }
        save_json(stage / "kernel-metadata.json", meta)
        args = ["kernels", "push", "-p", str(stage), "-t", str(timeout_min * 60)]
        if accelerator != "none":
            args += ["--accelerator", accelerator]
        code, out = kaggle(*args, timeout=300)
        run = {
            "id": run_id, "kernel": meta["id"], "notebook": str(nb), "repo": repo_name(nb), "dataset": dataset,
            "accelerator": accelerator, "timeout_min": timeout_min, "note": note,
            "submitted_at": iso(now()), "ended_at": None, "status": "QUEUED" if code == 0 else "ERROR",
            "message": out[-600:], "output_dir": None,
        }
        if code != 0:
            run["ended_at"] = run["submitted_at"]
        runs.append(run)
        save_json(RUNS_FILE, runs)
    if code != 0:
        raise RuntimeError(out)
    return run


def parse_status(text: str) -> str | None:
    m = re.search(r'status\s+"?(?:KernelWorkerStatus\.)?([A-Za-z_]+)"?', text)
    return m.group(1).upper() if m else None


def sync() -> list[dict]:
    """진행 중인 실행의 상태를 갱신하고, 끝난 실행은 결과를 내려받는다."""
    with LOCK:
        runs = load_runs()
        for r in runs:
            if r["status"] in TERMINAL and (r.get("output_dir") or r["status"] != "COMPLETE"):
                continue
            if r["status"] not in TERMINAL:
                code, out = kaggle("kernels", "status", r["kernel"], timeout=60)
                st = parse_status(out) if code == 0 else None
                if st:
                    r["status"] = st
                else:
                    r["message"] = out[-300:]
                    continue
                if st in TERMINAL:
                    r["ended_at"] = iso(now())
            if r["status"] in TERMINAL:
                dest = OUTPUTS / r["id"]
                dest.mkdir(parents=True, exist_ok=True)
                code, out = kaggle("kernels", "output", r["kernel"], "-p", str(dest), timeout=600)
                r["message"] = out[-600:]
                if code == 0:
                    r["output_dir"] = str(dest)
        save_json(RUNS_FILE, runs)
        return runs


# ---------- VM 크롬 ----------
def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def browser_status() -> dict:
    return {"viewer": port_open(NOVNC_PORT), "chrome": port_open(CDP_PORT)}


def browser_start() -> dict:
    p = subprocess.run(["bash", str(BROWSER_SH)], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError((p.stdout + p.stderr).strip() or "크롬 시작 실패")
    for _ in range(20):
        st = browser_status()
        if all(st.values()):
            break
        time.sleep(0.5)
    return st


def snapshot() -> dict:
    runs = load_runs()
    return {
        "now": iso(now()), "authed": authed(), "user": _safe_user(),
        "official": official_quota(), "local": local_usage(runs),
        "config": config(), "runs": list(reversed(runs)),
        "notebooks": find_notebooks(), "browser": browser_status(),
    }


def _safe_user() -> str:
    try:
        return kaggle_user()
    except RuntimeError:
        return ""


# ---------- 서버 ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json(self, code: int, obj):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode())

    def proxy_browser(self):
        """/browser/* 를 noVNC로 그대로 넘긴다. WebSocket(Upgrade)도 바이트 단위로 중계한다."""
        try:
            up = socket.create_connection(("127.0.0.1", NOVNC_PORT), timeout=5)
        except OSError:
            return self.send(502, "크롬 화면이 꺼져 있습니다. 관제 센터에서 '크롬 열기'를 누르세요.".encode(),
                             "text/plain; charset=utf-8")
        up.settimeout(None)
        head = f"{self.command} {self.path[len('/browser'):] or '/'} HTTP/1.1\r\n"
        hdrs = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items() if k.lower() != "connection")
        conn = "Upgrade" if self.headers.get("Upgrade") else "close"
        up.sendall((head + hdrs + f"Connection: {conn}\r\n\r\n").encode("latin-1"))
        self.close_connection = True
        client = self.connection

        def pump(src, dst):
            try:
                while data := src.recv(65536):
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                for sock in (src, dst):
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        t = threading.Thread(target=pump, args=(client, up), daemon=True)
        t.start()
        pump(up, client)
        t.join(1)
        up.close()

    def do_GET(self):
        if self.path.startswith("/browser/"):
            return self.proxy_browser()
        if self.path == "/":
            self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self.json(200, snapshot())
        else:
            self.json(404, {"error": "not found"})

    def do_POST(self):
        # 로컬 도구이므로 다른 출처의 요청(CSRF)을 막는다.
        # code-server /proxy/<port>/ 를 거치면 원래 호스트는 X-Forwarded-Host 에 남는다.
        hosts = {self.headers.get("Host", ""), *(self.headers.get("X-Forwarded-Host") or "").split(",")}
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] not in {h.strip() for h in hosts}:
            return self.json(403, {"error": "forbidden origin"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/sync":
                sync()
                return self.json(200, snapshot())
            if self.path == "/api/browser/start":
                return self.json(200, browser_start())
            if self.path == "/api/submit":
                run = submit(body.get("notebook", ""), body.get("accelerator"),
                             body.get("timeout_min"), body.get("note", ""))
                return self.json(200, run)
            self.json(404, {"error": "not found"})
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
            self.json(400, {"error": str(e)})


def poller(interval: int = 60) -> None:
    while True:
        time.sleep(interval)
        try:
            if any(r["status"] not in TERMINAL for r in load_runs()):
                sync()
        except Exception as e:  # 폴링 스레드는 죽지 않게 한다.
            print("poll error:", e, file=sys.stderr)


def serve(host: str, port: int) -> None:
    threading.Thread(target=poller, daemon=True).start()
    print(f"GPU 관제 센터: http://{host}:{port}  (원격 접속은 ssh -L {port}:127.0.0.1:{port} 사용)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


# ---------- CLI ----------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    p = sub.add_parser("submit")
    p.add_argument("notebook")
    p.add_argument("--accelerator", help="NvidiaTeslaT4 | NvidiaTeslaP100 | none")
    p.add_argument("--timeout-min", type=int)
    p.add_argument("--note", default="")
    sub.add_parser("sync")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "serve":
        serve(a.host, a.port)
    elif a.cmd == "submit":
        print(json.dumps(submit(a.notebook, a.accelerator, a.timeout_min, a.note), ensure_ascii=False, indent=2))
    elif a.cmd == "sync":
        for r in sync():
            print(r["id"], r["status"], r.get("output_dir") or "")
    else:
        snap = snapshot()
        loc = snap["local"]
        print(f"인증: {'OK' if snap['authed'] else '필요(kaggle auth login)'}  사용자: {snap['user'] or '-'}")
        print(f"이번 주 추정 사용 {loc['used_hours']}h / {loc['limit_hours']}h (남음 {loc['remaining_hours']}h, 갱신 {loc['next_reset']})")
        print("공식 쿼터:", snap["official"].get("raw") or snap["official"].get("message"))


if __name__ == "__main__":
    main()
