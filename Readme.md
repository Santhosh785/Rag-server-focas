# FOCAS Exam Paper Generator

A robust PDF ingestion and exam paper generation system for study materials.

## Project Structure

```text
├── api/                # Vercel entry point
├── backend/            # Core FastAPI application
│   ├── ingestion/     # PDF extraction & processing
│   ├── services/      # Business logic (e.g., paper generation)
│   ├── utils/         # Helper functions
│   └── main.py        # FastAPI app entry point
├── frontend/           # React + Vite frontend
├── scripts/            # Debugging and maintenance scripts
├── tests/              # Verification and repro scripts
├── pdfs/               # Source PDF files (Level/Subject organization)
└── requirements.txt    # Python dependencies
```

## Setup

1. Create a `.env` file in the root with:
   - `MONGODB_URI`
   - `OPENAI_API_KEY`

2. Install dependencies:
   ```bash
   pip install -r requirements.txt


   source rag_venv/bin/activate
   ```

## Workflow

### 1. Ingest PDFs
Extract questions and answers from PDFs into MongoDB.
```bash
python -m backend.ingestion.ingest --pdf_dir ./pdfs
```

### 2. Run Backend
Start the FastAPI server (default: port 8000).
```bash
python -m backend.main
```

### 3. Run Frontend
Navigate to the frontend folder and start the dev server.
```bash
cd frontend
npm install
npm run dev
```

### 4. Verify Ingestion
Compare a PDF's content against the database to find missing questions.
```bash
python tests/verify_ingestion.py --pdf "./pdfs/Path/To/Your.pdf"
```

## Useful Scripts

- **Export to Markdown:**
  ```bash
  python scripts/export_all.py --subject FM --chapter 1
  ```
- **Sync Ingested Tracker:**
  ```bash
  python scripts/sync_ingested.py
  ```
- **Debug Regex:**
  ```bash
  python scripts/debug_regex_simple.py
  ```

## Deployment

The app is configured for Vercel deployment using the `api/index.py` entry point and `vercel.json` configuration.
1. Connect github repo to Vercel.
2. Set Environment Variables (`MONGODB_URI`, `OPENAI_API_KEY`).
3. Vercel will automatically build the React frontend and Python backend.
