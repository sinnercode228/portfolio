PY ?= .venv/bin/python

.PHONY: setup data demo check test all clean

setup:            ## create .venv and install dependencies
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

data:             ## regenerate the fictional sample CSVs in data/
	$(PY) generate_sample_data.py

demo: data        ## build the four sample workbooks in output/
	$(PY) build_dashboard.py data/production_log_sample.csv -o output/dashboard_sample.xlsx
	$(PY) build_dashboard.py data/production_log_sample_ru.csv --lang ru -o output/dashboard_sample_ru.xlsx
	$(PY) build_invoice.py data/work_log_sample.csv data/rates_sample.csv -o output/invoice_sample.xlsx
	$(PY) build_invoice.py data/work_log_sample_ru.csv data/rates_sample_ru.csv --lang ru -o output/invoice_sample_ru.xlsx

check:            ## lint + evaluate every formula in the sample workbooks
	$(PY) check_workbook.py output/dashboard_sample.xlsx output/dashboard_sample_ru.xlsx output/invoice_sample.xlsx output/invoice_sample_ru.xlsx

test:             ## run the test suite
	$(PY) -m pytest

all: demo check test

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__
