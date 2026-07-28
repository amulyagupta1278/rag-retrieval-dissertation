"""Deterministic typed-metadata graph retrieval, separate from the legacy graph."""

from __future__ import annotations

import json
import math
import pickle
import re
import unicodedata
from collections import Counter, defaultdict, deque
from pathlib import Path

from .base_retriever import BaseRetriever, RetrievalResult
from .graphrag_retriever import _EntityExtractor

_TOKEN = re.compile(r"[a-z0-9]+")
_BENEFICIARIES = re.compile(
    r"\b(?:scheduled castes?|scheduled tribes?|other backward classes?|persons? with disabilities|"
    r"senior citizens?|women|farmers?|students?|workers?|self help groups?|below poverty line families)\b",
    re.I,
)
_LAWS = re.compile(r"\b([A-Z][A-Za-z ]{2,80}(?:Act|Rules|Code|Notification)(?:,?\s*\d{4})?)\b")
_STRUCTURED_KEYS = {
    "nodaldepartmentname": "department", "department": "department",
    "implementingagency": "agency", "implementingagencies": "agency", "agency": "agency",
}
_TYPE_WEIGHTS = {
    "scheme": 1.00, "alias": 1.00, "law": 0.90, "agency": 0.90,
    "beneficiary": 0.90, "ministry": 0.75, "department": 0.75, "entity": 0.60,
}


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).lower()
    return " ".join(_TOKEN.findall(value))


def _node_id(node_type: str, label: str) -> str:
    return f"{node_type}:{_normalise(label)}"


def _acronym(label: str) -> str | None:
    words = [word for word in re.findall(r"[A-Za-z]+", label) if word.lower() not in {"of", "the", "and", "for"}]
    value = "".join(word[0] for word in words).lower()
    return value if 2 <= len(value) <= 10 else None


def _scheme_aliases(label: str) -> set[str]:
    aliases = {_normalise(label)}
    aliases.update(_normalise(value) for value in re.findall(r"\(([A-Z][A-Z0-9-]{1,9})\)", label))
    short = re.sub(r"\b(?:scheme|programme|program|mission|yojana)\b", " ", label, flags=re.I)
    if len(_normalise(short)) >= 4:
        aliases.add(_normalise(short))
    initials = _acronym(label)
    if initials:
        aliases.add(initials)
    return {alias for alias in aliases if len(alias) >= 2}


