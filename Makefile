.PHONY: install spacy-model acquire dataset faiss bm25 graphrag statistics compare test clean all-v2

install:
	pip install -r requirements.txt

spacy-model:
	python -m spacy download en_core_web_sm

# Full pipeline: ingest docs → build benchmark → run all experiments → compare
all: dataset faiss bm25 graphrag compare

all-v2: acquire dataset bm25 faiss graphrag statistics compare

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

# Ablation sweeps
ablation-chunks:
	for size in 256 512 1024; do \
		python experiments/run_bm25.py --top-k 10 --rebuild; \
		python experiments/run_faiss.py --top-k 10 --rebuild; \
	done

ablation-topk:
	for k in 1 3 5 10; do \
		python experiments/run_bm25.py --top-k $$k; \
		python experiments/run_faiss.py --top-k $$k; \
		python experiments/run_graphrag.py --top-k $$k; \
	done

test:
	python -m pytest tests/ -v --tb=short

test-coverage:
	python -m pytest tests/ --cov=src --cov-report=term-missing

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
