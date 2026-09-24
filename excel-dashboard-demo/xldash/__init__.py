"""xldash — turn raw CSV logs into live Excel workbooks (openpyxl).

Demo project: every company, person and number in the sample data is fictional.

Modules
-------
sample_data   generators for fictional production and work logs (CSV)
production    load / clean the production log + reference aggregations
worklog       load / clean the time log and the rates table
dashboard     build the production dashboard workbook
invoice       build the time-and-materials invoice + payroll workbook
formula_check static lint + formula evaluation (pycel) for generated workbooks
"""

__version__ = "1.0.0"

DEMO_BRAND = "Quillmoor Machining"
DEMO_CONTRACTOR = "Nimbra Digital"
DEMO_CLIENT = "Quillmoor Machining"
