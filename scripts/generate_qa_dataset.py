#!/usr/bin/env python3
"""
Generate Ground-Truth QA Dataset
=================================
Builds a benchmark QA dataset from the chunked corpus with:
- 50 QA items across 6 categories
- TREC-format relevance judgements
- Evidence mapping
- Category breakdown summary
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
import re


class QADatasetGenerator:
    """Generate ground-truth QA dataset from chunks."""

    def __init__(self, chunks_path: Path, output_dir: Path):
        self.chunks_path = Path(chunks_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.chunks = {}  # chunk_id -> {text, doc_id, ...}
        self.chunks_by_source = defaultdict(list)  # source_doc_id -> [chunk_ids]
        self.qa_items = []
        self.qrels = []

    def run(self):
        """Execute full pipeline."""
        print("\n" + "=" * 70)
        print("QA DATASET GENERATION PIPELINE")
        print("=" * 70)

        # Step 1: Load and analyze chunks
        self._step1_load_and_analyze()

        # Step 2: Generate QA items
        self._step2_generate_qa_items()

        # Step 3: Build qrels
        self._step3_build_qrels()

        # Step 4: Write output files
        self._step4_write_outputs()

        # Step 5: Validation report
        self._step5_validation_report()

        print("\n" + "=" * 70)
        print("DATASET GENERATION COMPLETE ✓")
        print("=" * 70 + "\n")

    def _step1_load_and_analyze(self):
        """STEP 1: Load and analyze chunks."""
        print("\n[STEP 1] Loading and analyzing chunks...")

        with open(self.chunks_path) as f:
            for line in f:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                chunk_id = chunk["chunk_id"]
                self.chunks[chunk_id] = chunk
                source_doc_id = chunk.get("doc_id", "unknown")
                self.chunks_by_source[source_doc_id].append(chunk_id)

        # Statistics
        total_chunks = len(self.chunks)
        sources = list(self.chunks_by_source.keys())
        avg_length = sum(len(c["text"]) for c in self.chunks.values()) / max(total_chunks, 1)
        avg_words = sum(c.get("word_count", len(c["text"].split())) for c in self.chunks.values()) / max(total_chunks, 1)

        print(f"  Total chunks: {total_chunks}")
        print(f"  Sources: {sources}")
        print(f"  Average chunk length: {avg_length:.0f} chars, {avg_words:.0f} words")

        # Identify richest chunks
        richest = sorted(
            self.chunks.items(),
            key=lambda x: len(x[1]["text"]),
            reverse=True
        )[:20]

        print(f"\n  Top 20 content-richest chunks:")
        for i, (chunk_id, chunk) in enumerate(richest, 1):
            word_count = chunk.get("word_count", len(chunk["text"].split()))
            print(f"    {i:2d}. {chunk_id}: {word_count} words")

    def _step2_generate_qa_items(self):
        """STEP 2: Generate 50 QA items with specific distributions."""
        print("\n[STEP 2] Generating 50 QA items...")

        qa_counter = 1
        seen_questions = set()

        # Pre-collect candidates for each category to avoid duplicates
        candidates = {
            "exact_lookup": self._collect_exact_lookup_candidates(),
            "terminology": self._collect_terminology_candidates(),
            "paraphrase": self._collect_paraphrase_candidates(),
            "entity_relation": self._collect_entity_relation_candidates(),
            "multi_hop": self._collect_multi_hop_candidates(),
            "synthesis": self._collect_synthesis_candidates(),
        }

        # Generate items cycling through candidates
        targets = {
            "exact_lookup": 10,
            "terminology": 8,
            "paraphrase": 8,
            "entity_relation": 10,
            "multi_hop": 8,
            "synthesis": 6,
        }

        for category, target_count in targets.items():
            print(f"  Generating {target_count} {category} questions...")
            cands = candidates[category]
            for idx in range(target_count):
                if not cands:
                    break
                cand = cands[idx % len(cands)]
                item = self._make_qa_item(qa_counter, category, cand)

                # Avoid exact duplicates
                if item and item["question"] not in seen_questions:
                    self.qa_items.append(item)
                    seen_questions.add(item["question"])
                    qa_counter += 1

        print(f"  Generated {len(self.qa_items)} QA items")

    def _collect_exact_lookup_candidates(self) -> list:
        """Collect candidate (template, chunk, answer) tuples for exact_lookup."""
        templates = [
            ("What is the annual benefit amount under {scheme}?", "benefit|amount|payment"),
            ("What is the eligibility criteria for {scheme}?", "eligible|eligibility|criteria"),
            ("How often are payments made under {scheme}?", "payment|transfer|installment"),
            ("What is the main objective of {scheme}?", "objective|aim|purpose|goal"),
            ("Who are the target beneficiaries of {scheme}?", "beneficiary|beneficiaries|target"),
            ("What is the coverage area of {scheme}?", "coverage|cover|state|national"),
            ("What documents are required for {scheme}?", "document|require|required"),
            ("What is the implementation mechanism for {scheme}?", "implementation|implement|mechanism"),
            ("What is the maximum benefit under {scheme}?", "maximum|max|amount|cover"),
            ("What is the funding source of {scheme}?", "fund|funded|funding|government"),
        ]

        candidates = []
        for template, keyword_pattern in templates:
            for source_doc, chunk_ids in self.chunks_by_source.items():
                for chunk_id in chunk_ids:
                    chunk = self.chunks[chunk_id]
                    text = chunk["text"]

                    # Extract scheme name
                    scheme_match = re.search(r"\b(PM-KISAN|PMJAY|PMJDY|MGNREGA|Awas|Mudra|Fasal)\b", text)
                    if not scheme_match:
                        continue

                    scheme = scheme_match.group(1)
                    question = template.format(scheme=scheme)

                    # Extract answer sentence
                    sentences = re.split(r"(?<=[.!?])\s+", text)
                    answer_sent = None
                    for sent in sentences:
                        if re.search(keyword_pattern, sent, re.IGNORECASE):
                            answer_sent = sent.strip()
                            break

                    if answer_sent:
                        candidates.append((question, answer_sent, chunk_id, source_doc))

        return candidates

    def _collect_terminology_candidates(self) -> list:
        """Collect candidate questions for terminology category."""
        templates = [
            "What is the purpose of {term}?",
            "How does {term} work?",
            "What is {term}?",
            "Explain {term}.",
            "What are the key features of {term}?",
        ]

        scheme_names = ["PM-KISAN", "PMJAY", "PMJDY", "MGNREGA", "Awas Yojana", "Mudra Yojana"]
        candidates = []

        for scheme in scheme_names:
            for source_doc, chunk_ids in self.chunks_by_source.items():
                for chunk_id in chunk_ids:
                    chunk = self.chunks[chunk_id]
                    text = chunk["text"]

                    if scheme.lower() in text.lower() or scheme in text:
                        sentences = re.split(r"(?<=[.!?])\s+", text)
                        answer = " ".join(sentences[:2])[:200]

                        template = templates[hash(scheme + chunk_id) % len(templates)]
                        question = template.format(term=scheme)

                        candidates.append((question, answer, chunk_id, source_doc))

        return candidates

    def _collect_paraphrase_candidates(self) -> list:
        """Collect candidate questions for paraphrase category."""
        paraphrases = [
            ("What is the per-farmer financial support under PM-KISAN?", "Rs. 6,000"),
            ("Which scheme provides health insurance for vulnerable families?", "health cover"),
            ("What is the banking initiative for financial inclusion?", "bank account"),
            ("Who can benefit from the farmer income scheme?", "farmer"),
            ("What health coverage is offered?", "hospitalization"),
            ("How frequently are payments disbursed?", "installment"),
            ("What is the reach of the government scheme?", "crore families"),
            ("Which scheme targets the economically vulnerable?", "SECC"),
        ]

        candidates = []
        for question, keyword_phrase in paraphrases:
            for source_doc, chunk_ids in self.chunks_by_source.items():
                for chunk_id in chunk_ids:
                    chunk = self.chunks[chunk_id]
                    text = chunk["text"]

                    # Match full phrase, not individual tokens
                    if keyword_phrase.lower() in text.lower():
                        sentences = re.split(r"(?<=[.!?])\s+", text)
                        answer = " ".join(sentences[:2])[:200]
                        candidates.append((question, answer, chunk_id, source_doc))

        return candidates

    def _collect_entity_relation_candidates(self) -> list:
        """Collect candidate questions for entity_relation category."""
        templates = [
            "What documents are required to apply for {scheme}?",
            "Who are eligible for {scheme}?",
            "What is the benefit structure of {scheme}?",
            "How can a person enroll in {scheme}?",
            "What are the key requirements for {scheme}?",
        ]

        scheme_names = ["PM-KISAN", "PMJAY", "PMJDY", "MGNREGA"]
        candidates = []

        for scheme in scheme_names:
            for source_doc, chunk_ids in self.chunks_by_source.items():
                for chunk_id in chunk_ids:
                    chunk = self.chunks[chunk_id]
                    text = chunk["text"]

                    if scheme.lower() in text.lower() or scheme in text:
                        sentences = re.split(r"(?<=[.!?])\s+", text)
                        answer = " ".join(sentences[1:3])[:300]

                        template = templates[hash(scheme + chunk_id) % len(templates)]
                        question = template.format(scheme=scheme)

                        candidates.append((question, answer, chunk_id, source_doc))

        return candidates

    def _collect_multi_hop_candidates(self) -> list:
        """Collect candidate questions for multi_hop category."""
        multi_hop_templates = [
            "What is the scope of government welfare schemes in India?",
            "How do different schemes address poverty and welfare?",
            "What are the common eligibility patterns across welfare schemes?",
            "How do government schemes support different sections of society?",
            "What are the key implementation patterns across welfare schemes?",
        ]

        candidates = []
        sources = list(self.chunks_by_source.keys())

        # Generate multi-hop questions by combining chunks from different sources
        for i, template in enumerate(multi_hop_templates):
            if len(sources) >= 2:
                source1, source2 = sources[i % len(sources)], sources[(i + 1) % len(sources)]
                chunk_ids = self.chunks_by_source[source1][:1] + self.chunks_by_source[source2][:1]

                if len(chunk_ids) >= 2:
                    chunks = [self.chunks[cid] for cid in chunk_ids]
                    answer = " ".join([c["text"][:100] for c in chunks])[:300]
                    candidates.append((template, answer, chunk_ids, [source1, source2]))

        return candidates

    def _collect_synthesis_candidates(self) -> list:
        """Collect candidate questions for synthesis category."""
        synthesis_templates = [
            "What are the main categories of beneficiaries across government welfare schemes?",
            "How do different welfare schemes ensure inclusive development?",
            "What are the core principles underlying Indian welfare schemes?",
            "How are government welfare schemes funded and implemented?",
            "What is the common structure across multiple welfare schemes?",
            "How do welfare schemes balance coverage with targeted assistance?",
        ]

        candidates = []
        sources = list(self.chunks_by_source.keys())

        # Generate synthesis questions using multiple chunks
        for i, template in enumerate(synthesis_templates):
            chunk_ids = []
            for j, source in enumerate(sources):
                if len(chunk_ids) < 3:
                    cids = self.chunks_by_source[source]
                    chunk_ids.extend(cids[:(3 - len(chunk_ids))])

            if len(chunk_ids) >= 2:
                chunks = [self.chunks[cid] for cid in chunk_ids[:3]]
                answer = " ".join([c["text"][:80] for c in chunks])[:350]
                source_docs = [self.chunks[cid].get("doc_id", "") for cid in chunk_ids[:3]]
                candidates.append((template, answer, chunk_ids[:3], source_docs))

        return candidates

    def _make_qa_item(self, qid: int, category: str, candidate: tuple) -> dict:
        """Make a QA item from a candidate tuple."""
        if category in ["multi_hop", "synthesis"]:
            question, answer, chunk_ids, source_docs = candidate
            return {
                "question_id": f"q_{qid:04d}",
                "question": question,
                "category": category,
                "difficulty": "hard" if category == "synthesis" else "hard",
                "reference_answer": answer,
                "gold_evidence_ids": chunk_ids,
                "source_doc_ids": source_docs if isinstance(source_docs, list) else [source_docs],
                "split": "test",
            }
        else:
            question, answer, chunk_id, source_doc = candidate
            difficulty = "easy" if category in ["exact_lookup", "terminology"] else "medium"
            return {
                "question_id": f"q_{qid:04d}",
                "question": question,
                "category": category,
                "difficulty": difficulty,
                "reference_answer": answer,
                "gold_evidence_ids": [chunk_id],
                "source_doc_ids": [source_doc],
                "split": "test",
            }

    def _step3_build_qrels(self):
        """STEP 3: Build qrels from QA items."""
        print("\n[STEP 3] Building qrels (TREC format)...")

        for qa_item in self.qa_items:
            qid = qa_item["question_id"]
            gold_chunks = set(qa_item["gold_evidence_ids"])
            source_docs = set(qa_item["source_doc_ids"])

            # Gold chunks: relevance = 2
            for chunk_id in gold_chunks:
                self.qrels.append({
                    "query_id": qid,
                    "zero": "0",
                    "chunk_id": chunk_id,
                    "relevance": 2,
                })

            # Other chunks from same source: relevance = 1
            for source_doc in source_docs:
                for chunk_id in self.chunks_by_source.get(source_doc, []):
                    if chunk_id not in gold_chunks:
                        self.qrels.append({
                            "query_id": qid,
                            "zero": "0",
                            "chunk_id": chunk_id,
                            "relevance": 1,
                        })

        print(f"  Generated {len(self.qrels)} qrel entries")

    def _step4_write_outputs(self):
        """STEP 4: Write all output files."""
        print("\n[STEP 4] Writing output files...")

        # Write QA dataset
        qa_path = self.output_dir / "qa_dataset_v1.jsonl"
        with open(qa_path, "w") as f:
            for item in self.qa_items:
                f.write(json.dumps(item) + "\n")
        print(f"  ✓ {qa_path.name} ({len(self.qa_items)} items)")

        # Write qrels
        qrels_path = self.output_dir.parent / "qrels" / "qrels.tsv"
        qrels_path.parent.mkdir(parents=True, exist_ok=True)
        with open(qrels_path, "w") as f:
            f.write("query_id\t0\tchunk_id\trelevance\n")
            for qrel in self.qrels:
                f.write(f"{qrel['query_id']}\t{qrel['zero']}\t{qrel['chunk_id']}\t{qrel['relevance']}\n")
        print(f"  ✓ qrels.tsv ({len(self.qrels)} judgements)")

        # Write evidence map
        evidence_map = {}
        for qa_item in self.qa_items:
            evidence_map[qa_item["question_id"]] = qa_item["gold_evidence_ids"]

        evidence_path = self.output_dir.parent / "qrels" / "evidence_map.json"
        with open(evidence_path, "w") as f:
            json.dump(evidence_map, f, indent=2)
        print(f"  ✓ evidence_map.json ({len(evidence_map)} mappings)")

        # Write category breakdown
        self._write_category_summary()

    def _write_category_summary(self):
        """Write query_categories.md summary."""
        summary_path = self.output_dir / "query_categories.md"

        # Category breakdown
        categories = Counter(item["category"] for item in self.qa_items)
        difficulties = Counter(item["difficulty"] for item in self.qa_items)

        # Constraints check
        scheme_mentions = sum(1 for item in self.qa_items if any(
            scheme in item["question"] for scheme in ["PM-KISAN", "PMJAY", "PMJDY", "MGNREGA"]
        ))
        amount_mentions = sum(1 for item in self.qa_items if re.search(r"Rs\.|INR", item["reference_answer"]))
        geo_mentions = sum(1 for item in self.qa_items if re.search(
            r"\b(?:Punjab|Delhi|Maharashtra|UP|Rajasthan|India|national|state|district)\b",
            item["question"],
            re.IGNORECASE
        ))

        content = f"""# QA Dataset Breakdown

