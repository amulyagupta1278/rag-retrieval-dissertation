.PHONY: install spacy-model dataset faiss bm25 graphrag compare test clean

install:
	pip install -r requirements.txt

spacy-model:
	python -m spacy download en_core_web_sm

# Full pipeline: ingest docs → build benchmark → run all experiments → compare
all: dataset faiss bm25 graphrag compare

dataset:
	cd dissertation && python experiments/build_dataset.py

faiss:
	cd dissertation && python experiments/run_faiss.py --top-k 10 --rebuild

bm25:
	cd dissertation && python experiments/run_bm25.py --top-k 10 --rebuild

graphrag:
	cd dissertation && python experiments/run_graphrag.py --top-k 10 --rebuild

compare:
	cd dissertation && python experiments/compare_retrievers.py

# Ablation sweeps
ablation-chunks:
	for size in 256 512 1024; do \
		cd dissertation && python experiments/run_bm25.py --top-k 10 --rebuild; \
		cd dissertation && python experiments/run_faiss.py --top-k 10 --rebuild; \
	done

ablation-topk:
	for k in 1 3 5 10; do \
		cd dissertation && python experiments/run_bm25.py --top-k $$k; \
		cd dissertation && python experiments/run_faiss.py --top-k $$k; \
		cd dissertation && python experiments/run_graphrag.py --top-k $$k; \
	done

test:
	cd dissertation && python -m pytest tests/ -v --tb=short

test-coverage:
	cd dissertation && python -m pytest tests/ --cov=src --cov-report=term-missing

clean:
	find dissertation -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find dissertation -name "*.pyc" -delete 2>/dev/null || true