def _structured_values(path: str, cache: dict[str, dict[str, set[str]]]) -> dict[str, set[str]]:
    if path in cache:
        return cache[path]
    output: dict[str, set[str]] = defaultdict(set)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        cache[path] = output
        return output

    def visit(value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_type = _STRUCTURED_KEYS.get(_normalise(key).replace(" ", ""))
                if key_type:
                    values = child if isinstance(child, list) else [child]
                    for item in values:
                        if isinstance(item, str) and 2 <= len(_normalise(item)) <= 120:
                            output[key_type].add(item.strip())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    cache[path] = output
    return output


class StructuredMetadataGraphRetriever(BaseRetriever):
    """Typed scheme/metadata/entity graph with deterministic weighted traversal."""

    name = "structured_graph"

    def __init__(
        self, index_dir: str | Path = "indexes/structured_graph", *, max_depth: int = 3,
        hop_decay: float = 0.5, min_entity_freq: int = 2, use_aliases: bool = True,
        use_typed_metadata: bool = True, use_weighted_traversal: bool = True,
        use_fallback: bool = True,
    ) -> None:
        self.index_dir = Path(index_dir)
        self.max_depth = max_depth
        self.hop_decay = hop_decay
        self.min_entity_freq = min_entity_freq
        self.use_aliases = use_aliases
        self.use_typed_metadata = use_typed_metadata
        self.use_weighted_traversal = use_weighted_traversal
        self.use_fallback = use_fallback
        self.graph = None
        self.chunk_meta: dict[str, dict] = {}
        self.aliases: dict[str, list[str]] = {}
        self.document_frequency: Counter = Counter()
        self._extractor = _EntityExtractor()

    def build_index(self, chunks: list[dict]) -> None:
        import networkx as nx

        graph = nx.Graph()
        self.chunk_meta = {
            chunk["chunk_id"]: {
                "doc_id": chunk["doc_id"], "text": chunk["text"],
                "scheme_name": chunk.get("scheme_name"), "ministry": chunk.get("ministry"),
            }
            for chunk in chunks
        }
        alias_map: dict[str, set[str]] = defaultdict(set)
        structured_cache: dict[str, dict[str, set[str]]] = {}
        chunk_entities: dict[str, list[str]] = {}
        entity_frequency: Counter = Counter()
        for chunk in chunks:
            entities = self._extractor.extract(chunk["text"])
            chunk_entities[chunk["chunk_id"]] = entities
            entity_frequency.update(set(entities))

        def add_node(node_type: str, label: str) -> str:
            node = _node_id(node_type, label)
            if node not in graph:
                graph.add_node(node, type=node_type, label=label, normalized=_normalise(label))
            alias_map[_normalise(label)].add(node)
            return node

        def add_edge(left: str, right: str, relation: str, weight: float = 1.0) -> None:
            if graph.has_edge(left, right):
                graph[left][right]["weight"] += weight
            else:
                graph.add_edge(left, right, relation=relation, weight=weight)

        for chunk in chunks:
            chunk_id, doc_id = chunk["chunk_id"], chunk["doc_id"]
            chunk_node = f"chunk:{chunk_id}"
            doc_node = f"document:{doc_id}"
            graph.add_node(chunk_node, type="chunk", label=chunk_id, chunk_id=chunk_id)
            graph.add_node(doc_node, type="document", label=doc_id, doc_id=doc_id)
            add_edge(chunk_node, doc_node, "chunk-of-document")
            scheme = str(chunk.get("scheme_name") or "").strip()
            ministry = str(chunk.get("ministry") or "").strip()
            if scheme:
                scheme_node = add_node("scheme", scheme)
                add_edge(doc_node, scheme_node, "describes-scheme")
                if self.use_aliases:
                    for alias in _scheme_aliases(scheme):
                        alias_map[alias].add(scheme_node)
            else:
                scheme_node = None
            if self.use_typed_metadata and ministry and scheme_node:
                ministry_node = add_node("ministry", ministry)
                add_edge(scheme_node, ministry_node, "administered-by")
            if self.use_typed_metadata:
                structured = _structured_values(str(chunk.get("source_path") or ""), structured_cache)
                for value_type in ("department", "agency"):
                    for value in sorted(structured.get(value_type, set()), key=_normalise):
                        target = add_node(value_type, value)
                        add_edge(scheme_node or doc_node, target, "managed-by" if value_type == "department" else "implemented-by")
                for value in sorted(set(_BENEFICIARIES.findall(chunk["text"])), key=_normalise):
                    target = add_node("beneficiary", value)
                    add_edge(scheme_node or chunk_node, target, "targets")
                    add_edge(chunk_node, target, "mentions")
                for value in sorted(set(_LAWS.findall(chunk["text"])), key=_normalise):
                    target = add_node("law", value)
                    add_edge(scheme_node or chunk_node, target, "references-law")
                    add_edge(chunk_node, target, "mentions")
            valid_entities = [
                entity for entity in chunk_entities[chunk_id]
                if entity_frequency[entity] >= self.min_entity_freq
            ]
            entity_nodes = []
            for entity in valid_entities:
                target = add_node("entity", entity)
                add_edge(chunk_node, target, "mentions")
                entity_nodes.append(target)
            for left, right in zip(entity_nodes, entity_nodes[1:]):
                if left != right:
                    add_edge(left, right, "co-occurs")

        self.graph = graph
        self.aliases = {
            alias: sorted(nodes) for alias, nodes in sorted(alias_map.items())
            if alias and len(alias) >= 2
        }
        self.document_frequency = Counter()
        for meta in self.chunk_meta.values():
            self.document_frequency.update(set(_TOKEN.findall(meta["text"].lower())))
        self._save()

    def _save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "graph": self.graph, "chunk_meta": self.chunk_meta, "aliases": self.aliases,
            "document_frequency": self.document_frequency,
        }
        with (self.index_dir / "graph.gpickle").open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        nodes = [
            {"node_id": node, **dict(data)} for node, data in self.graph.nodes(data=True)
        ]
        edges = [
            {"src": left, "dst": right, **dict(data)}
            for left, right, data in self.graph.edges(data=True)
        ]
        for name, records in (("nodes.jsonl", nodes), ("edges.jsonl", edges)):
            with (self.index_dir / name).open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        (self.index_dir / "aliases.json").write_text(
            json.dumps(self.aliases, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.index_dir / "chunk_lookup.json").write_text(
            json.dumps(self.chunk_meta, sort_keys=True) + "\n", encoding="utf-8"
        )
        config = {
            "retriever": self.name, "human_name": "Structured Metadata Graph Retrieval",
            "max_depth": self.max_depth, "hop_decay": self.hop_decay,
            "min_entity_freq": self.min_entity_freq, "use_aliases": self.use_aliases,
            "use_typed_metadata": self.use_typed_metadata,
            "use_weighted_traversal": self.use_weighted_traversal,
            "use_fallback": self.use_fallback, "chunks": len(self.chunk_meta),
            "nodes": self.graph.number_of_nodes(), "edges": self.graph.number_of_edges(),
        }
        (self.index_dir / "config.json").write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def load_index(self) -> None:
        with (self.index_dir / "graph.gpickle").open("rb") as handle:
            payload = pickle.load(handle)
        self.graph = payload["graph"]
        self.chunk_meta = payload["chunk_meta"]
        self.aliases = payload["aliases"]
        self.document_frequency = Counter(payload.get("document_frequency", {}))
        config = json.loads((self.index_dir / "config.json").read_text(encoding="utf-8"))
        for key in ("max_depth", "hop_decay", "min_entity_freq", "use_aliases", "use_typed_metadata", "use_weighted_traversal", "use_fallback"):
            setattr(self, key, config[key])
        if config.get("chunks") != len(self.chunk_meta):
            raise RuntimeError("Structured graph config cardinality mismatch")

    def _seed_nodes(self, query: str) -> list[tuple[str, float]]:
        normalized = _normalise(query)
        candidates: dict[str, float] = {}
        for alias, nodes in self.aliases.items():
            if re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", normalized):
                for node in nodes:
                    node_type = self.graph.nodes[node].get("type", "entity")
                    candidates[node] = max(candidates.get(node, 0.0), _TYPE_WEIGHTS.get(node_type, 0.60))
        return sorted(candidates.items(), key=lambda item: (-item[1], item[0]))

    def _lexical_fallback(self, query: str, top_k: int) -> list[tuple[str, float]]:
        query_tokens = set(_TOKEN.findall(query.lower()))
        total = max(len(self.chunk_meta), 1)
        scores = []
        for chunk_id, meta in self.chunk_meta.items():
            chunk_tokens = set(_TOKEN.findall(meta["text"].lower()))
            score = sum(
                math.log((total + 1) / (self.document_frequency.get(token, 0) + 1)) + 1
                for token in query_tokens & chunk_tokens
            )
            if score > 0:
                scores.append((chunk_id, score / math.sqrt(max(len(chunk_tokens), 1))))
        return sorted(scores, key=lambda item: (-item[1], item[0]))[:top_k]

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        if self.graph is None:
            self.load_index()
        seeds = self._seed_nodes(query)
        chunk_scores: defaultdict[str, float] = defaultdict(float)
        if seeds:
            for seed, base_weight in seeds:
                queue = deque([(seed, 0, base_weight)])
                best: dict[str, float] = {}
                while queue:
                    node, depth, score = queue.popleft()
                    if depth > self.max_depth or score <= best.get(node, -1.0):
                        continue
                    best[node] = score
                    data = self.graph.nodes[node]
                    if data.get("type") == "chunk":
                        chunk_scores[data["chunk_id"]] += score
                    if depth == self.max_depth:
                        continue
                    for neighbour in sorted(self.graph.neighbors(node)):
                        edge = self.graph.edges[node, neighbour]
                        next_score = score * self.hop_decay
                        if self.use_weighted_traversal:
                            degree_penalty = 1.0 / math.log2(self.graph.degree(neighbour) + 2)
                            next_score *= min(float(edge.get("weight", 1.0)), 3.0) * degree_penalty
                        queue.append((neighbour, depth + 1, next_score))
            ranked = sorted(chunk_scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        elif self.use_fallback:
            ranked = self._lexical_fallback(query, top_k)
        else:
            ranked = []
        return [
            RetrievalResult(
                chunk_id=chunk_id, doc_id=self.chunk_meta[chunk_id]["doc_id"],
                text=self.chunk_meta[chunk_id]["text"], score=float(score), rank=rank,
                latency_ms=0.0, retriever=self.name,
                extra={"seed_nodes": [node for node, _ in seeds], "lexical_fallback": not seeds},
            )
            for rank, (chunk_id, score) in enumerate(ranked, 1)
        ]
