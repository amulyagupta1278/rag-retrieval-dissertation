# Corpus Downloader

## Overview

`download_corpus.py` fetches publicly available Indian government welfare scheme documents from multiple sources, extracts text, and runs the complete ingestion pipeline (clean → chunk → enrich).

## Usage

### 1. Install Dependencies

```bash
pip install -r requirements-corpus.txt
```

### 2. Run the Downloader

```bash
python scripts/download_corpus.py
```

## Data Sources

| Source | Type | URL | Fallback |
|--------|------|-----|----------|
| **MyScheme API** | JSON | api.myscheme.gov.in | Website scraping |
| **PM-KISAN Guidelines** | PDF | pmkisan.gov.in | (none) |
| **PMJAY Guidelines** | PDF | pmjay.gov.in | (none) |
| **Wikipedia Schemes** | HTML | en.wikipedia.org | (none) |

### Schemes Covered

- Pradhan Mantri Awas Yojana (housing)
- MGNREGA (rural employment)
- Pradhan Mantri Jan Dhan Yojana (financial inclusion)
- Pradhan Mantri Mudra Yojana (small business)
- Pradhan Mantri Fasal Bima Yojana (crop insurance)

## Outputs

### Chunks
- **File:** `data/chunks/chunks_v1.jsonl`
- **Format:** One enriched chunk per line (JSON)
- **Fields:** chunk_id, doc_id, text, word_count, source_name, source_type, crawl_date, domain_tags, estimated_reading_time_s, has_numbers, sentence_count, etc.

### Manifest
- **File:** `data/metadata/corpus_manifest.json`
- **Contents:**
  - `total_documents`: total docs downloaded
  - `total_chunks`: total chunks after processing
  - `avg_chunk_length_words`: mean chunk size
  - `chunk_size`: configured window size (words)
  - `chunk_overlap`: configured overlap (words)
  - `source_breakdown`: dict mapping source names to {doc_count, chunk_count}
  - `crawl_date`: YYYY-MM-DD

### Sources Registry
- **File:** `data/metadata/sources.csv`
- **Columns:** source_id, source_name, source_type, source_url, crawl_date, doc_count, chunk_count

## Processing Pipeline

1. **Download:** Fetch from all sources with graceful fallback on failure
2. **Extract:** Format-specific extraction
   - **PDF:** PyMuPDF (fitz) page-by-page extraction
   - **JSON:** Flatten nested fields to readable prose
   - **HTML:** BeautifulSoup tag stripping + paragraph extraction
3. **Clean:** Unicode normalization, boilerplate removal, whitespace collapse
4. **Chunk:** 300-word sliding windows (≈400 tokens) with 60-word overlap (≈80 tokens), respecting sentence boundaries
5. **Enrich:** Add computed metadata (reading time, domain tags, has_numbers, sentence_count)

## Configuration

Edit constants in `download_corpus.py`:

```python
CHUNK_SIZE = 300          # words per chunk
CHUNK_OVERLAP = 60        # words of overlap
DOMAIN = "indian_government_welfare_schemes"
```

## Error Handling

- **Network failures:** Logged and skipped; other sources continue
- **PDF extraction failure:** Falls back to graceful skip
- **Scraping failures:** Falls back to alternative sources (e.g., MyScheme API → website)
- **Empty results:** Logged as warnings; corpus proceeds with remaining sources

## Logging

All operations logged to stdout with [INFO], [WARNING], [ERROR] prefixes. Final summary printed at completion.
