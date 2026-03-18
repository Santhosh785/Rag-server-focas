# Focas PDF Ingestion & Query

## Setup
Ensure you have a `.env` file in the root directory with the following variables:
- `MONGODB_URI`
- `OPENAI_API_KEY`

Then install dependencies:
```bash
./.venv/bin/python -m pip install -r requirements.txt
```


## Ingest PDFs
Ingests all PDFs from the `./pdfs` directory, skipping already ingested files.
```bash
./.venv/bin/python ingest.py --pdf_dir ./pdfs
```

## Query Database
Find a specific question by Level, Subject, Chapter, and Question Number.
```bash
./.venv/bin/python query.py --level Final --subject FM --chapter 1 --question 3
```

## Sync Tracker
Refresh the `ingested_files.json` tracker from the database.
```bash
./.venv/bin/python sync_ingested.py
```

## Run Backend (FastAPI)
Navigate to the backend directory and run the server.
```bash
cd backend
../.venv/bin/python main.py
```

## Run Frontend (React/Vite)
Navigate to the frontend directory and start the development server.
```bash
cd frontend
npm run dev
```

## Export Questions
Export questions from the database into a Markdown file for easy verification.

- **Export All:**
  ```bash
  ./.venv/bin/python export_all.py
  ```
- **Filter by Chapter:**
  ```bash
  ./.venv/bin/python export_all.py --chapter 3
  ```
- **Filter by Level/Subject:**
  ```bash
  ./.venv/bin/python export_all.py --level Intermediate --subject FM --chapter 1
  ```
The output file will be named according to your filters (e.g., `export_ch3.md`).

## Verify Ingestion
Automatically compare a PDF's content against the database to find missing questions.
```bash
./.venv/bin/python verify_ingestion.py --pdf "./path/to/your.pdf"
```
This tool scans the PDF for "Question X" markers and cross-checks them with MongoDB. It will list exactly which questions are missing from the database.
