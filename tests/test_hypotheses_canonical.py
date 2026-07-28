"""Enforce README.md §Canonical Hypotheses (H1–H5) as the single source of truth."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL = {
    "H1": "BM25 performs competitively with FAISS on exact-match and terminology-sensitive queries.",
    "H2": "FAISS outperforms BM25 on paraphrased/semantic queries where query vocabulary differs from source text.",
    "H3": "Entity-Co-occurrence Graph Retrieval outperforms BM25 and FAISS on entity-relation and multi-hop queries.",
    "H4": "Hybrid BM25 + Entity-Co-occurrence Graph retrieval achieves the highest aggregate MRR across mixed query types, at the cost of higher latency.",
    "H5": "Retrieval quality (MRR) does not translate monotonically into generation faithfulness; retrieval and generation require separate evaluation.",
}


def _readme_hypotheses() -> dict[str, str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"^## Canonical Hypotheses \(H1–H5\)$(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, "README.md is missing the '## Canonical Hypotheses (H1–H5)' section"
    return dict(re.findall(r"^- \*\*(H\d)\*\*: (.+)$", match.group(1), re.M))


def test_readme_defines_all_five_hypotheses_verbatim():
    assert _readme_hypotheses() == CANONICAL


def test_statistical_evaluation_wording_matches_readme():
    spec = importlib.util.spec_from_file_location(
        "statistical_evaluation", ROOT / "scripts" / "statistical_evaluation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    readme = _readme_hypotheses()
    for key, wording in module.CANONICAL_WORDING.items():
        assert wording == readme[key], f"{key} wording in statistical_evaluation.py diverges from README.md"
