# Code Context Graph

Build a Neo4j knowledge graph from source code, then explore it through a FastAPI backend, a CLI, and a Next.js web UI.

The parser uses Python AST support for Python files and Tree-sitter for JavaScript, TypeScript, TSX, Go, Rust, and Java.

## Prerequisites

- Python 3.11 or newer
- Node.js and npm
- A running Neo4j database
- `uv` for Python dependency management

The app reads Neo4j connection settings from environment variables or a local `.env` file:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

## Install Dependencies

From the repository root:

```bash
source .venv/bin/activate
uv sync
export PYTHONPATH=src
```

Install the frontend dependencies:

```bash
cd web
npm install
cd ..
```

Optional LLM enrichment uses Anthropic:

```bash
uv sync --extra llm
export ANTHROPIC_API_KEY=your-api-key
```

Ask the Codebase uses Gemini:

```bash
export GOOGLE_API_KEY=your-google-api-key
export CODE_GRAPH_LLM_MODEL=gemini-3.5-flash
```

## Run the Backend API

Start the FastAPI server on port 8000:

```bash
source .venv/bin/activate
export PYTHONPATH=src
uv run ccg serve --host 0.0.0.0 --port 8000
```

The API is available at:

```text
http://localhost:8000
```

## Run the Web UI

In a second terminal:

```bash
cd web
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend rewrites `/api/*` requests to `http://localhost:8000/api/*`, so keep the backend running on port 8000 while using the UI.

## Ingest a Repository

You can ingest a local repository from the CLI:

```bash
source .venv/bin/activate
export PYTHONPATH=src
uv run ccg ingest /path/to/repository
```

To clear the existing graph before ingesting:

```bash
PYTHONPATH=src uv run ccg ingest /path/to/repository --clear
```

To clone and ingest a GitHub repository:

```bash
PYTHONPATH=src uv run ccg clone https://github.com/owner/repo.git
```

You can also ingest repositories from the web UI using the add-repository form.

## Query the Graph

Show graph statistics:

```bash
PYTHONPATH=src uv run ccg stats
```

Search entities:

```bash
PYTHONPATH=src uv run ccg search "query text"
```

Run a predefined query:

```bash
PYTHONPATH=src uv run ccg query MyFunction --kind calls
```

Supported query kinds include:

- `calls`
- `callers`
- `impact`
- `hierarchy`
- `imports`
- `importers`
- `cochange`
- `owners`
- `path`

## Optional Semantic Enrichment

After installing the `llm` extra and setting `ANTHROPIC_API_KEY`, enrich graph entities with semantic tags:

```bash
PYTHONPATH=src uv run ccg enrich --limit 50
```

## Ask the Codebase

The repo detail page includes an LLM-backed ad-hoc question panel. It generates read-only Cypher, validates the query, executes it, and summarizes the rows.

Set these values in `.env` before using it:

```bash
GOOGLE_API_KEY=your-google-api-key
CODE_GRAPH_LLM_MODEL=gemini-3.5-flash
```

## Run Tests

```bash
uv run pytest
```

Build the frontend:

```bash
cd web
npm run build
```
