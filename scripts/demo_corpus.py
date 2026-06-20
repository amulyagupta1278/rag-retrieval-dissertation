#!/usr/bin/env python3
"""
Demo Corpus Downloader with Sample Data
========================================
Demonstrates the complete ingestion pipeline with synthetic sample documents.
Useful for testing and verifying the pipeline before running against live sources.
"""

import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.ingestion.chunker import Chunker
from src.ingestion.metadata_enricher import MetadataEnricher
from src.ingestion.text_cleaner import TextCleaner

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)

CHUNK_SIZE = 300
CHUNK_OVERLAP = 60
CRAWL_DATE = date.today().isoformat()
DOMAIN = "indian_government_welfare_schemes"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "snapshot_v1"
METADATA_DIR = Path(__file__).parent.parent / "data" / "metadata"
CHUNKS_DIR = Path(__file__).parent.parent / "data" / "chunks"

# Sample documents for demonstration
SAMPLE_DOCUMENTS = [
    {
        "doc_id": "pmkisan_demo",
        "source_name": "PM-KISAN Guidelines",
        "source_type": "pdf",
        "source_url": "https://pmkisan.gov.in/Documents/RevisedPM-KISANOperationalGuidelines.pdf",
        "text": """Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)
=====================================
PM-KISAN is a centrally sponsored scheme with 100% funding from Government of India.
It provides income support to all landholding farmer families across the country to
supplement their financial needs for procurement of agricultural inputs like seeds,
fertilizers, pesticides, etc. The scheme aims to support the welfare of all landholding
farmers by providing direct income support of Rs. 6,000 per year per beneficiary farmer
household.

ELIGIBILITY:
All landholding farmer families whose names appear in the land records of the concerned
State/UT shall be eligible to avail the benefits of PM-KISAN scheme. The scheme provides
for payment of Rs. 6,000 per year to each beneficiary farmer in three equal installments.

IMPLEMENTATION:
The scheme shall be implemented through the existing system of District Administration
and State/UT Government with the support of PRIs and various government agencies.
The Central Government shall depute nodal officials to coordinate with State/UT.

PAYMENT MECHANISM:
The payment shall be made directly to the beneficiary farmer's bank account through
Direct Benefit Transfer (DBT) mechanism using Aadhaar. The farmer must have an active
bank account linked with their Aadhaar number for receiving the benefits.""",
    },
    {
        "doc_id": "pmjay_demo",
        "source_name": "PMJAY Operational Guidelines",
        "source_type": "pdf",
        "source_url": "https://pmjay.gov.in/sites/default/files/2019-09/Final-Operational-Guidelines_0.pdf",
        "text": """Pradhan Mantri Jan Arogya Yojana (PMJAY)
=====================================
PMJAY is the world's largest government-funded health assurance scheme. It provides
a health cover of Rs. 5 lakh per family per year for secondary and tertiary care
hospitalization to around 10.74 crore poor and vulnerable families.

OBJECTIVES:
To provide a health cover of Rs. 5 lakh per family per year for secondary and
tertiary care hospitalization in empanelled hospitals. To reduce out-of-pocket
expenditure for health care. To ensure equitable, affordable and reliable tertiary
care for economically weaker sections.

BENEFICIARIES:
Automatic inclusion based on SECC 2011 data for landless households and those with
unorganized workers. About 10.74 crore families are beneficiaries. Each family member
can avail health services up to Rs. 5 lakh per year.

COVERAGE:
The scheme covers pre-hospitalization and post-hospitalization expenses up to 3 days
before and 15 days after hospitalization. All emergency procedures are covered.
Certain conditions like hypertension and diabetes beyond certain limits are covered.""",
    },
    {
        "doc_id": "pmjdy_demo",
        "source_name": "Wikipedia: Pradhan Mantri Jan Dhan Yojana",
        "source_type": "wiki",
        "source_url": "https://en.wikipedia.org/wiki/Pradhan_Mantri_Jan_Dhan_Yojana",
        "text": """Pradhan Mantri Jan Dhan Yojana (PMJDY)
====================================
Pradhan Mantri Jan Dhan Yojana is a national mission for financial inclusion in India
designed to ensure access to financial services, namely banking savings accounts,
remittance, credit, insurance, and pension. The scheme was launched by Prime Minister
Narendra Modi on August 28, 2014.

OBJECTIVES:
To ensure access to financial services for all households. To open bank accounts for
low-income individuals. To encourage digital transactions. To provide government
subsidized life and accident insurance.

ACCOUNT FEATURES:
No minimum balance required. Digital payment facility through RuPay debit card.
Overdraft facility available for eligible accounts. Free life insurance coverage up to
Rs. 30,000 for account holders.

INSURANCE COVERAGE:
Coverage includes life insurance of Rs. 100,000 and accidental insurance of Rs. 100,000
for account holders. The benefits are provided at no cost to the account holder.""",
    },
]


