"""The search engine's two model calls, answered by the embedding worker through EmbedBroker.

The server runs no model (BGE-M3 runs only on the worker's GPU). RagQueryEngine asks for
- lab_scores(phrases): every lab's first-pass score per phrase and its closest chunks (op 'lab_scores'), and
- score(query, documents): reranker probabilities (op 'rerank').
Both travel as a query job, so EmbedBroker caches them (memory and the phrase_sims table) like phrase similarities:
a student who did not consent to processing abroad gets only answers already cached.
"""
import json
from pathlib import Path

MAX_BATCH = 12  # EmbedBroker.MAX_PHRASES


class Unavailable(RuntimeError):
    """The worker is off, too slow, or this request may use only the cache and it missed."""


class Refused(Exception):
    """The worker's refusal check matched (args[0]: off_topic, procedure, too_vague or only_dislike)."""


def load_chunks(path):
    with open(path, encoding='utf-8') as stream:
        return {c['id']: c for c in (json.loads(line) for line in stream if line.strip())}


class RemoteRetriever:
    def __init__(self, broker, chunks, timeout=30.0):
        self.broker, self.timeout = broker, timeout
        self.chunks = load_chunks(chunks) if isinstance(chunks, (str, Path)) else chunks

    def ask(self, phrases, query, remote):
        found = self.broker.understand(phrases, query, self.timeout, remote=remote) if self.broker else None
        from ..embed_broker import query_key
        answer = (found or {}).get(query_key(query))
        if not isinstance(answer, dict):
            raise Unavailable('worker did not answer')
        return answer

    def lab_scores(self, phrases, remote=True, gate=None):
        """{phrase: {lab_id: (score, [(chunk_score, chunk), ...])}}, the shape of the engine branch's Retriever.
        gate=(raw query text, margin): the worker first checks the query against its refusal examples and raises
        Refused when a refusal type is closer than 'search' by more than the margin."""
        phrases = list(dict.fromkeys(phrases))
        out = {}
        for start in range(0, len(phrases), MAX_BATCH):
            part = phrases[start:start + MAX_BATCH]
            request = {'op': 'lab_scores', 'phrases': part}
            if gate and start == 0:
                request.update(raw=gate[0], gate=gate[1])
            answer = self.ask(part, request, remote)
            if 'labs' not in answer and answer.get('intent'):
                raise Refused(answer['intent'])
            labs = answer.get('labs')
            if not isinstance(labs, dict) or any(p not in labs for p in part):
                raise Unavailable('worker answer is missing phrases')
            for p in part:
                out[p] = {lab: (float(score), [(float(s), self.chunks[cid]) for cid, s in best if cid in self.chunks])
                          for lab, (score, best) in labs[p].items()}
        return out


class RemoteReranker:
    def __init__(self, broker, timeout=30.0):
        self.broker, self.timeout = broker, timeout

    def score(self, query, documents, phrases, remote=True):
        """Probabilities in the order of `documents`. `phrases` ride along because a broker job needs some."""
        request = {'op': 'rerank', 'query': query, 'documents': list(documents)}
        answer = RemoteRetriever.ask(self, phrases, request, remote)
        scores = answer.get('scores')
        if not isinstance(scores, list) or len(scores) != len(documents):
            raise Unavailable('reranker answer does not match the documents')
        return [float(s) for s in scores]
