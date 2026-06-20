#!/usr/bin/env python3
"""
Corpus Downloader — Indian Government Welfare Schemes
======================================================
Fetches documents from public sources, extracts text, runs the ingestion
pipeline (clean → chunk → enrich), and generates manifest/source registry.

Sources
-------
A: MyScheme API (JSON) with fallback to website scraping
B: PM-KISAN Guidelines PDF
C: PMJAY Operational Guidelines PDF
D: Wikipedia scheme pages (supplementary plaintext)

Outputs
-------
- data/raw/snapshot_v1/       ← raw downloaded files
- data/chunks/chunks_v1.jsonl ← processed chunks (one JSON per line)
- data/metadata/corpus_manifest.json ← aggregate statistics
- data/metadata/sources.csv    ← source registry
"""

import csv
import json
import logging
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    import fitz
except ImportError:
    fitz = None

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.ingestion.chunker import Chunker
from src.ingestion.metadata_enricher import MetadataEnricher
from src.ingestion.text_cleaner import TextCleaner

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)

CHUNK_SIZE = 300  # words (≈400 tokens at 1.33 tokens/word)
CHUNK_OVERLAP = 60  # words (≈80 tokens)
CRAWL_DATE = date.today().isoformat()
DOMAIN = "indian_government_welfare_schemes"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "snapshot_v1"
METADATA_DIR = Path(__file__).parent.parent / "data" / "metadata"
CHUNKS_DIR = Path(__file__).parent.parent / "data" / "chunks"


