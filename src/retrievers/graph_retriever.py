"""
Graph RAG Retriever — Retrieval Layer
======================================
Entity-aware retrieval using knowledge graph construction from extracted
entities and their co-occurrence patterns. Queries are resolved by finding
matching entities and traversing the graph 2-hop neighbourhood.

Design choice
    spaCy for NER (PERSON, ORG, GPE, MONEY, LAW) + regex patterns for
    domain-specific entities (SCHEME_NAME, AMOUNT, BENEFICIARY). NetworkX
    DiGraph for storage; JSON for persistence and human inspection.
    Query resolution via entity matching + 2-hop neighbourhood traversal.

Alternative approaches
    LLM-based entity extraction would be more accurate but introduces
    non-reproducibility and API costs. Fixed patterns are transparent
    and deterministic.

Expected strengths
    Handles terminology variation (e.g., "PMJAY" vs "Pradhan Mantri Jan
    Arogya Yojana") via co-occurrence patterns. Recovers documents with
    implicit relevance (e.g., query mentions scheme, document mentions
    beneficiary of that scheme).

Expected weaknesses
    Depends on entity extraction quality. Cannot infer relations not
    explicitly mentioned in text. Graph sparsity at dissertation scale.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

import networkx as nx

try:
    import spacy
except ImportError:
    spacy = None

from .base_retriever import BaseRetriever, RetrievalResult

logger = logging.getLogger(__name__)


# Domain-specific entity patterns
_DOMAIN_PATTERNS = {
    "SCHEME_NAME": [
        r"\b(?:PM-KISAN|PMKISAN|PM KISAN)\b",
        r"\b(?:PMJAY|PM-JAY)\b",
        r"\b(?:MGNREGA|MNREGA|NREGA)\b",
        r"\b(?:PMJDY|PM-JDY|Jan Dhan Yojana)\b",
        r"\b(?:PMMY|PM-MY|Mudra Yojana)\b",
        r"\b(?:PMFBY|PM-FBY|Fasal Bima Yojana)\b",
        r"\b(?:Pradhan Mantri|Prime Minister)\s+\w+\s+(?:Yojana|Scheme|Mission|Programme|Abhiyan)\b",
        r"\b\w+\s+(?:Yojana|Scheme|Mission)\b",
    ],
    "AMOUNT": [
        r"Rs\.?\s*[\d,]+(?:\s*(?:lakh|crore|thousand|hundred))?\b",
        r"INR\s*[\d,]+(?:\s*(?:lakh|crore|thousand|hundred))?\b",
        r"₹\s*[\d,]+(?:\s*(?:lakh|crore|thousand|hundred))?\b",
        r"(?:Rs|INR)\s+[\d,]+(?:\s*(?:lakh|crore|thousand|hundred))?",
    ],
    "BENEFICIARY": [
        r"\b(?:farmer|farmers|agricultural worker)\b",
        r"\b(?:women|female|girl|widow)\b",
        r"\b(?:BPL|APL|SC|ST|OBC|EWS)\b",
        r"\b(?:landless|small and marginal|marginal farmer)\b",
        r"\b(?:poor|vulnerable|weaker section|economically weak)\b",
        r"\b(?:minority|tribal|scheduled caste)\b",
    ],
    "ELIGIBILITY": [
        r"(?:eligible|eligibility|criteria|condition|must|should|required)\b[^.]*(?:age|income|land|family|household|member)[^.]*",
        r"(?:age limit|income limit|annual income|land holding)\b[^.]*(?:\d+)",
        r"\b(?:above|below|minimum|maximum|more than|less than)\s+(?:Rs|age|year)[^.]*",
    ],
    "DOCUMENT": [
        r"\b(?:Aadhaar|Aadhar|PAN|Passport|Voter ID|Driving License|Ration Card)\b",
        r"\b(?:bank account|photograph|certificate)\b",
    ],
}


class GraphRAGRetriever(BaseRetriever):
    """
    Entity-aware retriever using a knowledge graph of extracted entities
    and their co-occurrence patterns.

    Parameters
    ----------
    graph_dir : Path | str
        Directory to store graph artifacts.
    chunks_path : Path | str
        Path to chunks_v1.jsonl.
    model_name : str
        spaCy NER model to use.
    """

    name = "graphrag"

    def __init__(
        self,
        graph_dir: Path | str = "indexes/graphrag",
        chunks_path: Path | str = "data/chunks/chunks_v1.jsonl",
        model_name: str = "en_core_web_sm",
    ) -> None:
        if spacy is None:
            raise ImportError("spacy not installed. Run: pip install spacy")

        self.graph_dir = Path(graph_dir)
        self.chunks_path = Path(chunks_path)
        self.model_name = model_name

        self.graph_dir.mkdir(parents=True, exist_ok=True)

        self.nlp: Optional[spacy.Language] = None
        self.graph: Optional[nx.DiGraph] = None
        self.chunk_lookup: dict[str, dict] = {}  # chunk_id -> {text, doc_id}
        self.entity_index: dict[str, list[str]] = {}  # entity_text -> [node_ids]

    def build_index(self, chunks: list[dict]) -> None:
        """
        Build index from chunks (required by BaseRetriever interface).

        Parameters
        ----------
        chunks : list[dict]
            List of chunk dicts.
        """
        # Save chunks to temporary file, then build graph
        temp_chunks_path = self.graph_dir / "_temp_chunks.jsonl"
        with open(temp_chunks_path, "w") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk) + "\n")

        self.build_graph(temp_chunks_path)

        # Clean up temp file
        temp_chunks_path.unlink()

    def build_graph(self, chunks_path: Path | str | None = None) -> None:
        """
        Build knowledge graph from chunks.

        Parameters
        ----------
        chunks_path : Path | str | None
            Path to chunks JSONL. If None, uses self.chunks_path.
        """
        if chunks_path is None:
            chunks_path = self.chunks_path
        chunks_path = Path(chunks_path)

        logger.info(f"Building graph from {chunks_path}...")

        # Load spaCy model
        logger.info(f"Loading spaCy model: {self.model_name}")
        try:
            self.nlp = spacy.load(self.model_name)
        except OSError:
            logger.error(f"Model not found: {self.model_name}")
            logger.error("Run: python -m spacy download en_core_web_sm")
            raise

        # Initialize graph
        self.graph = nx.DiGraph()
        self.chunk_lookup = {}
        self.entity_index = {}
        node_id_counter = 0

        # Process each chunk
        logger.info("Processing chunks...")
        with open(chunks_path) as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                chunk = json.loads(line)
                chunk_id = chunk["chunk_id"]
                text = chunk["text"]
                doc_id = chunk.get("doc_id", "")

                self.chunk_lookup[chunk_id] = {"text": text, "doc_id": doc_id}

                # Extract entities from this chunk
                entities = self._extract_entities(text)
                chunk_entity_ids = set()

                # Add entity nodes and track for co-occurrence edges
                for entity_text, entity_type in entities:
                    entity_key = (entity_text.lower(), entity_type)

                    # Create entity node if not exists
                    if entity_key not in self.entity_index:
                        node_id = f"entity_{node_id_counter}"
                        node_id_counter += 1
                        self.graph.add_node(
                            node_id,
                            text=entity_text,
                            type=entity_type,
                            chunk_ids=[],
                        )
                        self.entity_index[entity_key] = [node_id]
                    else:
                        node_id = self.entity_index[entity_key][0]

                    chunk_entity_ids.add(node_id)

                    # Add MENTIONED_IN edge
                    if not self.graph.has_edge(node_id, chunk_id):
                        self.graph.add_edge(
                            node_id,
                            chunk_id,
                            relation="MENTIONED_IN",
                        )

                    # Update chunk_ids for entity node
                    node_data = self.graph.nodes[node_id]
                    if chunk_id not in node_data["chunk_ids"]:
                        node_data["chunk_ids"].append(chunk_id)

                # Add chunk node (for lookup)
                self.graph.add_node(
                    chunk_id,
                    text=text,
                    type="CHUNK",
                    doc_id=doc_id,
                )

                # Add CO_OCCURS_WITH edges between entities in same chunk
                chunk_entities = list(chunk_entity_ids)
                for i, entity_id_1 in enumerate(chunk_entities):
                    for entity_id_2 in chunk_entities[i + 1 :]:
                        if not self.graph.has_edge(entity_id_1, entity_id_2):
                            self.graph.add_edge(
                                entity_id_1,
                                entity_id_2,
                                relation="CO_OCCURS_WITH",
                                chunk_id=chunk_id,
                            )
                        if not self.graph.has_edge(entity_id_2, entity_id_1):
                            self.graph.add_edge(
                                entity_id_2,
                                entity_id_1,
                                relation="CO_OCCURS_WITH",
                                chunk_id=chunk_id,
                            )

        # Save graph
        logger.info("Saving graph to disk...")
        self._save_graph()

        # Print statistics
        num_entity_nodes = sum(1 for n in self.graph.nodes(data=True) if n[1].get("type") != "CHUNK")
        num_chunk_nodes = len(self.chunk_lookup)
        num_edges = self.graph.number_of_edges()

        logger.info(f"✓ Graph built: {num_entity_nodes} entity nodes, {num_chunk_nodes} chunks, {num_edges} edges")

    def _extract_entities(self, text: str) -> list[tuple[str, str]]:
        """Extract entities from text using spaCy + domain patterns."""
        entities = []

        # spaCy NER
        doc = self.nlp(text)
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE", "MONEY", "DATE", "LAW"):
                entities.append((ent.text, ent.label_))

        # Domain-specific patterns
        for entity_type, patterns in _DOMAIN_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entity_text = match.group(0)
                    # Deduplicate (case-insensitive)
                    if not any(e[0].lower() == entity_text.lower() for e in entities):
                        entities.append((entity_text, entity_type))

        return entities

    def _save_graph(self) -> None:
        """Save graph to JSON."""
        nodes = []
        edges = []

        for node_id, node_data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "text": node_data.get("text", ""),
                "type": node_data.get("type", ""),
                "chunk_ids": node_data.get("chunk_ids", []),
            })

        for source, target, edge_data in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "relation": edge_data.get("relation", ""),
                "chunk_id": edge_data.get("chunk_id", ""),
            })

        graph_data = {"nodes": nodes, "edges": edges}

        graph_path = self.graph_dir / "graph.json"
        with open(graph_path, "w") as f:
            json.dump(graph_data, f, indent=2)

        chunk_lookup_path = self.graph_dir / "chunk_lookup.json"
        with open(chunk_lookup_path, "w") as f:
            json.dump(self.chunk_lookup, f, indent=2)

        logger.info(f"Graph saved to {graph_path}")

    def load_graph(self) -> None:
        """Load graph from JSON."""
        logger.info("Loading graph from disk...")

        # Load spaCy model for query-time entity extraction
        if self.nlp is None:
            logger.info(f"Loading spaCy model: {self.model_name}")
            try:
                self.nlp = spacy.load(self.model_name)
            except OSError:
                logger.error(f"Model not found: {self.model_name}")
                logger.error("Run: python -m spacy download en_core_web_sm")
                raise

        graph_path = self.graph_dir / "graph.json"
        chunk_lookup_path = self.graph_dir / "chunk_lookup.json"

        if not graph_path.exists():
            raise FileNotFoundError(f"Graph file not found: {graph_path}")

        # Load graph
        with open(graph_path) as f:
            graph_data = json.load(f)

        self.graph = nx.DiGraph()
        node_map = {}

        for node in graph_data["nodes"]:
            node_id = node["id"]
            node_map[node_id] = node
            self.graph.add_node(
                node_id,
                text=node.get("text", ""),
                type=node.get("type", ""),
                chunk_ids=node.get("chunk_ids", []),
            )

        for edge in graph_data["edges"]:
            source = edge["source"]
            target = edge["target"]
            self.graph.add_edge(
                source,
                target,
                relation=edge.get("relation", ""),
                chunk_id=edge.get("chunk_id", ""),
            )

        # Load chunk lookup
        with open(chunk_lookup_path) as f:
            self.chunk_lookup = json.load(f)

        # Rebuild entity index for query-time lookups
        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get("type") != "CHUNK":
                entity_text = node_data.get("text", "").lower()
                entity_type = node_data.get("type", "")
                entity_key = (entity_text, entity_type)
                if entity_key not in self.entity_index:
                    self.entity_index[entity_key] = []
                self.entity_index[entity_key].append(node_id)

        logger.info(f"✓ Graph loaded: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        """
        Retrieve chunks using entity-based graph traversal.

        Parameters
        ----------
        query : str
            Query text.
        top_k : int
            Number of results to return.

        Returns
        -------
        list[RetrievalResult]
            Ranked chunks.
        """
        if self.graph is None:
            raise RuntimeError("Graph not loaded. Call load_graph() first.")

        # Step 1: Extract entities from query
        query_entities = self._extract_entities(query)
        logger.debug(f"Query entities: {query_entities}")

        # Step 2: Find seed nodes
        seed_nodes = set()
        for entity_text, entity_type in query_entities:
            entity_key = (entity_text.lower(), entity_type)
            if entity_key in self.entity_index:
                seed_nodes.update(self.entity_index[entity_key])

        # If no seed nodes, fall back to keyword overlap
        if not seed_nodes:
            logger.debug("No entity matches found. Using keyword fallback...")
            return self._retrieve_by_keyword(query, top_k)

        logger.debug(f"Seed nodes: {seed_nodes}")

        # Step 3: 2-hop traversal
        visited_chunks = {}  # chunk_id -> score

        for seed_node in seed_nodes:
            # Direct chunks (seed node mentions them)
            for target in self.graph.successors(seed_node):
                if self.graph.nodes[target].get("type") == "CHUNK":
                    visited_chunks[target] = visited_chunks.get(target, 0) + 1.0

            # 1-hop neighbours
            for neighbor in self.graph.successors(seed_node):
                if self.graph.nodes[neighbor].get("type") != "CHUNK":
                    # Chunks referenced by neighbour
                    for chunk in self.graph.successors(neighbor):
                        if self.graph.nodes[chunk].get("type") == "CHUNK":
                            visited_chunks[chunk] = visited_chunks.get(chunk, 0) + 0.5

        # Step 4: Rank and return
        ranked_chunks = sorted(visited_chunks.items(), key=lambda x: x[1], reverse=True)

        results = []
        for rank, (chunk_id, score) in enumerate(ranked_chunks[:top_k], 1):
            text = self.chunk_lookup.get(chunk_id, {}).get("text", "")
            doc_id = self.chunk_lookup.get(chunk_id, {}).get("doc_id", "")

            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    text=text,
                    score=float(score),
                    rank=rank,
                    latency_ms=0.0,
                    retriever=self.name,
                    extra={"num_seed_matches": len(seed_nodes)},
                )
            )

        return results

    def _retrieve_by_keyword(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Fallback: rank chunks by keyword overlap."""
        query_tokens = set(query.lower().split())

        chunk_scores = {}
        for chunk_id, chunk_data in self.chunk_lookup.items():
            text = chunk_data.get("text", "")
            chunk_tokens = set(text.lower().split())
            overlap = len(query_tokens & chunk_tokens)
            if overlap > 0:
                chunk_scores[chunk_id] = overlap

        ranked_chunks = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for rank, (chunk_id, score) in enumerate(ranked_chunks[:top_k], 1):
            text = self.chunk_lookup.get(chunk_id, {}).get("text", "")
            doc_id = self.chunk_lookup.get(chunk_id, {}).get("doc_id", "")

            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    text=text,
                    score=float(score) / max(len(query_tokens), 1),
                    rank=rank,
                    latency_ms=0.0,
                    retriever=self.name,
                    extra={"fallback": "keyword_overlap"},
                )
            )

        return results

    def write_run_file(
        self,
        queries: list[dict],
        top_k: int,
        output_path: Path | str,
    ) -> None:
        """
        Write TREC-format run file.

        Parameters
        ----------
        queries : list[dict]
            List of {"query_id": ..., "query": ...} or {"question_id": ..., "question": ...} dicts.
        top_k : int
            Number of results per query.
        output_path : Path | str
            Output path for run file (tab-separated).
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Writing run file to {output_path}...")
        with open(output_path, "w") as f:
            f.write("query_id\tQ0\tchunk_id\trank\tscore\tsystem_name\n")

            for query_dict in queries:
                query_id = query_dict.get("query_id", query_dict.get("question_id"))
                query_text = query_dict.get("query", query_dict.get("question"))

                results = self.retrieve(query_text, top_k=top_k)

                for result in results:
                    f.write(
                        f"{query_id}\tQ0\t{result.chunk_id}\t{result.rank}\t{result.score:.6f}\t{self.name}\n"
                    )

        logger.info(f"✓ Run file written to {output_path}")
