#!/usr/bin/env python3
"""Generate evidence-aligned Chapter 4 architecture figures as editable SVG."""

from __future__ import annotations

from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission/figures/chapter4"
W, H = 1400, 850


class SVG:
    def __init__(self, title: str, description: str) -> None:
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
            f"<title id=\"title\">{escape(title)}</title>",
            f"<desc id=\"desc\">{escape(description)}</desc>",
            """<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#476172"/></marker>
  <marker id="arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#2F6B9A"/></marker>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#17324D" flood-opacity="0.12"/></filter>
  <style>
    text { font-family: Arial, Helvetica, sans-serif; fill: #17324D; }
    .title { font-size: 27px; font-weight: 700; }
    .subtitle { font-size: 15px; fill: #587083; }
    .stage { font-size: 14px; font-weight: 700; letter-spacing: 1.4px; fill: #2F6B9A; }
    .box-title { font-size: 18px; font-weight: 700; }
    .body { font-size: 15px; }
    .small { font-size: 13px; fill: #587083; }
    .tiny { font-size: 12px; fill: #587083; }
    .metric { font-size: 16px; font-weight: 700; fill: #2A706B; }
    .mono { font-family: Menlo, Consolas, monospace; font-size: 13px; }
  </style>
</defs>""",
            '<rect width="1400" height="850" fill="#FFFFFF"/>',
        ]

    def add(self, value: str) -> None:
        self.parts.append(value)

    def header(self, title: str, subtitle: str) -> None:
        self.add(f'<text x="60" y="52" class="title">{escape(title)}</text>')
        self.add(f'<text x="60" y="78" class="subtitle">{escape(subtitle)}</text>')
        self.add('<line x1="60" y1="96" x2="1340" y2="96" stroke="#D6E0E7" stroke-width="2"/>')

    def text(self, x: float, y: float, lines: list[str] | str, *, cls: str = "body", anchor: str = "middle", gap: int = 21) -> None:
        if isinstance(lines, str):
            lines = [lines]
        spans = []
        for i, line in enumerate(lines):
            dy = 0 if i == 0 else gap
            spans.append(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
        self.add(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">' + "".join(spans) + "</text>")

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: list[str] | None = None, *, fill: str = "#F4F7FA", stroke: str = "#AFC0CC", accent: str | None = None, radius: int = 12, shadow: bool = False) -> None:
        fx = ' filter="url(#shadow)"' if shadow else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{fx}/>')
        if accent:
            self.add(f'<rect x="{x}" y="{y}" width="7" height="{h}" rx="3" fill="{accent}"/>')
        self.text(x + w / 2, y + 31, title, cls="box-title")
        if lines:
            first = y + 57
            self.text(x + w / 2, first, lines, cls="small", gap=19)

    def lane(self, x: float, y: float, w: float, h: float, label: str, *, fill: str = "#FBFCFD") -> None:
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{fill}" stroke="#D6E0E7" stroke-width="1.5"/>')
        self.add(f'<rect x="{x}" y="{y}" width="44" height="{h}" rx="16" fill="#E8F0F6"/>')
        self.add(f'<text x="{x+27}" y="{y+h/2}" class="stage" text-anchor="middle" transform="rotate(-90 {x+27} {y+h/2})">{escape(label)}</text>')

    def arrow(self, x1: float, y1: float, x2: float, y2: float, *, label: str | None = None, color: str = "#476172", dashed: bool = False, bend: float | None = None) -> None:
        dash = ' stroke-dasharray="7 6"' if dashed else ""
        marker = "arrow-blue" if color == "#2F6B9A" else "arrow"
        if bend is None:
            path = f"M {x1} {y1} L {x2} {y2}"
        else:
            path = f"M {x1} {y1} C {x1+bend} {y1}, {x2-bend} {y2}, {x2} {y2}"
        self.add(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" marker-end="url(#{marker})"{dash}/>')
        if label:
            self.text((x1+x2)/2, (y1+y2)/2-8, label, cls="tiny")

    def pill(self, x: float, y: float, w: float, text: str, *, fill: str = "#E7F2F1", color: str = "#2A706B") -> None:
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="30" rx="15" fill="{fill}"/>')
        self.add(f'<text x="{x+w/2}" y="{y+20}" text-anchor="middle" style="font: 700 13px Arial; fill:{color}">{escape(text)}</text>')

    def note(self, x: float, y: float, w: float, lines: list[str], *, color: str = "#D99B2B") -> None:
        h = 27 + 18 * len(lines)
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="#FFF9E8" stroke="{color}" stroke-width="1.2"/>')
        self.add(f'<circle cx="{x+18}" cy="{y+20}" r="6" fill="{color}"/>')
        self.text(x+34, y+21, lines, cls="tiny", anchor="start", gap=18)

    def save(self, filename: str) -> None:
        self.parts.append("</svg>")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / filename).write_text("\n".join(self.parts) + "\n", encoding="utf-8")


def figure_41() -> None:
    s = SVG("End-to-end retrieval evaluation platform", "Layered architecture from policy documents through retrieval, controlled evaluation, and H5 generation analysis.")
    s.header("End-to-end retrieval evaluation platform", "Implemented R4 architecture; solid arrows are data flow, dashed arrows are control or external-service flow")
    s.lane(55, 120, 1290, 125, "INGESTION")
    s.box(125, 143, 180, 76, "Policy corpus", ["130 documents", "public policy domain"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(365, 143, 190, 76, "Normalise", ["clean text + metadata", "section detection"])
    s.box(615, 143, 210, 76, "Section-aware chunker", ["450 words · 60 overlap"])
    s.box(885, 143, 210, 76, "Chunk manifest", ["954 stable chunk IDs", "content provenance"], fill="#EDF6F4", accent="#2A8C82")
    s.box(1155, 143, 130, 76, "Qrels", ["reviewed", "judgments"], fill="#FFF7E5", accent="#D99B2B")
    for a,b in [((305,181),(365,181)),((555,181),(615,181)),((825,181),(885,181))]: s.arrow(*a,*b)

    s.lane(55, 265, 1290, 165, "RETRIEVAL")
    specs = [
        (120,"BM25",["rank-bm25","k1 1.2 · b 0.75"],"#EAF2F8","#2F6B9A"),
        (345,"FAISS cosine",["MiniLM · 384 dim","normalised IndexFlatIP"],"#EEF0FA","#5966A8"),
        (570,"Entity Graph v4",["spaCy + NetworkX","2-hop + lexical fallback"],"#EDF6F4","#2A8C82"),
        (795,"Weighted hybrid",["RRF k=10","weights 1/.25/.10"],"#FFF7E5","#D99B2B"),
        (1020,"Prompt-RAG",["BM25 25 ∪ FAISS 25","Claude scores 0–3"],"#F6EEF8","#8B5E9C"),
    ]
    for x,t,ls,f,a in specs: s.box(x, 305, 195, 92, t, ls, fill=f, accent=a, shadow=True)
    for x in [217,442,667]: s.arrow(990,245,x,305,color="#2F6B9A",dashed=True,bend=-100)

    s.lane(55, 450, 1290, 175, "EVALUATION")
    s.box(120, 486, 215, 106, "Frozen query tiers", ["60 development", "40 locked test", "12-query holdout"], fill="#F4F7FA", accent="#2F6B9A")
    s.box(405, 492, 215, 94, "Experiment runner", ["query × retriever", "top-50 ranked outputs"])
    s.box(690, 492, 215, 94, "Metric engine", ["MRR · nDCG · Recall", "Precision · Hit rate"], fill="#EDF6F4", accent="#2A8C82")
    s.box(975, 492, 215, 94, "Statistical analysis", ["paired bootstrap", "whole-query resampling"], fill="#FFF7E5", accent="#D99B2B")
    for x1,x2 in [(335,405),(620,690),(905,975)]: s.arrow(x1,539,x2,539)
    s.arrow(1115,430,1115,492,color="#2F6B9A")
    s.arrow(230,430,512,492,color="#2F6B9A",bend=50)

    s.lane(55, 645, 1290, 145, "GENERATION / H5")
    s.box(120, 680, 210, 78, "Top-3 evidence", ["five retrieval systems"])
    s.box(390, 680, 210, 78, "Answer generation", ["fixed prompt · temp 0"])
    s.box(660, 680, 210, 78, "Blinded review", ["claim-level support"])
    s.box(930, 680, 300, 78, "H5 analysis", ["150 answers · 301 claims"], fill="#EDF6F4", accent="#2A8C82")
    for x1,x2 in [(330,390),(600,660),(870,930)]: s.arrow(x1,719,x2,719)
    s.save("figure-4-1-end-to-end-architecture.svg")


def figure_42() -> None:
    s = SVG("Document ingestion and section-aware chunking", "Pipeline from source documents to 954 content-addressed chunks using 450-word windows and 60-word overlap.")
    s.header("Document ingestion and section-aware chunking", "Single frozen chunk manifest feeds every retriever, preventing corpus drift between systems")
    s.text(135, 132, "SOURCE", cls="stage")
    s.text(480, 132, "NORMALISE", cls="stage")
    s.text(840, 132, "SEGMENT", cls="stage")
    s.text(1215, 132, "FREEZE", cls="stage")
    s.box(60, 165, 210, 145, "130 policy documents", ["PDF / HTML extracts", "title · ministry · source", "cleaned_text"], fill="#EAF2F8", accent="#2F6B9A", shadow=True)
    s.box(345, 165, 270, 145, "Text + metadata processing", ["whitespace normalisation", "document metadata retained", "heading candidates detected"], shadow=True)
    s.box(690, 165, 300, 145, "Section-aware windowing", ["target: 450 words", "overlap: 60 words", "title + active heading prepended"], fill="#EDF6F4", accent="#2A8C82", shadow=True)
    s.box(1065, 165, 270, 145, "Frozen chunk manifest", ["chunks_section_aware_450w.jsonl", "954 stable r4chunk_* IDs", "ordered manifest + SHA-256"], fill="#FFF7E5", accent="#D99B2B", shadow=True)
    for x1,x2 in [(270,345),(615,690),(990,1065)]: s.arrow(x1,238,x2,238,color="#2F6B9A")

    s.add('<rect x="90" y="390" width="1220" height="260" rx="18" fill="#FBFCFD" stroke="#D6E0E7" stroke-width="1.5"/>')
    s.text(120, 425, "OVERLAPPING WINDOW CONSTRUCTION", cls="stage", anchor="start")
    s.text(125, 470, ["Document title", "Section A heading", "body words …"], cls="small", anchor="start")
    s.add('<line x1="330" y1="485" x2="1240" y2="485" stroke="#AFC0CC" stroke-width="8" stroke-linecap="round"/>')
    s.add('<rect x="350" y="450" width="560" height="72" rx="10" fill="#DCEAF4" stroke="#2F6B9A" stroke-width="1.5"/>')
    s.text(630, 481, ["Chunk n · words 1–450", "title + current section retained"], cls="body")
    s.add('<rect x="835" y="535" width="405" height="72" rx="10" fill="#DDEFEA" stroke="#2A8C82" stroke-width="1.5"/>')
    s.text(1037, 566, ["Chunk n+1 · starts at word 391", "60-word overlap"], cls="body")
    s.add('<rect x="835" y="450" width="75" height="157" fill="#D99B2B" opacity="0.22"/>')
    s.text(873, 630, "shared evidence boundary", cls="tiny")
    s.arrow(873,617,873,598,color="#2F6B9A")
    s.note(85, 700, 380, ["Same ordered 954-chunk manifest is hashed", "and reused by BM25, FAISS, and Graph v4."])
    s.pill(545, 706, 220, "7.3 chunks / document")
    s.pill(800, 706, 190, "no exact duplicates")
    s.pill(1025, 706, 260, "provenance validated at load")
    s.save("figure-4-2-ingestion-and-chunking.svg")


def figure_43() -> None:
    s = SVG("Entity Graph v4 construction and retrieval", "Offline graph construction and online two-hop query traversal with seed filtering, hub penalty, dual-entity coverage, and lexical fallback.")
    s.header("Entity Graph v4: construction and query-time retrieval", "Custom spaCy + NetworkX entity–chunk graph; not Microsoft GraphRAG")
    s.add('<rect x="55" y="125" width="635" height="655" rx="18" fill="#F7FAFC" stroke="#BFCED8" stroke-width="1.5"/>')
    s.add('<rect x="710" y="125" width="635" height="655" rx="18" fill="#F7FAFC" stroke="#BFCED8" stroke-width="1.5"/>')
    s.text(85, 160, "OFFLINE INDEX CONSTRUCTION", cls="stage", anchor="start")
    s.text(740, 160, "ONLINE QUERY RETRIEVAL", cls="stage", anchor="start")
    s.box(90, 195, 220, 90, "954 chunks", ["text + metadata", "stable chunk IDs"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(405, 195, 220, 90, "Entity extraction", ["spaCy NER", "regex fallback if unavailable"], fill="#EDF6F4", accent="#2A8C82")
    s.arrow(310,240,405,240)
    s.box(90, 345, 220, 95, "Frequency filter", ["min_entity_freq = 2", "co-occurrence window = 2"])
    s.box(405, 345, 220, 95, "Entity–chunk graph", ["contains + co_occurs edges", "undirected NetworkX graph"], fill="#EDF6F4", accent="#2A8C82")
    s.arrow(515,285,515,345)
    s.arrow(310,392,405,392)
    s.box(215, 510, 300, 100, "Frozen graph artefacts", ["3,781 nodes · 26,430 edges", "graph.gpickle · nodes/edges JSONL"], fill="#FFF7E5", accent="#D99B2B", shadow=True)
    s.arrow(515,440,365,510,bend=-60)
    # miniature bipartite graph
    for x,y,label,color in [(125,680,"entity A","#2A8C82"),(260,650,"chunk 1","#2F6B9A"),(260,720,"chunk 2","#2F6B9A"),(395,680,"entity B","#2A8C82"),(530,650,"chunk 3","#2F6B9A")]:
        s.add(f'<circle cx="{x}" cy="{y}" r="28" fill="#FFFFFF" stroke="{color}" stroke-width="3"/>')
        s.text(x,y+4,label,cls="tiny")
    for x1,y1,x2,y2 in [(153,680,232,650),(153,680,232,720),(288,650,367,680),(423,680,502,650)]: s.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#8AA0AF" stroke-width="2"/>')

    s.box(745, 195, 215, 90, "Query text", ["same entity extractor", "normalised seed labels"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(1055, 195, 245, 90, "Seed controls", ["aliases · generic-seed filter", "max 5 query seeds"], fill="#EDF6F4", accent="#2A8C82")
    s.arrow(960,240,1055,240)
    s.add('<polygon points="1040,345 1175,410 1040,475 905,410" fill="#FFF7E5" stroke="#D99B2B" stroke-width="1.7"/>')
    s.text(1040,402,["valid graph","seed found?"],cls="box-title")
    s.arrow(1175,410,1285,410,label="no")
    s.box(1180, 495, 130, 82, "BM25 fallback", ["lexical results"], fill="#FCEEEE", accent="#B85C5C")
    s.arrow(1285,410,1245,495,bend=-35)
    s.arrow(1040,475,1040,535,label="yes")
    s.box(810, 535, 460, 105, "Two-hop traversal + scoring", ["hop decay 0.5 · hub penalty", "dual-entity coverage · matched-entity evidence"], fill="#EDF6F4", accent="#2A8C82", shadow=True)
    s.box(865, 690, 350, 65, "Ranked top-50 chunks", ["trace logs seeds, hops, fallback"], fill="#EAF2F8", accent="#2F6B9A")
    s.arrow(1040,640,1040,690)
    s.arrow(1245,577,1215,722,bend=-40,dashed=True)
    s.save("figure-4-3-entity-graph-v4.svg")


def figure_44() -> None:
    s = SVG("Hybrid fusion and Prompt-RAG reranking", "Parallel comparison of development-selected weighted rank fusion and Claude relevance reranking over a BM25–FAISS candidate union.")
    s.header("Hybrid fusion and Prompt-RAG reranking", "Two distinct second-stage methods: rank fusion versus model-based relevance judgment")
    s.add('<rect x="55" y="125" width="1290" height="300" rx="18" fill="#F8FBFD" stroke="#BFCED8" stroke-width="1.5"/>')
    s.text(85, 160, "A · WEIGHTED HYBRID RRF", cls="stage", anchor="start")
    s.box(95, 205, 190, 83, "BM25 top-50", ["weight 1.00"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(95, 310, 190, 83, "FAISS top-50", ["weight 0.25"], fill="#EEF0FA", accent="#5966A8")
    s.box(360, 205, 190, 83, "Graph v4 top-50", ["weight 0.10"], fill="#EDF6F4", accent="#2A8C82")
    s.box(640, 220, 290, 145, "Weighted reciprocal-rank fusion", ["score(c) = Σ wᵢ/(10 + rankᵢ)", "graph-only factor = 0.0", "score desc → chunk ID tie-break"], fill="#FFF7E5", accent="#D99B2B", shadow=True)
    for x1,y1 in [(285,246),(285,351),(550,246)]: s.arrow(x1,y1,640,292,bend=60)
    s.box(1030, 240, 245, 105, "Hybrid ranked output", ["top-50 audit trace", "development-selected weights", "locked before test/holdout"], fill="#EAF2F8", accent="#2F6B9A")
    s.arrow(930,292,1030,292,color="#2F6B9A")
    s.pill(1040, 370, 225, "local · deterministic · no API")

    s.add('<rect x="55" y="450" width="1290" height="335" rx="18" fill="#FCFAFD" stroke="#CDBFD3" stroke-width="1.5"/>')
    s.text(85, 485, "B · PROMPT-RAG RELEVANCE RERANKER", cls="stage", anchor="start")
    s.box(90, 530, 180, 75, "BM25 top-25", ["lexical pool"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(90, 650, 180, 75, "FAISS top-25", ["semantic pool"], fill="#EEF0FA", accent="#5966A8")
    s.box(345, 565, 220, 125, "Deduplicated union", ["≤50 candidates", "candidate recall@25 = 0.880", "stable candidate IDs"], fill="#FFF7E5", accent="#D99B2B")
    s.arrow(270,568,345,600)
    s.arrow(270,687,345,650)
    s.box(645, 545, 250, 165, "Claude Haiku 4.5", ["temperature 0", "score every candidate 0–3", "JSON schema contract", "max output 1,024 tokens"], fill="#F6EEF8", accent="#8B5E9C", shadow=True)
    s.arrow(565,627,645,627,color="#2F6B9A")
    s.box(975, 555, 285, 145, "Validate and rerank", ["all candidate IDs required", "integer score range enforced", "score desc → chunk ID tie-break", "malformed response = failure"], fill="#EDF6F4", accent="#2A8C82")
    s.arrow(895,627,975,627)
    s.note(985, 720, 265, ["zero retries", "observed: $2.430722 / 100 queries"])
    s.save("figure-4-4-fusion-and-reranking.svg")


def figure_45() -> None:
    s = SVG("Evaluation harness and experiment controls", "Frozen development, locked-test, and holdout paths through retrieval, metrics, paired bootstrap, and immutable run artefacts.")
    s.header("Evaluation harness and experiment controls", "Configuration selection remains separated from locked-test and canonical holdout inference")
    s.box(65, 140, 260, 130, "Benchmark inputs", ["100 reviewed questions", "60 development · 40 locked", "140-row qrel crosswalk", "954-chunk manifest"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(65, 330, 260, 120, "Independent holdout", ["12 post-freeze questions", "21 reviewed judgments", "two per category"], fill="#EDF6F4", accent="#2A8C82")
    s.box(65, 510, 260, 105, "Frozen system configs", ["hash-checked artefacts", "one corpus provenance chain"], fill="#FFF7E5", accent="#D99B2B")
    s.add('<polygon points="470,145 590,205 470,265 350,205" fill="#FFF7E5" stroke="#D99B2B" stroke-width="1.7"/>')
    s.text(470,198,["development-only","selection"],cls="box-title")
    s.box(385, 310, 170, 88, "Freeze gate", ["configs + query sets", "SHA-256 recorded"], fill="#FFF7E5", accent="#D99B2B")
    s.box(385, 470, 170, 88, "Zero-retry gate", ["one attempt/query", "failures preserved"], fill="#FCEEEE", accent="#B85C5C")
    s.arrow(325,205,350,205)
    s.arrow(470,265,470,310)
    s.arrow(325,390,385,354)
    s.arrow(325,562,385,514)

    s.box(650, 220, 250, 200, "Query × system runner", ["BM25", "FAISS cosine", "Entity Graph v4", "Weighted Hybrid", "Prompt-RAG*"], fill="#F4F7FA", accent="#2F6B9A", shadow=True)
    s.arrow(555,354,650,320,color="#2F6B9A")
    s.arrow(555,514,650,350,color="#2F6B9A",bend=45)
    s.box(980, 150, 285, 135, "Per-query metrics", ["MRR@10 · nDCG@10", "Recall@10 · Precision@k", "Hit@10 · category breakdown"], fill="#EDF6F4", accent="#2A8C82")
    s.box(980, 345, 285, 145, "Statistical inference", ["10,000 paired bootstrap samples", "whole-query resampling · seed 42", "confidence intervals + Holm control"], fill="#FFF7E5", accent="#D99B2B")
    s.box(980, 550, 285, 115, "Immutable run artefacts", ["rankings · traces · metrics", "config snapshots · hashes", "failure ledgers"], fill="#EAF2F8", accent="#2F6B9A")
    s.arrow(900,285,980,218)
    s.arrow(900,320,980,417)
    s.arrow(1122,285,1122,345)
    s.arrow(1122,490,1122,550)
    s.note(640, 500, 275, ["* Prompt-RAG: full R4 locked-test result retained.", "Holdout excluded after zero-retry dispatch violation."])
    s.pill(385, 680, 225, "40-query locked test: once")
    s.pill(635, 680, 260, "12-query holdout: canonical")
    s.pill(920, 680, 300, "all paired holdout CIs cross zero")
    s.text(700, 770, "Development informs configuration · locked test estimates benchmark performance · holdout determines hypothesis verdicts", cls="small")
    s.save("figure-4-5-evaluation-harness.svg")


def figure_46() -> None:
    s = SVG("Generation and H5 faithfulness evaluation", "Five retrieval systems supply top-three evidence for 150 generated answers, blinded claim review, adjudication, and gated H5 bootstrap analysis.")
    s.header("Generation layer and H5 faithfulness evaluation", "Claim-level grounding study; abstention recorded separately from unfaithfulness")
    s.box(55, 160, 205, 125, "Retrieval panel", ["30 questions × 5 systems", "top-10 rankings retained", "top-3 chunks supplied"], fill="#EAF2F8", accent="#2F6B9A", shadow=True)
    s.box(325, 160, 220, 125, "Prompt assembler", ["question + evidence E01–E03", "answer only from evidence", "explicit abstention allowed"], fill="#FFF7E5", accent="#D99B2B")
    s.box(610, 160, 220, 125, "Claude generation", ["Haiku 4.5 · temperature 0", "fixed decoding per stratum", "zero retries"], fill="#F6EEF8", accent="#8B5E9C")
    s.box(850, 145, 220, 155, "150 frozen outputs", ["100 V3 records", "50 legacy-contract records", "prompt strata disclosed", "answer + evidence IDs"], fill="#EDF6F4", accent="#2A8C82", shadow=True)
    for x1,x2 in [(260,325),(545,610),(830,850)]: s.arrow(x1,222,x2,222,color="#2F6B9A")
    s.add('<polygon points="1210,160 1325,222 1210,284 1095,222" fill="#FFF7E5" stroke="#D99B2B" stroke-width="1.7"/>')
    s.text(1210,215,["verifiable","claim?"],cls="box-title")
    s.arrow(1070,222,1095,222)

    s.box(1065, 365, 260, 90, "69 abstentions", ["no verifiable claim", "excluded from faithfulness score"], fill="#F4F7FA", accent="#7A8994")
    s.arrow(1210,284,1195,365)
    s.box(790, 365, 215, 90, "81 claim-bearing answers", ["301 verifiable claims"], fill="#EDF6F4", accent="#2A8C82")
    s.arrow(1095,222,898,365,bend=-50)
    s.box(480, 350, 230, 120, "Blinded Reviewer A", ["fully supported", "partially supported", "unsupported · contradicted"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(480, 515, 230, 120, "Blinded Reviewer B", ["same claim-level rubric", "independent review record"], fill="#EEF0FA", accent="#5966A8")
    s.arrow(790,405,710,410)
    s.arrow(790,430,710,575,bend=-40)
    s.box(785, 515, 230, 120, "Adjudication + seal", ["final claim counts", "answer slot → system map", "retrieval metrics joined last"], fill="#FFF7E5", accent="#D99B2B")
    s.arrow(710,410,785,555,bend=40)
    s.arrow(710,575,785,595)
    s.box(1090, 520, 235, 130, "H5 bootstrap analysis", ["faithfulness = (full + .5 partial)/claims", "Spearman ρ vs retrieval metrics", "10,000 question-cluster samples"], fill="#EDF6F4", accent="#2A8C82", shadow=True)
    s.arrow(1015,575,1090,585,color="#2F6B9A")
    s.note(60, 540, 350, ["Estimability gates", "coverage ≥ 0.80 · SD ≥ 0.10 · ≥3 values"])
    s.pill(65, 685, 235, "300 full · 1 partial")
    s.pill(325, 685, 210, "0 unsupported")
    s.pill(560, 685, 210, "0 contradicted")
    s.pill(795, 685, 220, "faithfulness SD 0.0111")
    s.add('<rect x="1040" y="680" width="285" height="56" rx="12" fill="#FCEEEE" stroke="#B85C5C" stroke-width="1.5"/>')
    s.text(1182, 705, ["H5 verdict: NOT ESTIMABLE", "range-restriction gate failed"], cls="body")
    s.save("figure-4-6-generation-and-h5.svg")


def figure_47() -> None:
    s = SVG("Component and deployment view", "Single-host research deployment with persistent artefacts, in-process retrieval and evaluation modules, and external Claude API.")
    s.header("Component and deployment view", "Research deployment boundary and production-scaling substitutions")
    s.add('<rect x="55" y="125" width="1015" height="650" rx="22" fill="#F8FBFD" stroke="#2F6B9A" stroke-width="2"/>')
    s.text(85, 160, "SINGLE RESEARCH HOST", cls="stage", anchor="start")
    s.add('<rect x="85" y="190" width="360" height="535" rx="16" fill="#FFFFFF" stroke="#BFCED8" stroke-width="1.5"/>')
    s.text(115, 225, "PERSISTENT ARTEFACTS", cls="stage", anchor="start")
    stores = [
        (115,255,"Chunk manifest",["954-row JSONL","provenance hashes"]),
        (115,355,"BM25 index",["pickled rank-bm25","k1 1.2 · b 0.75"]),
        (115,455,"FAISS index",["IndexFlatIP + vectors","normalised cosine"]),
        (115,555,"Graph store",["NetworkX pickle","3,781 nodes · 26,430 edges"]),
        (115,655,"Experiment records",["configs · rankings · traces · metrics"]),
    ]
    for x,y,t,ls in stores: s.box(x,y,300,78,t,ls,fill="#F4F7FA",accent="#2F6B9A")
    s.add('<rect x="480" y="190" width="550" height="535" rx="16" fill="#FFFFFF" stroke="#BFCED8" stroke-width="1.5"/>')
    s.text(510, 225, "IN-PROCESS COMPONENTS", cls="stage", anchor="start")
    s.box(520, 265, 210, 90, "Retrievers", ["BM25 · FAISS", "Entity Graph v4"], fill="#EAF2F8", accent="#2F6B9A")
    s.box(790, 265, 200, 90, "Second stage", ["weighted hybrid", "Prompt-RAG client"], fill="#FFF7E5", accent="#D99B2B")
    s.box(520, 425, 210, 90, "Experiment runner", ["frozen query tiers", "zero-retry controls"], fill="#EDF6F4", accent="#2A8C82")
    s.box(790, 425, 200, 90, "Metrics + statistics", ["IR metrics", "bootstrap analysis"], fill="#EDF6F4", accent="#2A8C82")
    s.box(650, 590, 220, 82, "Generation client", ["H5 answer requests", "schema validation"], fill="#F6EEF8", accent="#8B5E9C")
    s.arrow(730,310,790,310)
    s.arrow(625,355,625,425)
    s.arrow(730,470,790,470)
    s.arrow(890,515,830,590,bend=-20)
    for y1,y2 in [(294,310),(394,310),(494,310),(594,310),(694,470)]: s.arrow(415,y1,520,y2,dashed=True)

    s.add('<rect x="1120" y="200" width="225" height="170" rx="16" fill="#F6EEF8" stroke="#8B5E9C" stroke-width="1.7"/>')
    s.text(1232, 238, "EXTERNAL SERVICE", cls="stage")
    s.text(1232, 282, "Anthropic Claude API", cls="box-title")
    s.text(1232, 315, ["Prompt-RAG reranking", "H5 answer generation"], cls="small")
    s.arrow(990,310,1120,285,dashed=True,color="#2F6B9A")
    s.arrow(870,630,1120,325,dashed=True,color="#2F6B9A",bend=90)

    s.add('<rect x="1120" y="430" width="225" height="295" rx="16" fill="#FFF9E8" stroke="#D99B2B" stroke-width="1.7" stroke-dasharray="8 6"/>')
    s.text(1232, 468, "PRODUCTION SCALE", cls="stage")
    s.text(1145, 515, ["① IndexFlatIP", "→ exact vector index", "", "② NetworkX pickle", "→ persistent graph store", "", "③ direct API calls", "→ cache + batch queue"], cls="body", anchor="start", gap=23)
    s.note(1130, 665, 205, ["Scaling changes throughput", "not reported comparisons."])
    s.save("figure-4-7-deployment-view.svg")


def main() -> None:
    for build in (figure_41, figure_42, figure_43, figure_44, figure_45, figure_46, figure_47):
        build()
    print(f"Wrote 7 SVG figures to {OUT}")


if __name__ == "__main__":
    main()
