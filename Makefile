.PHONY: setup test eval eval-full app
setup:
	python -m pip install -r requirements.txt
test:
	python -m pytest -q
eval:
	python -m src.eval.run_eval --quick
eval-full:
	python -m src.eval.run_eval --full
app:
	python run.py
