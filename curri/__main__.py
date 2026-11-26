import argparse
import os
from pathlib import Path
from .community import Community
from .curated_catalog import CuratedCatalog
from .curated_query_engine import CuratedQueryEngine, RagQueryEngine
from .embed_broker import EmbedBroker
from .kaggle_launcher import KaggleLauncher
from .meeting_links import load_provider
from .platform import Platform
from .server import make_server
from .store import Store
from .research_papers import ResearchPapers

REMOTE_WAIT = 15.0  # seconds RagQueryEngine waits for the worker's chunk scores, and again for the reranker


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description='3분커리 로컬 프로토타입')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--data-dir', type=Path, default=root / 'data' / 'sunwoo')
    parser.add_argument('--db', type=Path, default=root / '.local' / 'curri.sqlite')
    parser.add_argument('--secure-cookie', action='store_true', help='HTTPS 프록시 환경에서 Secure 쿠키 사용')
    parser.add_argument('--no-demo-data', action='store_true', help='더미 선배·후기·쪽지 시드를 넣지 않음(이미 넣은 데이터는 유지)')
    parser.add_argument('--worker-token-file', type=Path, default=root / '.local' / 'worker_token', help='임베딩 워커(Kaggle 등) 인증 토큰 파일. 없으면 워커 연동을 끈다')
    parser.add_argument('--no-query-engine', action='store_true', help='질의 해석·임베딩 검색 엔진을 끄고 이전 사전 검색만 사용')
    parser.add_argument('--search-engine', choices=['rag', 'curated'], default='rag', help='rag: 팀원 vectorRAG 엔진(R2 요약·R5 리랭커·R7 질의 재작성, 워커가 조각 점수와 리랭커 계산), curated: 이전 엔진(사전·구절 임베딩·질의 분석 RRF). rag는 data/sunwoo/search_chunks.jsonl이 있어야 한다')
    parser.add_argument('--kaggle-launcher-config', type=Path, default=root / '.local' / 'kaggle_launcher.json', help='없으면 사용자 질의로 Kaggle 워커를 자동 시작하지 않음')
    parser.add_argument('--meeting-links-config', type=Path, default=root / '.local' / 'meeting_links.json', help='온라인 만남 확정 시 Google Meet·Zoom 링크를 만들 설정. 없으면 링크를 직접 입력받음')
    parser.add_argument('--local-dir', type=Path, default=root / '.local', help='메일·관리자·LLM 워커·개인정보 슬롯 등 설정 파일 폴더')
    parser.add_argument('--guide-variant-file', type=Path, default=root / '.local' / 'guide_variant', help='가이드 버전 A 또는 B가 적힌 파일. 없으면 A')
    args = parser.parse_args()
    try:
        catalog = CuratedCatalog(args.data_dir)
        meeting_links = load_provider(args.meeting_links_config)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    store = Store(args.db)
    community = Community(store, catalog, args.data_dir, seed=not args.no_demo_data, meeting_links=meeting_links)
    broker = None
    if args.worker_token_file.is_file() and args.worker_token_file.read_text().strip():
        broker = EmbedBroker(args.worker_token_file.read_text().strip(), store=store)
    launcher = KaggleLauncher(args.kaggle_launcher_config) if broker and args.kaggle_launcher_config.is_file() else None
    research_papers = ResearchPapers(args.data_dir / 'papers.jsonl')
    try:
        platform = Platform(store, catalog, args.data_dir, args.local_dir, broker)
    except ValueError as exc:
        parser.error(str(exc))
    engine = None
    if not args.no_query_engine and args.search_engine == 'rag' and broker and (args.data_dir / 'search_chunks.jsonl').is_file():
        from .rag.query_llm import LlmQuery
        from .rag.remote import RemoteReranker, RemoteRetriever
        engine = RagQueryEngine(catalog, broker, RemoteRetriever(broker, args.data_dir / 'search_chunks.jsonl', timeout=REMOTE_WAIT),
                                reranker=RemoteReranker(broker, timeout=REMOTE_WAIT), rewriter=LlmQuery(platform.llm), launcher=launcher,
                                rerank_top=os.environ.get('CURRI_RERANK_TOP'))  # default curri/rag/rerank.TOP
    elif not args.no_query_engine:
        engine = CuratedQueryEngine(catalog, broker, launcher=launcher)
    platform.start()
    server = make_server(args.host, args.port, catalog, store, args.secure_cookie, community, engine, broker,
                         research_papers, args.guide_variant_file, platform)
    print(f'3분커리: http://{args.host}:{server.server_port} · 엔진 curated · 질의 엔진 {type(engine).__name__ if engine else "꺼짐"} · 임베딩 워커 {"대기" if broker else "없음"} · 만남 링크 {meeting_links.label if meeting_links else "직접 입력"} · 메일 {"발송" if platform.mailer.enabled else "보류(outbox)"} · AI 가이드 {"워커 대기" if platform.llm.enabled() else "꺼짐"} · 관리자 API {"켜짐" if platform.admin.enabled() else "꺼짐"} (종료: Ctrl+C)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
