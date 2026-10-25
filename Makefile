.PHONY: setup test eval eval-full app
setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
test:
	python tests/run_tests.py
eval:
	python -m src.eval.run_eval --quick
eval-full:
	python -m src.eval.run_eval --full
app:
	streamlit run app.py
