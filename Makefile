.PHONY: install spacy-model acquire dataset faiss bm25 graphrag statistics compare test clean all \
	release-corpus release-indexes release-benchmark release-evaluate release-statistics \
	release-verify release-v3-clean verify-v2-baseline

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
	python experiments/compare_retrievers.py

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
