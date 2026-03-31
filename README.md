# Correspondence-Tracker

A lightweight correspondence intake and cross-reference tracker for disputes lawyers.

## Features

- Store each incoming letter with extracted metadata:
  - `from`, `to`, `issue_date`, `received_at`, `themes`, `summary`
- Automatic theme extraction from letter body
- Simple cross-referencing by content similarity
- CLI operations: `add`, `list`, `view`

## Setup

1. Install Python 3.11+ (3.10 is usually fine).
2. From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

No extra packages are required for the default implementation.

## Usage

- Add from file:

```bash
python src/tracker.py add --file /path/to/letter.txt
```

- Add from inline text:

```bash
python src/tracker.py add --content "Dear Client..." --from "X Solicitors" --to "Y Ltd" --date "2026-03-31"
```

- List saved letters:

```bash
python src/tracker.py list
```

- View letter with metadata and cross-references:

```bash
python src/tracker.py view 1
```

## Data storage

Data is stored in `data/correspondence.db` (SQLite). The directory is created automatically.

## Notes and next steps

- You can extend parser logic for PDF/Word import (e.g., using `pdfminer` / `python-docx`).
- Improve NLP with `scikit-learn` + `nltk` for robust theme detection and better matching.
- Add full-text search and privacy controls for sensitive dispute correspondence.
