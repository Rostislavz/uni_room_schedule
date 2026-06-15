# uni_room_schedule

This repository has two branch roles:

- `main`: update pipeline source (Python scripts + GitHub Actions workflow).
- `gh_pages`: published static site embedded into Google Sites.

## Automated updates

Workflow: `.github/workflows/update-pages-data.yml`

- Runs daily at `04:15 UTC`.
- Also supports manual run from GitHub Actions UI.
- Pipeline:
  1. refresh institute cache (`fetch_institute_groups.py`)
  2. download schedules (`batch_schedule_downloader.py`)
  3. rebuild room files (`generate_room_status.py --force`)
  4. rebuild static web data (`scripts/build_static_data.py`)
  5. publish `index.html`, `style.css`, `script.js`, `_headers`, `data/` to `gh_pages`

## Manual local run (same as workflow)

```bash
python -m pip install -r requirements.txt
python fetch_institute_groups.py
python batch_schedule_downloader.py
python generate_room_status.py --force
python scripts/build_static_data.py
```

## Thanks

Inspired by [lpnu.pp.ua](https://lpnu.pp.ua/)

Please, star the great work of https://github.com/cupoftea4/timetable