class CorpusDownloader:
    """Downloads, extracts, and processes welfare scheme documents."""

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

        self.documents = []  # Track all downloaded docs: {doc_id, source_name, source_type, source_url, text}
        self.chunks_list = []  # All enriched chunks
        self.source_stats = {}  # {source_name: {doc_count, chunk_count, source_type, source_url}}

    def run(self):
        """Execute full download → extract → ingest pipeline."""
        logger.info("Starting corpus downloader...")

        # Download from all sources
        self._download_myscheme()
        self._download_pmkisan()
        self._download_pmjay()
        self._download_wikipedia()

        if not self.documents:
            logger.error("No documents downloaded. Exiting.")
            return

        logger.info(f"Downloaded {len(self.documents)} documents. Starting ingestion pipeline...")

        # If we have fewer than 15 chunks from downloads, add fallback corpus
        if len(self.documents) < 5:
            logger.info("Download corpus is small. Adding fallback synthetic content...")
            self._add_fallback_corpus()

        # Process each document through the pipeline
        for doc in self.documents:
            self._process_document(doc)

        # Save outputs
        self._save_chunks()
        self._save_manifest()
        self._save_sources_csv()
        self._print_summary()

    def _download_myscheme(self):
        """Download from MyScheme API; fallback to website scraping."""
        source_name = "MyScheme"
        source_type = "api_json"
        source_url = "https://api.myscheme.gov.in/search/v4/schemes"

        logger.info(f"Attempting {source_name} API download...")
        try:
            # Try API first
            response = requests.get(
                source_url,
                params={"lang": "en", "q": "", "keyword": ""},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            schemes = data.get("schemes", [])
            if not schemes:
                logger.warning(f"{source_name} API returned empty. Attempting website scrape...")
                self._scrape_myscheme_website(source_name)
            else:
                for scheme in schemes:
                    doc_id = f"myscheme_{_slugify(scheme.get('name', 'unknown'))}"
                    text = self._flatten_scheme(scheme)

                    self.documents.append({
                        "doc_id": doc_id,
                        "source_name": source_name,
                        "source_type": source_type,
                        "source_url": source_url,
                        "text": text,
                    })
                    logger.info(f"  ✓ {doc_id}")

        except Exception as e:
            logger.warning(f"{source_name} API failed: {e}. Attempting website scrape...")
            self._scrape_myscheme_website(source_name)

    def _scrape_myscheme_website(self, source_name: str):
        """Scrape MyScheme website as fallback."""
        url = "https://www.myscheme.gov.in/schemes"
        source_type = "website_html"

        logger.info(f"Scraping {url}...")
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "lxml")

            # Extract scheme cards (adjust selector if needed)
            cards = soup.find_all("div", class_=re.compile(r"scheme|card", re.I))
            if not cards:
                logger.warning(f"No scheme cards found on {url}")
                return

            for card in cards[:50]:  # Limit to first 50 to avoid overload
                try:
                    name = card.find(["h2", "h3", "a"])
                    if not name:
                        continue
                    name_text = name.get_text(strip=True)
                    if not name_text:
                        continue

                    doc_id = f"myscheme_{_slugify(name_text)}"
                    description = card.find(["p", "span"])
                    description_text = description.get_text(strip=True) if description else ""

                    text = f"{name_text}\n{description_text}"

                    self.documents.append({
                        "doc_id": doc_id,
                        "source_name": source_name,
                        "source_type": source_type,
                        "source_url": url,
                        "text": text,
                    })
                    logger.info(f"  ✓ {doc_id}")
                except Exception as e:
                    logger.debug(f"Error parsing card: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")

    def _flatten_scheme(self, scheme: dict) -> str:
        """Convert scheme JSON dict to readable prose."""
        parts = []
        for key, value in scheme.items():
            if isinstance(value, str):
                parts.append(f"{key.replace('_', ' ').title()}: {value}")
            elif isinstance(value, list):
                parts.append(f"{key.replace('_', ' ').title()}: {', '.join(str(v) for v in value)}")
        return "\n".join(parts)

    def _download_pmkisan(self):
        """Download PM-KISAN Guidelines PDF."""
        source_name = "PM-KISAN Guidelines"
        source_type = "pdf"
        source_url = "https://pmkisan.gov.in/Documents/RevisedPM-KISANOperationalGuidelines.pdf"
        local_path = self.raw_dir / "pmkisan_guidelines.pdf"

        logger.info(f"Downloading {source_name}...")
        try:
            response = requests.get(source_url, timeout=30)
            response.raise_for_status()

            local_path.write_bytes(response.content)
            logger.info(f"  ✓ Saved to {local_path.name}")

            # Extract text
            text = self._extract_pdf_text(local_path)
            if text:
                doc_id = f"pmkisan_guidelines"
                self.documents.append({
                    "doc_id": doc_id,
                    "source_name": source_name,
                    "source_type": source_type,
                    "source_url": source_url,
                    "text": text,
                })
                logger.info(f"  ✓ Extracted text from {doc_id}")
        except Exception as e:
            logger.error(f"Failed to download {source_name}: {e}")

    def _download_pmjay(self):
        """Download PMJAY Operational Guidelines PDF."""
        source_name = "PMJAY Operational Guidelines"
        source_type = "pdf"
        source_url = "https://pmjay.gov.in/sites/default/files/2019-09/Final-Operational-Guidelines_0.pdf"
        local_path = self.raw_dir / "pmjay_guidelines.pdf"

        logger.info(f"Downloading {source_name}...")
        try:
            response = requests.get(source_url, timeout=30)
            response.raise_for_status()

            local_path.write_bytes(response.content)
            logger.info(f"  ✓ Saved to {local_path.name}")

            # Extract text
            text = self._extract_pdf_text(local_path)
            if text:
                doc_id = f"pmjay_guidelines"
                self.documents.append({
                    "doc_id": doc_id,
                    "source_name": source_name,
                    "source_type": source_type,
                    "source_url": source_url,
                    "text": text,
                })
                logger.info(f"  ✓ Extracted text from {doc_id}")
        except Exception as e:
            logger.error(f"Failed to download {source_name}: {e}")

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """Extract text from PDF using PyMuPDF."""
        if not fitz:
            logger.warning("PyMuPDF (fitz) not installed. Skipping PDF text extraction.")
            return ""

        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return "\n".join(text_parts)
        except Exception as e:
            logger.error(f"Failed to extract text from {pdf_path}: {e}")
            return ""

    def _download_wikipedia(self):
        """Scrape Wikipedia pages as supplementary plaintext."""
        pages = [
            ("Pradhan_Mantri_Awas_Yojana", "https://en.wikipedia.org/wiki/Pradhan_Mantri_Awas_Yojana"),
            ("MGNREGA", "https://en.wikipedia.org/wiki/Mahatma_Gandhi_National_Rural_Employment_Guarantee_Act"),
            ("PMJDY", "https://en.wikipedia.org/wiki/Pradhan_Mantri_Jan_Dhan_Yojana"),
            ("PMMY", "https://en.wikipedia.org/wiki/Pradhan_Mantri_Mudra_Yojana"),
            ("PMFBY", "https://en.wikipedia.org/wiki/Pradhan_Mantri_Fasal_Bima_Yojana"),
        ]

        source_type = "wiki"
        for slug, url in pages:
            source_name = f"Wikipedia: {slug.replace('_', ' ')}"
            logger.info(f"Scraping {source_name}...")

            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "lxml")

                # Extract main content (typical Wikipedia layout)
                content = soup.find("div", {"id": "mw-content-text"})
                if not content:
                    content = soup.find("div", {"class": "mw-parser-output"})
                if not content:
                    content = soup.find("main")

                if not content:
                    logger.warning(f"Could not find main content on {url}")
                    continue

                # Extract text from paragraphs and list items, skip sections
                text_parts = []
                for elem in content.find_all(["p", "li"]):
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:  # Skip very short snippets
                        text_parts.append(text)

                # Limit to first 2000 chars to get main overview without becoming too large
                text = "\n".join(text_parts)[:2500]

                if text:
                    doc_id = f"wiki_{_slugify(slug)}"
                    local_path = self.raw_dir / f"wiki_{slug.lower()}.txt"
                    local_path.write_text(text, encoding="utf-8")

                    self.documents.append({
                        "doc_id": doc_id,
                        "source_name": source_name,
                        "source_type": source_type,
                        "source_url": url,
                        "text": text,
                    })
                    logger.info(f"  ✓ {doc_id} ({len(text)} chars)")
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")

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

        logger.info(f"  ✓ {doc_id}: {len(chunks)} chunks")

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

    def _add_fallback_corpus(self):
        """Add fallback synthetic corpus if downloads fail or are insufficient."""
        fallback_docs = [
            {
                "doc_id": "pmkisan_fallback_1",
                "source_name": "PM-KISAN Guidelines",
                "source_type": "fallback",
                "source_url": "https://pmkisan.gov.in/",
                "text": """Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)
PM-KISAN is a centrally sponsored scheme with 100% funding from the Government of India.
The scheme provides income support to all landholding farmer families across the country to
supplement their financial needs for procurement of agricultural inputs like seeds, fertilizers,
pesticides, and other essential items. The scheme aims at supporting the welfare of all
landholding farmers by providing direct income support of Rs. 6,000 per year per beneficiary
farmer household. This support is provided in three equal installments of Rs. 2,000 each."""
            },
            {
                "doc_id": "pmkisan_fallback_2",
                "source_name": "PM-KISAN Guidelines",
                "source_type": "fallback",
                "source_url": "https://pmkisan.gov.in/",
                "text": """Eligibility and Implementation of PM-KISAN
All landholding farmer families whose names appear in the land records of the concerned
State/Union Territory shall be eligible to avail the benefits of the PM-KISAN scheme.
The scheme provides for payment of Rs. 6,000 per year to each beneficiary farmer in three
equal installments. The payment shall be made directly to the beneficiary farmer's bank account
through Direct Benefit Transfer (DBT) mechanism using Aadhaar. The farmer must have an active
bank account linked with their Aadhaar number for receiving the benefits under this scheme."""
            },
            {
                "doc_id": "pmjay_fallback_1",
                "source_name": "PMJAY Operational Guidelines",
                "source_type": "fallback",
                "source_url": "https://pmjay.gov.in/",
                "text": """Pradhan Mantri Jan Arogya Yojana (PMJAY)
PMJAY is the world's largest government-funded health assurance scheme. It provides a health
cover of Rs. 5 lakh per family per year for secondary and tertiary care hospitalization to
around 10.74 crore poor and vulnerable families. The scheme aims to reduce out-of-pocket
expenditure for health care and ensure equitable, affordable and reliable tertiary care for
economically weaker sections of the population. Coverage includes pre-hospitalization and
post-hospitalization expenses up to 3 days before and 15 days after hospitalization."""
            },
            {
                "doc_id": "pmjay_fallback_2",
                "source_name": "PMJAY Operational Guidelines",
                "source_type": "fallback",
                "source_url": "https://pmjay.gov.in/",
                "text": """PMJAY Beneficiaries and Beneficiary Identification
Beneficiaries are automatically included based on SECC 2011 data for landless households and
those with unorganized workers. About 10.74 crore families are beneficiaries of PMJAY. Each
family member can avail health services up to Rs. 5 lakh per year. The scheme covers all
emergency procedures and certain chronic conditions like hypertension and diabetes within
specified limits. All empanelled hospitals in the network are eligible to provide services."""
            },
            {
                "doc_id": "mgnrega_fallback_1",
                "source_name": "MGNREGA",
                "source_type": "fallback",
                "source_url": "https://mgnrega.nic.in/",
                "text": """Mahatma Gandhi National Rural Employment Guarantee Act (MGNREGA)
MGNREGA guarantees 100 days of wage employment in every financial year to every household
whose adult members volunteer to do unskilled manual work. The scheme is the largest social
security and public works program in the world. It aims to enhance livelihood security in rural
areas by providing guaranteed employment. The minimum wage rate is set by the government and
is paid directly to workers through bank transfers."""
            },
            {
                "doc_id": "pmjdy_fallback_1",
                "source_name": "Pradhan Mantri Jan Dhan Yojana",
                "source_type": "fallback",
                "source_url": "https://pmjdy.gov.in/",
                "text": """Pradhan Mantri Jan Dhan Yojana (PMJDY)
PMJDY is a national mission for financial inclusion designed to ensure access to financial
services for all households. The scheme enables every Indian household to open a bank account
with zero minimum balance and no monthly balance requirements. Account holders get a RuPay
debit card with built-in accident insurance of Rs. 1 lakh. The scheme also provides access to
government-subsidized life insurance and accident insurance coverage up to Rs. 30,000 and
Rs. 100,000 respectively."""
            },
            {
                "doc_id": "pmfby_fallback_1",
                "source_name": "Pradhan Mantri Fasal Bima Yojana",
                "source_type": "fallback",
                "source_url": "https://pmfby.gov.in/",
                "text": """Pradhan Mantri Fasal Bima Yojana (PMFBY)
PMFBY is a crop insurance scheme to protect farmers against crop loss due to natural disasters,
pests, and diseases. Farmers pay only a low premium (1.5-3% of the insured amount for most crops)
and the government subsidizes 75-90% of the premium. The scheme covers both named perils causing
yield loss and other insurable risks. Insurance coverage is on an area basis; if crop loss exceeds
the threshold level, all farmers growing that crop in the notified area are covered."""
            },
        ]

        for doc in fallback_docs:
            self.documents.append(doc)
            logger.info(f"Added fallback: {doc['doc_id']}")

    def _print_summary(self):
        """Print final summary."""
        total_chunks = len(self.chunks_list)
        avg_chunk_length = 0
        if total_chunks > 0:
            total_words = sum(c.get("word_count", 0) for c in self.chunks_list)
            avg_chunk_length = round(total_words / total_chunks, 1)

        print("\n" + "=" * 70)
        print("CORPUS DOWNLOAD SUMMARY")
        print("=" * 70)
        print(f"Total documents downloaded: {len(self.documents)}")
        print(f"Total chunks created: {total_chunks}")
        print(f"Average chunk length (words): {avg_chunk_length}")
        print("\nSources:")
        for name, stats in sorted(self.source_stats.items()):
            print(f"  • {name}: {stats['doc_count']} doc(s) → {stats['chunk_count']} chunk(s)")
        print("=" * 70 + "\n")


def _slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "_", text)
    return text


if __name__ == "__main__":
    downloader = CorpusDownloader()
    downloader.run()
