"""Freeze corpus-grounded synthetic query text and source-backed topic targets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "query_rich_v3"

# A representative title in a first-five paper for each target. The title is
# evidence of topic presence, not a gold relevance label for every lab.
TOPICS = {
    "battery": ("전고체 배터리", "lab:269027c5b93829258d2eef4d0a38f196", "All-Solid-State Li Batteries"),
    "photonics": ("광자 양자통신", "lab:04a4270953e536b3d89b39189ea28f5a", "Quantum communication with time-bin"),
    "robotics": ("로봇 동작 학습", "lab:032749fe44cb8a804902ff1aa9236d09", "Motion Retargeting"),
    "llm": ("대형 언어모델 최적화", "lab:12eecc7d8bcdc47fda0b04b169c3a660", "Pruning Large Language Models"),
    "semiconductor": ("반도체 트랜지스터 센서", "lab:00a146f5c5267ed6caeb590edaa47fac", "Detection of Urea Using Si Electrolyte-Gated Transistor"),
    "neuroscience": ("작업 기억 신경회로", "lab:537bec3b2e35d774cf892c88ca3255cb", "Interneurons in Working Memory"),
    "wireless": ("무선 의미통신", "lab:247c2d847af8f32337fb7de6ad268360", "Channel-Adaptive Digital Semantic Communications"),
    "microscopy": ("홀로그래픽 현미경", "lab:19b352c9ef06346d69d36e9456cdff0d", "Digital in-line holographic microscopy"),
    "architecture": ("메모리 중심 컴퓨터 구조", "lab:8ad648173a74311bbdf5fd7872955c27", "Near-Data Processing in CXL Memory"),
    "haptics": ("햅틱 상호작용", "lab:e5c3fc5f5173e1479fd4e72edd9c0599", "Haptic Effects"),
    "radar": ("레이더 신호처리", "lab:820d6eb33837425aab1270d236524366", "Radar-Based People Counting"),
    "microbiome": ("장내 미생물", "lab:fdf7c49c167de224cc78528fcfdcfbe8", "Food antigens drive spontaneous IgE elevation"),
}

POSITIVE = [
    ("battery", "전고체 배터리 소재를 연구해 보고 싶어요."),
    ("photonics", "광자를 이용한 양자통신이 궁금합니다."),
    ("robotics", "로봇 동작 학습을 다루는 연구실을 찾고 싶습니다."),
    ("llm", "대형 언어모델의 효율을 높이는 연구를 하고 싶어요."),
    ("semiconductor", "반도체 트랜지스터 센서에 관심이 있습니다."),
    ("neuroscience", "기억을 담당하는 신경회로가 궁금해요."),
    ("wireless", "무선 의미통신 연구를 해보고 싶습니다."),
    ("microscopy", "홀로그래픽 현미경으로 세포를 관찰하는 연구가 좋아요."),
    ("architecture", "메모리 중심 컴퓨터 구조를 공부하고 싶어요."),
    ("haptics", "햅틱 상호작용 기술을 연구하고 싶습니다."),
    ("radar", "레이더 신호처리와 영상화에 관심이 있어요."),
    ("microbiome", "장내 미생물과 면역의 관계를 알고 싶어요."),
    ("battery", "리튬 금속 전지의 고체 전해질 연구실을 찾습니다."),
    ("photonics", "얽힌 광자로 정보를 보내는 연구를 하고 싶어요."),
    ("robotics", "로봇이 사람의 행동을 학습하는 문제에 관심 있습니다."),
    ("llm", "언어모델 경량화 방법이 궁금합니다."),
    ("semiconductor", "실리콘 기반 센서 소자를 만들고 싶어요."),
    ("wireless", "통신 채널에 맞춰 정보를 보내는 방법을 연구하고 싶어요."),
    ("haptics", "촉각 피드백을 만드는 연구가 재미있습니다."),
    ("radar", "SAR 레이더 영상 처리에 관심이 있습니다."),
]

NEGATIVE_PAIRS = [
    ("battery", "robotics"), ("robotics", "battery"),
    ("photonics", "microbiome"), ("microbiome", "photonics"),
    ("llm", "semiconductor"), ("semiconductor", "llm"),
    ("neuroscience", "architecture"), ("architecture", "neuroscience"),
    ("wireless", "haptics"), ("haptics", "wireless"),
    ("microscopy", "radar"), ("radar", "microscopy"),
    ("battery", "photonics"), ("microbiome", "robotics"),
    ("semiconductor", "wireless"),
]

AMBIGUOUS_PAIRS = [
    ("battery", "semiconductor"), ("photonics", "robotics"),
    ("llm", "neuroscience"), ("wireless", "radar"),
    ("haptics", "microscopy"), ("architecture", "llm"),
    ("microbiome", "battery"), ("robotics", "haptics"),
    ("semiconductor", "photonics"), ("neuroscience", "microbiome"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def particle(label: str, no_final: str, with_final: str) -> str:
    last = next((char for char in reversed(label) if "가" <= char <= "힣"), None)
    if last is None:
        raise ValueError(f"topic label has no Hangul: {label}")
    return with_final if (ord(last) - ord("가")) % 28 else no_final


def main() -> None:
    if OUT.exists():
        raise RuntimeError("existing query targets are immutable")
    packet_path = RESULTS / "holdout_relevance_v1/packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    evidence = {}
    for key, (label, lab_id, match) in TOPICS.items():
        lab = packet["labs"][lab_id]
        options = [(index, paper["title"]) for index, paper in enumerate(lab["representative_papers"][:5])
                   if match.casefold() in paper["title"].casefold()]
        if len(options) != 1:
            raise ValueError(f"target title evidence not unique: {key}: {options}")
        index, title = options[0]
        evidence[key] = {"label": label, "lab_id": lab_id,
                         "source_list": "representative_papers", "source_index": index,
                         "paper_title": title}
    queries = []
    for topic, text in POSITIVE:
        queries.append({"id": f"q{len(queries)+1:02d}", "text": text, "group": "positive_only",
                        "positive_targets": [topic], "negative_targets": [], "ambiguous": False})
    for index, (bad, good) in enumerate(NEGATIVE_PAIRS):
        b, g = TOPICS[bad][0], TOPICS[good][0]
        for style in (0, 1):
            text = (f"{b}{particle(b, '는', '은')} 싫고 {g}{particle(g, '를', '을')} 연구하고 싶어요."
                    if style == 0 else f"{b} 말고 {g}에 관심이 있어요.")
            queries.append({"id": f"q{len(queries)+1:02d}", "text": text,
                            "group": "explicit_negative", "positive_targets": [good],
                            "negative_targets": [bad], "ambiguous": False})
    for index, (first, second) in enumerate(AMBIGUOUS_PAIRS):
        a, b = TOPICS[first][0], TOPICS[second][0]
        text = (f"{a}도 흥미롭지만 {b}{particle(b, '가', '이')} 더 끌려요." if index % 2 == 0 else
                f"{a}{particle(a, '는', '은')} 해봤고 {b}도 궁금해요. 어느 쪽이 맞을까요?")
        queries.append({"id": f"q{len(queries)+1:02d}", "text": text,
                        "group": "ambiguous", "positive_targets": [first, second],
                        "negative_targets": [], "ambiguous": True})
    if len(queries) != 60:
        raise ValueError("query count mismatch")
    OUT.mkdir()
    path = OUT / "query_targets.json"
    path.write_text(json.dumps({"status": "frozen_before_rankings", "topics": evidence,
                                "queries": queries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"query_targets_sha256": sha(path), "relation_packet_sha256": sha(packet_path),
                "script_sha256": sha(Path(__file__)), "queries": 60, "topics": len(evidence),
                "scope": "corpus-grounded synthetic challenge set; not real-user prevalence"}
    (OUT / "targets_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
