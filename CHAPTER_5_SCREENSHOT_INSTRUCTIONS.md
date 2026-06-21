# Screenshot Instructions for Chapter 5

## How to Embed Evidence in Your Dissertation

Below are instructions for capturing and embedding each evidence screenshot into your Word/LaTeX dissertation document at the specified locations in Chapter 5.

---

## Screenshot Checklist

### **SS1** — Corpus Manifest (for Section 5.2)
**Location in Chapter 5:** First paragraph, after "source provenance"  
**How to capture:**
```bash
cat data/metadata/corpus_manifest.json
```
**Visual requirement:**
- Show JSON structure with document list
- Include timestamps and file sizes
- Dark terminal (black background preferred)
**Save as:** `SS1_corpus_manifest.png`  
**Dimension:** ~900px width minimum

---

### **SS2** — Chunk Statistics (for Section 5.2)
**Location in Chapter 5:** "Chunking statistics" paragraph  
**How to capture:**
```bash
python3 << 'EOF'
import json
chunks = []
with open('data/chunks/chunks_v1.jsonl') as f:
    for line in f:
        chunks.append(json.loads(line))
lengths = [len(c['text'].split()) for c in chunks]
sources = {}
for c in chunks:
    s = c.get('source_name', 'unknown')
    sources[s] = sources.get(s, 0) + 1
print(f'Total chunks     : {len(chunks)}')
print(f'Avg chunk length : {sum(lengths)/len(lengths):.1f} words')
print(f'Min chunk length : {min(lengths)} words')
print(f'Max chunk length : {max(lengths)} words')
print()
print('Chunks per source:')
for source, count in sorted(sources.items(), key=lambda x: -x[1]):
    print(f'  {source}: {count}')
EOF
```
**Expected output:**
- Total chunks: 10
- Avg chunk length: 244.5 words
- Min/Max range
- Per-source breakdown
**Save as:** `SS2_chunk_statistics.png`

---

### **SS3** — QA Dataset Overview (for Section 5.2)
**Location in Chapter 5:** "The QA dataset" paragraph  
**How to capture:** Show first part of `evidence/S5_qa_dataset_overview.txt`  
**Content:**
- Total QA items: 28
- Category breakdown (7 terminology, 9 exact, etc.)
- Difficulty levels
- Sample questions
**Save as:** `SS3_qa_dataset_overview.png`

---

### **SS4** — Qrels Statistics (for Section 5.2)
**Location in Chapter 5:** "The qrels file" paragraph  
**How to capture:**
```bash
python3 << 'EOF'
from collections import Counter
grades = Counter()
queries = set()
with open('data/qrels/qrels.tsv') as f:
    for i, line in enumerate(f):
        if i == 0: continue
        parts = line.strip().split('\t')
        if len(parts) >= 4:
            queries.add(parts[0])
            grades[int(parts[3])] += 1
print(f'Total judgements : {sum(grades.values())}')
print(f'Unique queries   : {len(queries)}')
print(f'Gold (2)         : {grades[2]}')
print(f'Relevant (1)     : {grades[1]}')
print(f'Not relevant (0) : {grades[0]}')
print(f'Avg gold per query: {grades[2]/len(queries):.2f}')
EOF
```
**Expected output:**
- Total judgements: 56
- Gold: 57
- Avg per query: 2.04
**Save as:** `SS4_qrels_statistics.png`

---

### **SS5** — BM25 Index Build (for Section 5.3.1)
**Location:** After "Index construction" in BM25 subsection  
**How to capture:**
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from retrievers.bm25_retriever import BM25Retriever
import json
chunks = []
with open('data/chunks/chunks_v1.jsonl') as f:
    for line in f:
        chunks.append(json.loads(line))
retriever = BM25Retriever(index_path='indexes/bm25/bm25_index.pkl')
retriever.build_index(chunks)
print(f'BM25 index built successfully')
print(f'Chunks indexed: {len(chunks)}')
import os
for f in os.listdir('indexes/bm25/'):
    size = os.path.getsize(f'indexes/bm25/{f}')
    print(f'  {f}: {size:,} bytes')
EOF
```
**Expected output:**
- "successfully"
- Chunks indexed: 10
- File sizes (~1.6 KB)
**Save as:** `SS5_bm25_index_build.png`

---

### **SS6** — BM25 Run Results Sample (for Section 5.3.1)
**Location:** After "Run file output"  
**How to capture:**
```bash
python3 << 'EOF'
import json
with open('runs/retrieval/bm25_run.jsonl') as f:
    runs = [json.loads(line) for line in f]
print(f'Total queries in run file: {len(runs)}')
print(f'Queries with results: {sum(1 for r in runs if r["results"])}')
print()
print('Sample results (first 2 queries):')
for run in runs[:2]:
    print(f'Query: {run["query_text"][:60]}')
    print(f'Results: {len(run["results"])} retrieved')
    if run["results"]:
        for r in run["results"][:2]:
            print(f'  - {r["chunk_id"]}: score={r["score"]:.4f}')
    print()
