"""Wires the account, mail, events, LLM, watch, Q&A and admin pieces together from `.local/` config files.

Every file is optional: without mail.json mail is held in the outbox, without llm_worker_token the AI guide is off,
without admin_token the admin API answers 404.
"""
import json
from pathlib import Path
import secrets

from .accounts import Accounts
from .admin_api import AdminAPI
from .events import Events
from .llm_jobs import LLMJobs
from .mailer import Mailer
from .notifier import Notifier
from .privacy import load_slots
from .qna import LabQnA
from .research_guide import LabPapers, ResearchGuide
from .watch import LabWatch


def _secret(path):
    """Server secret for keyed hashes; created once and kept in .local/ (never committed)."""
    if path is None:
        return secrets.token_hex(32)
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip()


def _read(path):
    return Path(path).read_text().strip() if path and Path(path).is_file() and Path(path).read_text().strip() else None


class Platform:
    def __init__(self, store, catalog, data_dir=None, local_dir=None, broker=None, base_url='https://3mincurri.duckdns.org'):
        local = Path(local_dir) if local_dir else None
        cfg = lambda name: (local / name) if local else None
        self.secret = _secret(cfg('secret'))
        self.privacy_slots = load_slots(cfg('privacy.json'))
        site = json.loads(cfg('site.json').read_text()) if local and cfg('site.json').is_file() else {}
        self.mailer = Mailer(store, cfg('mail.json'), site.get('base_url', base_url))
        self.accounts = Accounts(store, self.mailer, catalog, site.get('graduate_domains', ['postech.ac.kr']))
        self.events = Events(store, self.secret, cfg('experiments.json'))
        self.llm = LLMJobs(store, _read(cfg('llm_worker_token')))
        papers = LabPapers(Path(data_dir) / 'papers.jsonl') if data_dir else LabPapers(Path('/nonexistent'))
        self.guide = ResearchGuide(catalog, papers)
        self.llm.register('guide', self.guide.validate)
        self.llm.register('summary', self.guide.validate_summary)
        self.watch = LabWatch(store, catalog, papers, self.mailer, site.get('openalex_mailto'))
        self.qna = LabQnA(store, catalog)
        self.notifier = Notifier(store, self.mailer)
        self.admin = AdminAPI(store, catalog, self.accounts, self.events, self.mailer, self.llm, self.guide, self.watch,
                              broker, _read(cfg('admin_token')), site.get('backup_dir') or (local / 'backups' if local else None))

    def start(self):
        """Background threads: mail sender, notifier and the weekly lab watch."""
        self.mailer.start()
        self.notifier.start()
        self.watch.start()