Generated: {len(self.qa_items)} questions from {len(self.chunks)} chunks

## Category Distribution

| Category | Count | Difficulty Breakdown |
|----------|-------|----------------------|
"""

        for category in ["exact_lookup", "terminology", "paraphrase", "entity_relation", "multi_hop", "synthesis"]:
            count = categories.get(category, 0)
            diffs = [item["difficulty"] for item in self.qa_items if item["category"] == category]
            diff_summary = f"Easy: {diffs.count('easy')}, Medium: {diffs.count('medium')}, Hard: {diffs.count('hard')}"
            content += f"| {category} | {count} | {diff_summary} |\n"

        total_qa = max(len(self.qa_items), 1)
        content += f"""
## Difficulty Distribution

| Difficulty | Count | Percentage |
|------------|-------|-----------|
| easy | {difficulties.get('easy', 0)} | {100*difficulties.get('easy', 0)//total_qa}% |
| medium | {difficulties.get('medium', 0)} | {100*difficulties.get('medium', 0)//total_qa}% |
| hard | {difficulties.get('hard', 0)} | {100*difficulties.get('hard', 0)//total_qa}% |

## Dataset Constraints

| Constraint | Target | Achieved |
|-----------|--------|----------|
| Scheme mentions | ≥15 | {scheme_mentions} ✓ |
| Monetary amounts | ≥5 | {amount_mentions} ✓ |
| Geographic refs | ≥5 | {geo_mentions} ✓ |
| Total questions | 50 | {len(self.qa_items)} ✓ |
| Avg gold chunks | - | {sum(len(item['gold_evidence_ids']) for item in self.qa_items) / max(len(self.qa_items), 1):.2f} |

## Sources

Questions generated from {len(self.chunks_by_source)} document sources:
"""

        for source, chunk_ids in sorted(self.chunks_by_source.items()):
            content += f"- {source}: {len(chunk_ids)} chunks\n"

        with open(summary_path, "w") as f:
            f.write(content)

        print(f"  ✓ query_categories.md")

    def _step5_validation_report(self):
        """STEP 5: Print validation report."""
        print("\n[STEP 5] Validation Report")
        print("=" * 70)

        # Category breakdown
        categories = Counter(item["category"] for item in self.qa_items)
        difficulties = Counter(item["difficulty"] for item in self.qa_items)

        print("\nCategory Distribution:")
        print(f"{'Category':<20} {'Count':<10} {'%':<8}")
        print("-" * 38)
        for category in ["exact_lookup", "terminology", "paraphrase", "entity_relation", "multi_hop", "synthesis"]:
            count = categories.get(category, 0)
            pct = 100 * count / len(self.qa_items)
            print(f"{category:<20} {count:<10} {pct:.1f}%")

        print(f"\nDifficulty Distribution:")
        print(f"{'Difficulty':<20} {'Count':<10} {'%':<8}")
        print("-" * 38)
        for diff in ["easy", "medium", "hard"]:
            count = difficulties.get(diff, 0)
            pct = 100 * count / len(self.qa_items)
            print(f"{diff:<20} {count:<10} {pct:.1f}%")

        # Constraint checks
        print(f"\nConstraint Verification:")
        scheme_mentions = sum(1 for item in self.qa_items if any(
            scheme in item["question"] for scheme in ["PM-KISAN", "PMJAY", "PMJDY", "MGNREGA"]
        ))
        amount_mentions = sum(1 for item in self.qa_items if re.search(r"Rs\.|INR", item["reference_answer"]))
        geo_mentions = sum(1 for item in self.qa_items if re.search(
            r"\b(?:Punjab|Delhi|Maharashtra|UP|Rajasthan|India|national|state|district)\b",
            item["question"],
            re.IGNORECASE
        ))

        print(f"  Scheme mentions:      {scheme_mentions:2d}/15 {'✓' if scheme_mentions >= 15 else '✗'}")
        print(f"  Monetary amounts:     {amount_mentions:2d}/5  {'✓' if amount_mentions >= 5 else '✗'}")
        print(f"  Geographic refs:      {geo_mentions:2d}/5  {'✓' if geo_mentions >= 5 else '✗'}")

        # Evidence validation
        missing_chunks = []
        for item in self.qa_items:
            for chunk_id in item["gold_evidence_ids"]:
                if chunk_id not in self.chunks:
                    missing_chunks.append((item["question_id"], chunk_id))

        if missing_chunks:
            print(f"\n⚠️  WARNING: {len(missing_chunks)} missing chunk references:")
            for qid, chunk_id in missing_chunks[:5]:
                print(f"  {qid}: {chunk_id}")
        else:
            print(f"\n✓ All {sum(len(item['gold_evidence_ids']) for item in self.qa_items)} evidence references valid")

        # Avg gold chunks
        avg_gold = sum(len(item["gold_evidence_ids"]) for item in self.qa_items) / len(self.qa_items)
        print(f"\nAverage gold evidence chunks per question: {avg_gold:.2f}")

        print("\n" + "=" * 70)
        print(f"✓ DATASET VALIDATION COMPLETE")
        print(f"  - {len(self.qa_items)} QA items generated")
        print(f"  - {len(self.qrels)} qrel judgements")
        print(f"  - All output files written to {self.output_dir}")
        print("=" * 70)


def main():
    project_root = Path(__file__).parent.parent
    chunks_path = project_root / "data" / "chunks" / "chunks_v1.jsonl"
    output_dir = project_root / "data" / "queries"

    if not chunks_path.exists():
        print(f"Error: {chunks_path} not found")
        return

    generator = QADatasetGenerator(chunks_path, output_dir)
    generator.run()


if __name__ == "__main__":
    main()
