.PHONY: test demo eval serve book-assets release-baseline verify
PYTHON ?= python3

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

demo:
	$(PYTHON) run.py demo --output artifacts/demo
	$(PYTHON) run.py serve --port 8000

eval:
	$(PYTHON) run.py evaluate --output artifacts/eval-report.json

serve:
	$(PYTHON) run.py serve --port 8000

book-assets:
	$(PYTHON) tools/verify_book_assets.py

release-baseline:
	$(PYTHON) tools/verify_release_baseline.py

verify:
	$(PYTHON) tools/verify.py
