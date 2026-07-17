"""
Entity-Co-occurrence Graph Retriever — Retrieval Layer
======================================
Research purpose
    Tests H3: "Entity-Co-occurrence Graph Retrieval will outperform flat retrieval methods on relational
    and multi-hop questions where graph structure exposes evidence paths more
    effectively."

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
import pickle
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

from .base_retriever import BaseRetriever, RetrievalResult

logger = logging.getLogger(__name__)


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
    ) -> None:
        self.entity_model = entity_model
        self.max_hop = max_hop
        self.graph_path = Path(graph_path)
        self.nodes_path = Path(nodes_path)
        self.edges_path = Path(edges_path)
        self._builder = _GraphBuilder(
            relation_window=relation_window,
            min_entity_freq=min_entity_freq,
        )
        self._extractor = _EntityExtractor(entity_model)
        self._graph = None
        self._chunk_meta: dict[str, dict] = {}   # chunk_id → {text, doc_id}

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def build_index(self, chunks: list[dict]) -> None:
        """Build the entity-chunk graph and save artifacts."""
        self._chunk_meta = {c["chunk_id"]: {"text": c["text"], "doc_id": c["doc_id"]} for c in chunks}
        G, nodes_list, edges_list = self._builder.build(chunks)
        self._graph = G
        self._save(nodes_list, edges_list)

    def _save(self, nodes_list: list[dict], edges_list: list[dict]) -> None:
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        with self.graph_path.open("wb") as fh:
            pickle.dump({"graph": self._graph, "chunk_meta": self._chunk_meta}, fh)

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

        logger.info("Entity-co-occurrence graph artifacts saved → %s", self.graph_path)

    def load_index(self) -> None:
        if not self.graph_path.exists():
            raise FileNotFoundError(f"Graph index not found: {self.graph_path}")
        with self.graph_path.open("rb") as fh:
            payload = pickle.load(fh)
        self._graph = payload["graph"]
        self._chunk_meta = payload["chunk_meta"]
        logger.info(
            "Entity-co-occurrence graph index loaded: %d nodes, %d edges",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        if self._graph is None:
            self.load_index()

        query_entities = self._extractor.extract(query)
        seed_nodes = [e for e in query_entities if e in self._graph]

        if not seed_nodes:
            # Fallback: keyword overlap against entity node labels
            query_lower = query.lower()
            seed_nodes = [
                n for n in self._graph.nodes
                if self._graph.nodes[n].get("type") == "entity"
                and re.search(rf"\b{re.escape(n)}\b", query_lower)
            ][:5]

        # BFS from each seed independently so a chunk reachable from several
        # query entities accumulates one hop-decayed contribution per seed.
        chunk_scores: dict[str, float] = {}
        for seed in seed_nodes:
            visited: set[str] = set()
            queue: deque[tuple[str, int]] = deque([(seed, 0)])

            while queue:
                node, hop = queue.popleft()
                if node in visited or hop > self.max_hop:
                    continue
                visited.add(node)

                node_data = self._graph.nodes.get(node, {})
                if node_data.get("type") == "chunk":
                    # Score decays with hop distance
                    score = 1.0 / (hop + 1)
                    chunk_scores[node] = chunk_scores.get(node, 0.0) + score
                elif node_data.get("type") == "entity":
                    for neighbour in self._graph.neighbors(node):
                        if neighbour not in visited:
                            queue.append((neighbour, hop + 1))

        # Rank by score descending
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