class DemoCorpusDownloader:
    """Demonstrates the ingestion pipeline with sample data."""

    def __init__(self):
        self.raw_dir = RAW_DIR
        self.metadata_dir = METADATA_DIR
        self.chunks_dir = CHUNKS_DIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

        self.cleaner = TextCleaner()
        self.chunker = Chunker(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            min_chunk_length=50,
            respect_sentence_boundaries=True,
        )
        self.enricher = MetadataEnricher()

        self.documents = []
        self.chunks_list = []
        self.source_stats = {}

    def run(self):
        """Execute demo pipeline with sample documents."""
        logger.info("Starting DEMO corpus downloader with sample data...")
        logger.info(f"Processing {len(SAMPLE_DOCUMENTS)} sample documents...")

        self.documents = SAMPLE_DOCUMENTS

        # Process each document
        for doc in self.documents:
            self._process_document(doc)

        # Save outputs
        self._save_chunks()
        self._save_manifest()
        self._save_sources_csv()
        self._print_summary()

    def _process_document(self, doc: dict):
        """Run document through clean → chunk → enrich pipeline."""
        doc_id = doc["doc_id"]
        text = doc["text"]
        source_name = doc["source_name"]

        # 1. Clean
        cleaned = self.cleaner.clean(text)

        # 2. Chunk
        chunks = self.chunker.chunk_document(
            doc_id=doc_id,
            text=cleaned,
            source_path="",
            domain_tag=DOMAIN,
            section_title=source_name,
            extra_meta={
                "source_name": source_name,
                "source_type": doc["source_type"],
                "crawl_date": CRAWL_DATE,
                "domain": DOMAIN,
            },
        )

        # 3. Enrich & collect
        for chunk in chunks:
            chunk_dict = chunk.to_dict()
            enriched = self.enricher.enrich(chunk_dict)
            self.chunks_list.append(enriched)

        # Track source stats
        if source_name not in self.source_stats:
            self.source_stats[source_name] = {
                "doc_count": 0,
                "chunk_count": 0,
                "source_type": doc["source_type"],
                "source_url": doc["source_url"],
            }
        self.source_stats[source_name]["doc_count"] += 1
        self.source_stats[source_name]["chunk_count"] += len(chunks)

        total_words = sum(c.word_count for c in chunks)
        logger.info(f"  ✓ {doc_id}: {len(chunks)} chunks ({total_words} words)")

    def _save_chunks(self):
        """Save all chunks as JSONL."""
        output_path = self.chunks_dir / "chunks_v1.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for chunk in self.chunks_list:
                f.write(json.dumps(chunk) + "\n")
        logger.info(f"Saved {len(self.chunks_list)} chunks to {output_path.name}")

    def _save_manifest(self):
        """Save corpus manifest with aggregate statistics."""
        total_chunks = len(self.chunks_list)
        avg_chunk_length = 0
        if total_chunks > 0:
            total_words = sum(c.get("word_count", 0) for c in self.chunks_list)
            avg_chunk_length = round(total_words / total_chunks, 2)

        source_breakdown = {
            name: {
                "doc_count": stats["doc_count"],
                "chunk_count": stats["chunk_count"],
            }
            for name, stats in self.source_stats.items()
        }

        manifest = {
            "crawl_date": CRAWL_DATE,
            "total_documents": len(self.documents),
            "total_chunks": total_chunks,
            "avg_chunk_length_words": avg_chunk_length,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "source_breakdown": source_breakdown,
            "domain": DOMAIN,
        }

        output_path = self.metadata_dir / "corpus_manifest.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Saved manifest to {output_path.name}")

    def _save_sources_csv(self):
        """Save source registry."""
        output_path = self.metadata_dir / "sources.csv"
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "source_id",
                    "source_name",
                    "source_type",
                    "source_url",
                    "crawl_date",
                    "doc_count",
                    "chunk_count",
                ],
            )
            writer.writeheader()

            for i, (name, stats) in enumerate(self.source_stats.items(), 1):
                writer.writerow({
                    "source_id": i,
                    "source_name": name,
                    "source_type": stats["source_type"],
                    "source_url": stats["source_url"],
                    "crawl_date": CRAWL_DATE,
                    "doc_count": stats["doc_count"],
                    "chunk_count": stats["chunk_count"],
                })

        logger.info(f"Saved sources registry to {output_path.name}")

    def _print_summary(self):
        """Print final summary."""
        total_chunks = len(self.chunks_list)
        avg_chunk_length = 0
        if total_chunks > 0:
            total_words = sum(c.get("word_count", 0) for c in self.chunks_list)
            avg_chunk_length = round(total_words / total_chunks, 1)

        print("\n" + "=" * 70)
        print("DEMO CORPUS SUMMARY")
        print("=" * 70)
        print(f"Total documents processed: {len(self.documents)}")
        print(f"Total chunks created: {total_chunks}")
        print(f"Average chunk length (words): {avg_chunk_length}")
        print("\nSources:")
        for name, stats in sorted(self.source_stats.items()):
            print(f"  • {name}: {stats['doc_count']} doc(s) → {stats['chunk_count']} chunk(s)")
        print("\nOutput Files:")
        print(f"  • Chunks: data/chunks/chunks_v1.jsonl")
        print(f"  • Manifest: data/metadata/corpus_manifest.json")
        print(f"  • Sources: data/metadata/sources.csv")
        print("=" * 70 + "\n")

        # Show sample chunk
        if self.chunks_list:
            sample = self.chunks_list[0]
            print("SAMPLE CHUNK (first chunk):")
            print("-" * 70)
            print(f"chunk_id: {sample['chunk_id']}")
            print(f"doc_id: {sample['doc_id']}")
            print(f"word_count: {sample['word_count']}")
            print(f"source_name: {sample['extra_meta'].get('source_name', 'N/A')}")
            print(f"domain_tags: {sample['domain_tags']}")
            print(f"Text (first 200 chars):\n{sample['text'][:200]}...\n")


if __name__ == "__main__":
    downloader = DemoCorpusDownloader()
    downloader.run()
