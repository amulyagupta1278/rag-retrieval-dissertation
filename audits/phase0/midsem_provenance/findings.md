# Mid-semester provenance findings

- VERIFIED: all five raw files first appear in `123932df629cd7e6379721b449baacd44557d5a1`.
- VERIFIED: direct word-based chunking with committed `Chunker(300, 60)` reproduces all ten IDs and texts.
- CONTRADICTED: “token” does not mean model/subword token; actual overlap ranges from 49 to 77 words.
- VERIFIED: benchmark contains 28 records across six categories with counts 9/4/2/2/5/6.
- INFERRED: questions are template-generated from committed six-category generator.
- UNVERIFIED: manual editing/review before the introducing commit.
- VERIFIED: qrels contain 78 resolving judgments: 45 grade 2 and 33 grade 1.
- UNVERIFIED: independent URL authenticity and human relevance validation.