EOF
```
**Expected output:**
- Total: 28
- With results: 28
- Sample chunk IDs and scores
**Save as:** `SS6_bm25_run_sample.png`

---

### **SS7** — FAISS Index Status (for Section 5.3.2)
**Location:** After "The FAISS index is persisted"  
**How to capture:**
```bash
ls -lh indexes/faiss/
```
**Expected output:**
- faiss.index (~large file)
- chunk_ids.json
- config.json
- Approximate sizes shown
**Save as:** `SS7_faiss_index_files.png`

---

### **SS8** — GraphRAG Graph Statistics (for Section 5.3.3)
**Location:** After "Graph construction persists"  
**How to capture:**
```bash
python3 << 'EOF'
import os, json
path = 'indexes/graphrag/graph.json'
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print(f'Graph Statistics:')
    print(f'  Nodes: {len(data.get("nodes", []))}')
    print(f'  Edges: {len(data.get("edges", []))}')
    print(f'  File size: {os.path.getsize(path):,} bytes')
    
    from collections import Counter
    node_types = Counter(n.get('type', 'unknown') for n in data.get('nodes', []))
    print(f'\nNode types:')
    for t, c in sorted(node_types.items(), key=lambda x: -x[1]):
        print(f'  {t}: {c}')
EOF
```
**Expected output:**
- Node and edge counts
- File size
- Node type breakdown
**Save as:** `SS8_graphrag_graph_stats.png`

---

### **SS9** — Comparison Metrics Table (for Section 5.4.2)
**Location:** After "The comparison summary shows:"  
**How to capture:**
```bash
python3 << 'EOF'
import csv
with open('runs/metrics/comparison_summary.csv') as f:
    reader = csv.DictReader(f)
    print('=== OVERALL METRICS ===')
    for row in reader:
        print(f'{row["Retriever"]}: MRR@5={row["MRR@5"]} Recall@10={row["Recall@10"]} Latency={row["Avg Latency (ms)"]}')
EOF
```
**Expected output:**
- All three retrievers (BM25, FAISS, GraphRAG)
- Key metrics visible
- Column headers
**Save as:** `SS9_comparison_metrics.png`

---

### **SS10** — Per-Category Performance (for Section 5.4.2)
**Location:** After "The per-category breakdown"  
**How to capture:**
```bash
head -10 runs/metrics/per_category.csv
```
**Expected output:**
- Category column
- BM25, FAISS, GraphRAG columns
- At least 6 category rows visible
- Header row included
**Save as:** `SS10_per_category_metrics.png`

---

## General Screenshot Guidelines

1. **Terminal theme:** Use a dark terminal (black background, white/bright text) for readability in print

2. **Command visibility:** Include the command that produced the output at the top of each screenshot (can be typed or visible in shell prompt)

3. **Width:** Minimum 900 pixels width to ensure numbers and output are readable in printed dissertation

4. **Cropping:** Crop to remove unnecessary whitespace above/below the key output, but include full command + output

5. **Naming:** Use exact filenames provided (SS1.png, SS2.png, etc.) for consistent referencing

6. **Format:** PNG format recommended for crisp text rendering (JPG acceptable but less ideal for terminal output)

---

## Embedding in Word Document

1. In your Word document, find the marker: `[INSERT SS1 HERE]` (etc. for each screenshot)

2. Insert the PNG file at that location

3. Right-click → Compress Picture → reduce file size to ~200KB per image for manageable document size

4. Add caption below each figure: "Figure 5.X: [Description from this document]"

5. Cross-reference in text: "As shown in Figure 5.X, ..."

---

## Embedding in LaTeX

If using LaTeX:

```latex
\begin{figure}[h]
\centering
\includegraphics[width=0.9\textwidth]{SS1_corpus_manifest.png}
\caption{Corpus manifest showing document sources and metadata.}
\label{fig:corpus-manifest}
\end{figure}
```

---

## Troubleshooting

**Q: Screenshot shows different output than expected**  
A: Make sure you're running the exact command from the instructions, and the working directory is the dissertation root.

**Q: Image is too small/blurry**  
A: Increase terminal font size before screenshotting (e.g., Ctrl++ in most terminals), or increase terminal window width to at least 900px.

**Q: How do I know if a file is missing?**  
A: If a command fails with "file not found" or "does not exist", that's expected for optional runs that haven't been executed yet. Reference the MISSING_ evidence file instead.

---

## Evidence File Cross-Reference

If you don't want to re-run commands, you can also extract text from the pre-generated evidence files in the `evidence/` directory:

- `evidence/S1_corpus_manifest.txt` → SS1
- `evidence/S4_chunk_statistics.txt` → SS2
- `evidence/S5_qa_dataset_overview.txt` → SS3
- `evidence/S6_qrels_statistics.txt` → SS4
- `evidence/S7_bm25_index_build.txt` → SS5
- `evidence/S8_bm25_run_sample.txt` → SS6
- `evidence/S9_faiss_index_status.txt` → SS7
- `evidence/S11_graph_status.txt` → SS8
- `evidence/S15_comparison_metrics.txt` → SS9-SS10

Simply screenshot or copy-paste the relevant sections from these files if the live commands don't produce the expected output.
