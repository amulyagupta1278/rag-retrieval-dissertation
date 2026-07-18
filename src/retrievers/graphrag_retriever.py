"""
Entity-Co-occurrence Graph Retriever — Retrieval Layer
======================================
Research purpose
    Tests H3 — canonical definition in README.md §Canonical Hypotheses (H1–H5).

    The graph is built offline in two stages:
    (1) entity and relation extraction from chunks using spaCy NER +
        co-occurrence windowing;
    (2) a NetworkX graph linking entity nodes to chunk nodes with
        co-occurrence and named-relation edges.

    At query time, entities are extracted from the query, matched to graph
    nodes, and a BFS/DFS traversal collects supporting chunks up to max_hop.

Design choice
    Custom lightweight pipeline over spaCy + NetworkX rather than the
    microsoft/graphrag package. This is entity co-occurrence retrieval, not
    Microsoft's LLM-based GraphRAG: it has no typed relations, communities,
    summaries, or global/local GraphRAG query modes. The custom pipeline is
    auditable, free, and reproducible.

Alternative approaches
    LlamaIndex PropertyGraphIndex; Neo4j for persistent graph storage.
    Both are heavier than needed at mid-semester scale (< 10k chunks).

Expected strengths
    Retrieves evidence along relational paths invisible to flat retrievers;
    graph artifacts are serialised and inspectable (nodes.jsonl, edges.jsonl).

Expected weaknesses
    Entity extraction quality depends on spaCy model; small/domain-specific
    corpora may have sparse graphs that degrade multi-hop retrieval.
    Graph construction is the most expensive offline step.
"""

from __future__ import annotations

import json
import logging
import math
import pickle
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Optional

from .base_retriever import BaseRetriever, RetrievalResult
from ..utils.artifact_provenance import chunk_provenance, package_versions, stable_json_hash, validate_chunk_provenance, validate_config_hash

logger = logging.getLogger(__name__)

_SEED_TOKENS = re.compile(r"[a-z0-9]+")
_GENERIC_SEEDS = {
    "al", "application", "beneficiary", "central", "department", "government",
    "central government", "government of india", "gram", "india", "ministry", "national",
    "programme", "ri", "sc", "scheme", "state government", "st", "state", "yojana",
}
_SCHEMA_SEEDS = {
    "answer", "answer md", "chunk id", "doc id", "children", "list item",
    "implementing agency", "scheme id",
}


# ---------------------------------------------------------------------------
# Graph node / edge schemas
# ---------------------------------------------------------------------------

def _node_dict(node_id: str, label: str, node_type: str, chunk_ids: list[str]) -> dict:
    return {
        "node_id": node_id,
        "label": label,
        "type": node_type,   # "entity" | "chunk"
        "chunk_ids": chunk_ids,
    }


def _edge_dict(src: str, dst: str, relation: str, weight: float, chunk_id: str) -> dict:
    return {
        "src": src,
        "dst": dst,
        "relation": relation,
        "weight": weight,
        "chunk_id": chunk_id,
    }


# ---------------------------------------------------------------------------
# Entity extractor
# ---------------------------------------------------------------------------

