# SHA National Day flight project

This repository contains the original flight-event data and the final Word
report package in [`final_project_word`](./final_project_word).

## Final report package

- [`sha_national_day_final_report.docx`](./final_project_word/sha_national_day_final_report.docx)
  is the academic report.
- [`sha_national_day_final_executed.ipynb`](./final_project_word/sha_national_day_final_executed.ipynb)
  is the executed analysis notebook.
- [`sha_national_day_final.ipynb`](./final_project_word/sha_national_day_final.ipynb)
  is the notebook source.
- [`sha_national_day_final_results.json`](./final_project_word/sha_national_day_final_results.json)
  contains machine-readable summary results.
- [`figures`](./final_project_word/figures) contains the figures used by the
  report and notebook.

The proposal, presentation, and adjusted-workday analysis plan in the same
folder are supplementary materials.

## Original data and reproduction

[`sha_master.csv`](./sha_master.csv) is the supplied source dataset. The report
and notebook can be regenerated from the repository root with:

```bash
uv sync --group report
uv run --group report python scripts/build_word_final_project.py
uv run --group report jupyter nbconvert --execute --to notebook \
  final_project_word/sha_national_day_final.ipynb \
  --output sha_national_day_final_executed.ipynb \
  --output-dir final_project_word
```

The report generator also updates the figures and results JSON. The notebook
command writes its executed copy into `final_project_word`.
