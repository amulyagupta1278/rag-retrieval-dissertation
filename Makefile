.PHONY: install spacy-model acquire dataset faiss bm25 graphrag statistics compare test clean all \
	release-corpus release-indexes release-benchmark release-evaluate release-statistics \
	release-verify release-v3-clean verify-v2-baseline benchmark-audit-r1

VERSION ?= v3_clean
WORK_DIR ?= releases/.work-$(VERSION)
RELEASE_ARGS = --version $(VERSION) --work-dir $(WORK_DIR)

install:
	pip install -r requirements.txt

spacy-model:
	python -m spacy download en_core_web_sm

# The default build is the gated, atomic v3 release.  Legacy one-off targets
# below remain available for local diagnostics only.
all: release-v3-clean

acquire:
	python scripts/download_corpus.py

dataset:
	python experiments/build_dataset.py

faiss:
	python experiments/run_faiss.py --top-k 10 --rebuild

bm25:
	python experiments/run_bm25.py --top-k 10 --rebuild

graphrag:
	python experiments/run_graphrag.py --top-k 10 --rebuild

statistics:
	python scripts/generate_corpus_statistics.py

compare:
	python experiments/compare_retrievers.py --qa-dataset data/queries/qa_dataset.jsonl --chunks data/chunks/chunks.jsonl

# Creates review workbooks only. Publication/model selection remain blocked
# until real reviewers complete them.
benchmark-audit-r1:
	python scripts/prepare_benchmark_audit.py \
		--qa releases/v3_clean/data/queries/qa_dataset_v3_clean.jsonl \
		--qrels releases/v3_clean/data/qrels/qrels_v3_clean.tsv \
		--chunks releases/v3_clean/data/chunks/chunks_v3_clean.jsonl \
		--run bm25=releases/v3_clean/runs/retrieval/bm25_run.jsonl \
		--run faiss=releases/v3_clean/runs/retrieval/faiss_run.jsonl \
		--run entity_graph=releases/v3_clean/runs/retrieval/graphrag_run.jsonl \
		--output-dir audits/v3_clean_benchmark_r1

# Deterministic release pipeline. Each stage consumes only the preceding
# staging paths; publication happens only after release-verify succeeds.
release-corpus:
	python scripts/release_pipeline.py $(RELEASE_ARGS) --stage corpus --clean-work

release-indexes: release-corpus
	python scripts/release_pipeline.py $(RELEASE_ARGS) --stage indexes

release-benchmark: release-indexes
	python scripts/release_pipeline.py $(RELEASE_ARGS) --stage benchmark

release-evaluate: release-benchmark
	python scripts/release_pipeline.py $(RELEASE_ARGS) --stage evaluate

release-statistics: release-evaluate
	python scripts/release_pipeline.py $(RELEASE_ARGS) --stage statistics

release-verify: release-statistics
	python scripts/release_pipeline.py $(RELEASE_ARGS) --stage verify --replace --publish-canonical --verify-determinism

release-v3-clean: release-verify

verify-v2-baseline:
	python scripts/release_manifest.py \
		--include-root data/baselines/serialized_json_baseline \
		--include-root indexes/baselines/serialized_json_baseline \
		--include-root runs/baselines/serialized_json_baseline \
		--base-dir . \
		--manifest data/baselines/serialized_json_baseline/release_manifest.jsonl \
		--sums data/baselines/serialized_json_baseline/BASELINE_SHA256SUMS \
		--verify

test:
	python -m pytest tests/ -v --tb=short

test-coverage:
	python -m pytest tests/ --cov=src --cov-report=term-missing

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