class _EntityExtractor:
    """Extracts named entities from text using spaCy."""

    _NER_TYPES = {"PERSON", "ORG", "GPE", "PRODUCT", "WORK_OF_ART", "LAW", "NORP", "FAC"}

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        self.model_name = model_name
        self._nlp = None

    def _load(self) -> None:
        if self._nlp is not None:
            return
        try:
            import spacy

            self._nlp = spacy.load(self.model_name)
        except (ImportError, OSError) as exc:
            logger.warning("spaCy model '%s' not available: %s. Falling back to regex NER.", self.model_name, exc)
            self._nlp = None

    def extract(self, text: str) -> list[str]:
        """Return list of unique entity strings."""
        self._load()
        if self._nlp is not None:
            doc = self._nlp(text[:50_000])  # cap for speed
            # spaCy emits entities in source order. dict.fromkeys removes
            # repeats without destroying the textual co-occurrence order.
            return list(dict.fromkeys(
                ent.text.strip().lower()
                for ent in doc.ents
                if ent.label_ in self._NER_TYPES and len(ent.text.strip()) > 1
            ))
        # Regex fallback: capitalised phrases
        import re

        return list(dict.fromkeys(
            m.group().lower()
            for m in re.finditer(r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*", text)
            if len(m.group()) > 3
        ))


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

class _GraphBuilder:
    """Builds a NetworkX entity-chunk bipartite graph from chunk dicts."""

    def __init__(self, relation_window: int = 2, min_entity_freq: int = 2) -> None:
        self.relation_window = relation_window
        self.min_entity_freq = min_entity_freq
        self._extractor = _EntityExtractor()

    def build(self, chunks: list[dict]) -> tuple[object, list[dict], list[dict]]:
        """
        Returns (graph, nodes_list, edges_list).

        The graph maps node_id → list[chunk_id] (adjacency for retrieval).
        """
        try:
            import networkx as nx
        except ImportError as exc:
            raise ImportError("Install networkx: pip install networkx") from exc

        entity_freq: dict[str, int] = defaultdict(int)
        chunk_entities: dict[str, list[str]] = {}

        # First pass: count entity frequencies
        for chunk in chunks:
            ents = self._extractor.extract(chunk["text"])
            chunk_entities[chunk["chunk_id"]] = ents
            for e in ents:
                entity_freq[e] += 1

        # Filter rare entities
        valid_entities = {e for e, f in entity_freq.items() if f >= self.min_entity_freq}
        logger.info("Valid entities after freq filter: %d", len(valid_entities))

        G = nx.Graph()
        nodes_list: list[dict] = []
        edges_list: list[dict] = []

        # Add chunk nodes
        for chunk in chunks:
            cid = chunk["chunk_id"]
            G.add_node(cid, type="chunk", label=cid, chunk_ids=[cid])

        # Add entity nodes and edges
        for chunk in chunks:
            cid = chunk["chunk_id"]
            ents = [e for e in chunk_entities[cid] if e in valid_entities]
            for ent in ents:
                if ent not in G:
                    G.add_node(ent, type="entity", label=ent, chunk_ids=[])
                    nodes_list.append(_node_dict(ent, ent, "entity", []))
                # Entity → chunk edge (co-occurrence)
                if G.has_edge(ent, cid):
                    G[ent][cid]["weight"] += 1.0
                else:
                    G.add_edge(ent, cid, relation="contains", weight=1.0)
                    edges_list.append(_edge_dict(ent, cid, "contains", 1.0, cid))
                # Track which chunks mention this entity
                G.nodes[ent]["chunk_ids"].append(cid)

            # Co-occurrence between entities within the same chunk
            for i, e1 in enumerate(ents):
                for e2 in ents[i + 1: i + 1 + self.relation_window]:
                    if e1 == e2:
                        continue
                    if G.has_edge(e1, e2):
                        G[e1][e2]["weight"] += 1.0
                    else:
                        G.add_edge(e1, e2, relation="co_occurs", weight=1.0)
                        edges_list.append(_edge_dict(e1, e2, "co_occurs", 1.0, cid))

        # Build chunk nodes list
        for chunk in chunks:
            cid = chunk["chunk_id"]
            nodes_list.append(
                _node_dict(cid, cid[:16], "chunk", [cid])
            )

        logger.info(
            "Graph built: %d nodes, %d edges",
            G.number_of_nodes(),
            G.number_of_edges(),
        )
        return G, nodes_list, edges_list


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class GraphRAGRetriever(BaseRetriever):
    """
    Graph-based retriever using entity co-occurrence graph + BFS traversal.

    Parameters
    ----------
    entity_model : str
        spaCy model name for entity extraction.
    max_hop : int
        Maximum BFS depth from query entities.
    relation_window : int
        Window size for co-occurrence edges during graph construction.
    min_entity_freq : int
        Prune entities appearing fewer times than this.
    graph_path : str | Path
        Where to persist/load the NetworkX graph (pickle).
    nodes_path : str | Path
        Where to persist nodes.jsonl.
    edges_path : str | Path
        Where to persist edges.jsonl.
    """

    name = "graphrag"
    human_name = "Entity-Co-occurrence Graph Retrieval"

    def __init__(
        self,
        entity_model: str = "en_core_web_sm",
        max_hop: int = 2,
        relation_window: int = 2,
        min_entity_freq: int = 2,
        graph_path: str | Path = "indexes/graphrag/graph.gpickle",
        nodes_path: str | Path = "indexes/graphrag/nodes.jsonl",
        edges_path: str | Path = "indexes/graphrag/edges.jsonl",
        chunks_path: str | Path | None = None,
        seed_filtering: bool = False,
        use_aliases: bool = False,
        hub_penalty: bool = False,
        dual_entity_coverage: bool = False,
        lexical_fallback: bool = False,
        max_seeds: int = 5,
        hop_decay: float = 0.5,
    ) -> None:
        self.entity_model = entity_model
        self.max_hop = max_hop
        self.graph_path = Path(graph_path)
        self.nodes_path = Path(nodes_path)
        self.edges_path = Path(edges_path)
        self.chunks_path = Path(chunks_path) if chunks_path else None
        self.seed_filtering = seed_filtering
        self.use_aliases = use_aliases
        self.hub_penalty = hub_penalty
        self.dual_entity_coverage = dual_entity_coverage
        self.lexical_fallback = lexical_fallback
        self.max_seeds = max_seeds
        self.hop_decay = hop_decay
        self._builder = _GraphBuilder(
            relation_window=relation_window,
            min_entity_freq=min_entity_freq,
        )
        self._extractor = _EntityExtractor(entity_model)
        self._graph = None
        self._chunk_meta: dict[str, dict] = {}   # chunk_id → {text, doc_id}
        self.provenance: dict = {}
        self.index_config: dict = {}
        self._aliases: dict[str, list[str]] = {}
        self._document_frequency: Counter = Counter()
        self.last_trace: dict = {}

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def build_index(self, chunks: list[dict]) -> None:
        """Build the entity-chunk graph and save artifacts."""
        self._chunk_meta = {
            c["chunk_id"]: {
                "text": c["text"], "doc_id": c["doc_id"],
                "scheme_name": c.get("scheme_name", ""), "ministry": c.get("ministry", ""),
            }
            for c in chunks
        }
        self.provenance = chunk_provenance(chunks, self.chunks_path)
        G, nodes_list, edges_list = self._builder.build(chunks)
        self._graph = G
        self._refresh_retrieval_metadata()
        self._save(nodes_list, edges_list)

    def _save(self, nodes_list: list[dict], edges_list: list[dict]) -> None:
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        with self.graph_path.open("wb") as fh:
            pickle.dump({
                "graph": self._graph,
                "chunk_meta": self._chunk_meta,
                "provenance": self.provenance,
            }, fh)

        self.nodes_path.parent.mkdir(parents=True, exist_ok=True)
        with self.nodes_path.open("w", encoding="utf-8") as fh:
            for node in nodes_list:
                fh.write(json.dumps(node) + "\n")

        self.edges_path.parent.mkdir(parents=True, exist_ok=True)
        with self.edges_path.open("w", encoding="utf-8") as fh:
            for edge in edges_list:
                fh.write(json.dumps(edge) + "\n")

        # Portable, inspectable companions to the pickle.  They are derived
        # from the same in-memory graph and do not change retrieval behavior.
        graph_json = self.graph_path.with_name("graph.json")
        graph_payload = {
            "nodes": [
                {"node_id": node, **dict(data)}
                for node, data in self._graph.nodes(data=True)
            ],
            "edges": [
                {"src": src, "dst": dst, **dict(data)}
                for src, dst, data in self._graph.edges(data=True)
            ],
        }
        graph_json.write_text(json.dumps(graph_payload, ensure_ascii=False) + "\n", encoding="utf-8")
        chunk_lookup = self.graph_path.with_name("chunk_lookup.json")
        chunk_lookup.write_text(
            json.dumps(self._chunk_meta, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        base_config = {
            "retriever": self.name,
            "human_name": self.human_name,
            "entity_model": self.entity_model,
            "max_hop": self.max_hop,
            "relation_window": self._builder.relation_window,
            "min_entity_freq": self._builder.min_entity_freq,
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "provenance": self.provenance,
            "package_versions": package_versions(("networkx", "spacy")),
        }
        self.index_config = {
            **base_config,
            "configuration_hash": stable_json_hash(base_config),
        }
        self.graph_path.with_name("config.json").write_text(
            json.dumps(self.index_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        logger.info("Entity-co-occurrence graph artifacts saved → %s", self.graph_path)

    def load_index(self) -> None:
        if not self.graph_path.exists():
            raise FileNotFoundError(f"Graph index not found: {self.graph_path}")
        with self.graph_path.open("rb") as fh:
            payload = pickle.load(fh)
        self._graph = payload["graph"]
        self._chunk_meta = payload["chunk_meta"]
        config_path = self.graph_path.with_name("config.json")
        self.index_config = (
            json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        )
        validate_config_hash(self.index_config)
        self.provenance = payload.get("provenance", self.index_config.get("provenance", {}))
        self._refresh_retrieval_metadata()
        logger.info(
            "Entity-co-occurrence graph index loaded: %d nodes, %d edges",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )

    def validate_provenance(self, chunks: list[dict], *, require_complete: bool = False) -> dict:
        """Validate graph parent corpus independently of graph cardinality."""
        validate_config_hash(self.index_config, required=require_complete)
        return validate_chunk_provenance(
            self.provenance, chunks, self.chunks_path,
            require_complete=require_complete,
        )

    @staticmethod
    def _normalise(value: str) -> str:
        return " ".join(_SEED_TOKENS.findall(value.lower()))

    def _valid_seed(self, value: str) -> tuple[bool, str | None]:
        normalised = self._normalise(value)
        if len(normalised) < 3:
            return False, "too_short"
        if normalised in _GENERIC_SEEDS:
            return False, "generic"
        if normalised in _SCHEMA_SEEDS or "_md" in value or "_id" in value:
            return False, "schema_artifact"
        if not re.search(r"[a-z]", normalised):
            return False, "malformed"
        return True, None

    def _refresh_retrieval_metadata(self) -> None:
        """Build deterministic aliases and lexical statistics from clean chunk text."""
        if self._graph is None:
            return
        aliases: dict[str, set[str]] = defaultdict(set)
        entity_nodes = [
            node for node, data in self._graph.nodes(data=True)
            if data.get("type") == "entity"
        ]
        by_normalised = {self._normalise(node): node for node in entity_nodes}
        for node in entity_nodes:
            aliases[self._normalise(node)].add(node)
        expansion_pattern = re.compile(r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){1,10})\s*\(([A-Z][A-Z0-9-]{1,9})\)")
        for meta in self._chunk_meta.values():
            text = meta.get("text", "")
            for expansion, acronym in expansion_pattern.findall(text):
                node = by_normalised.get(self._normalise(expansion))
                if node:
                    aliases[self._normalise(acronym)].add(node)
            scheme = self._normalise(meta.get("scheme_name", ""))
            if scheme and scheme in by_normalised:
                node = by_normalised[scheme]
                aliases[scheme].add(node)
                stripped = re.sub(r"\b(?:scheme|programme|program|mission|yojana)\b", " ", scheme)
                stripped = self._normalise(stripped)
                if len(stripped) >= 4:
                    aliases[stripped].add(node)
        self._aliases = {
            alias: sorted(nodes) for alias, nodes in sorted(aliases.items()) if alias
        }
        self._document_frequency = Counter()
        for meta in self._chunk_meta.values():
            self._document_frequency.update(set(_SEED_TOKENS.findall(meta.get("text", "").lower())))

    def _select_seeds(
        self, query: str, extracted: list[str] | None = None,
    ) -> tuple[list[str], list[dict]]:
        extracted = extracted if extracted is not None else self._extractor.extract(query)
        candidates: list[tuple[str, str]] = []
        for entity in extracted:
            if entity in self._graph:
                candidates.append((entity, "ner"))
        query_normalised = self._normalise(query)
        if self.seed_filtering:
            for node, data in self._graph.nodes(data=True):
                if data.get("type") != "entity":
                    continue
                label = self._normalise(str(data.get("label", node)))
                if label and re.search(rf"(?:^|\s){re.escape(label)}(?:$|\s)", query_normalised):
                    candidates.append((node, "exact_phrase"))
        if self.use_aliases:
            for alias, nodes in self._aliases.items():
                if re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", query_normalised):
                    candidates.extend((node, "verified_alias") for node in nodes)

        decisions: list[dict] = []
        accepted: dict[str, tuple[int, str]] = {}
        source_priority = {"verified_alias": 3, "exact_phrase": 2, "ner": 1}
        for node, source in candidates:
            valid, reason = self._valid_seed(node) if self.seed_filtering else (True, None)
            decision = {
                "node": node, "source": source, "accepted": valid,
                "reason": reason, "degree": self._graph.degree(node) if node in self._graph else None,
            }
            decisions.append(decision)
            if valid:
                candidate = (source_priority[source], source)
                if candidate > accepted.get(node, (-1, "")):
                    accepted[node] = candidate
        ordered = sorted(
            accepted,
            key=lambda node: (-accepted[node][0], -len(self._normalise(node)), self._graph.degree(node), node),
        )
        if self.seed_filtering:
            ordered = ordered[: self.max_seeds]
        selected = set(ordered)
        for decision in decisions:
            if decision["accepted"] and decision["node"] not in selected:
                decision["accepted"] = False
                decision["reason"] = "seed_cap"
        return ordered, decisions

    def _lexical_results(self, query: str, top_k: int) -> dict[str, float]:
        tokens = set(_SEED_TOKENS.findall(query.lower())) - _GENERIC_SEEDS
        total = max(len(self._chunk_meta), 1)
        scores: dict[str, float] = {}
        for chunk_id, meta in self._chunk_meta.items():
            chunk_tokens = set(_SEED_TOKENS.findall(meta.get("text", "").lower()))
            score = sum(
                math.log((total + 1) / (self._document_frequency.get(token, 0) + 1)) + 1.0
                for token in tokens & chunk_tokens
            )
            if score > 0:
                scores[chunk_id] = score / math.sqrt(max(len(chunk_tokens), 1))
        return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k])

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        if self._graph is None:
            self.load_index()

        query_entities = self._extractor.extract(query)
        seed_nodes, seed_decisions = self._select_seeds(query, query_entities)

        if not seed_nodes and not self.seed_filtering:
            # Fallback: keyword overlap against entity node labels
            query_lower = query.lower()
            seed_nodes = [
                n for n in self._graph.nodes
                if self._graph.nodes[n].get("type") == "entity"
                and re.search(rf"\b{re.escape(n)}\b", query_lower)
            ][:5]

        if not seed_nodes and self.lexical_fallback:
            chunk_scores = self._lexical_results(query, top_k)
            self.last_trace = {
                "query": query, "extracted_entities": query_entities,
                "seed_decisions": seed_decisions, "selected_seeds": [],
                "fallback": "lexical", "candidate_chunks": len(chunk_scores),
                "result_scores": chunk_scores,
            }
            return self._results(chunk_scores, top_k, [])

        # BFS from each seed independently so a chunk reachable from several
        # query entities accumulates one hop-decayed contribution per seed.
        chunk_scores: dict[str, float] = {}
        chunk_seed_coverage: dict[str, set[str]] = defaultdict(set)
        for seed in seed_nodes:
            visited: set[str] = set()
            start_score = (
                1.0 / math.log2(self._graph.degree(seed) + 2)
                if self.hub_penalty else 1.0
            )
            queue: deque[tuple[str, int, float]] = deque([(seed, 0, start_score)])

            while queue:
                node, hop, path_score = queue.popleft()
                if node in visited or hop > self.max_hop:
                    continue
                visited.add(node)

                node_data = self._graph.nodes.get(node, {})
                if node_data.get("type") == "chunk":
                    score = path_score if self.hub_penalty else 1.0 / (hop + 1)
                    chunk_scores[node] = chunk_scores.get(node, 0.0) + score
                    chunk_seed_coverage[node].add(seed)
                elif node_data.get("type") == "entity":
                    for neighbour in self._graph.neighbors(node):
                        if neighbour not in visited:
                            next_score = path_score
                            if self.hub_penalty and self._graph.nodes[neighbour].get("type") == "entity":
                                next_score *= self.hop_decay / math.log2(self._graph.degree(neighbour) + 2)
                            queue.append((neighbour, hop + 1, next_score))

        if self.dual_entity_coverage and len(seed_nodes) >= 2:
            for chunk_id, covered in chunk_seed_coverage.items():
                if len(covered) >= 2:
                    chunk_scores[chunk_id] *= 1.0 + 0.25 * (len(covered) - 1)

        trace_scores = dict(sorted(chunk_scores.items(), key=lambda item: (-item[1], item[0]))[:20])
        self.last_trace = {
            "query": query, "extracted_entities": query_entities,
            "seed_decisions": seed_decisions, "selected_seeds": seed_nodes,
            "fallback": None, "candidate_chunks": len(chunk_scores),
            "result_scores": trace_scores,
            "coverage": {
                key: sorted(chunk_seed_coverage[key]) for key in trace_scores
            },
        }
        return self._results(chunk_scores, top_k, seed_nodes)

    def _results(
        self, chunk_scores: dict[str, float], top_k: int, seed_nodes: list[str],
    ) -> list[RetrievalResult]:
        """Convert deterministic chunk scores into common retrieval records."""
        ranked = sorted(chunk_scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]

        results: list[RetrievalResult] = []
        for rank, (chunk_id, score) in enumerate(ranked, start=1):
            meta = self._chunk_meta.get(chunk_id, {})
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    doc_id=meta.get("doc_id", "unknown"),
                    text=meta.get("text", ""),
                    score=score,
                    rank=rank,
                    latency_ms=0.0,
                    retriever=self.name,
                    extra={"seed_entities": seed_nodes},
                )
            )
        return results
