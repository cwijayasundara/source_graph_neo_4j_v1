# Code Context Graph

Build a Neo4j knowledge graph from source code, then explore it through a FastAPI backend, a CLI, and a Next.js web UI.

The parser uses Python AST support for Python files and Tree-sitter for JavaScript, TypeScript, TSX, Go, Rust, and Java.

## What You Need

- Python 3.11 or newer
- Node.js and npm
- `uv` for Python dependency management
- Docker Desktop or another Docker Compose-compatible runtime
- (Optional, for COBOL analysis) JDK 17 and Maven — to build the bundled COBOL extractor

## Quick Start

Run these commands from the repository root.

### 1. Create Your `.env`

Copy the example environment file:

```bash
cp .env.example .env
```

The backend loads values from `.env` automatically through `python-dotenv`. You do not need to export these variables manually for normal CLI or API use.

Default local Neo4j settings:

```bash
NEO4J_URI=bolt://localhost:7689
NEO4J_USER=neo4j
NEO4J_PASSWORD=please-change-me
```

LLM key (required for semantic enrichment, BRD generator/judge, and Ask the Codebase) also goes in `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
CODE_GRAPH_LLM_MODEL=claude-sonnet-4-6   # global default; leave blank to use Haiku for cheap paths
```

For COBOL analysis (optional), also set these in `.env` (see the "COBOL support" section below for the one-time JAR build). With `JAVA_HOME` set, Java does not need to be on your `PATH`:

```bash
JAVA_HOME=/path/to/jdk-17
CCG_COBOL_EXTRACTOR_JAR=tools/cobol-extractor/target/ccg-cobol-extractor.jar
CCG_COBOL_COPYBOOK_DIRS=/abs/path/to/copybooks   # comma-separated; resolves COPY statements
CCG_COBOL_FORMAT=FIXED                            # FIXED | VARIABLE | TANDEM
```

Leave `CCG_COBOL_EXTRACTOR_JAR` unset to disable COBOL ingestion.

### 2. Start Neo4j

Start the bundled Neo4j Community Edition container:

```bash
docker compose up -d neo4j
```

Neo4j Browser is available at:

```text
http://localhost:7474
```

Bolt is exposed on:

```text
bolt://localhost:7689
```

Check the container status:

```bash
docker compose ps
```

### 3. Install Backend Dependencies

```bash
uv sync
```

### 4. Install Frontend Dependencies

```bash
cd web
npm install
cd ..
```

### 5. Start the Backend API

In one terminal:

```bash
uv run ccg serve --host 0.0.0.0 --port 8000
```

The API runs at:

```text
http://localhost:8000
```

### 6. Start the Web UI

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

## Daily Development Commands

Start Neo4j:

```bash
docker compose up -d neo4j
```

Stop Neo4j:

```bash
docker compose down
```

Show Neo4j logs:

```bash
docker compose logs -f neo4j
```

Start the backend:

```bash
uv run ccg serve --host 0.0.0.0 --port 8000
```

Start the frontend:

```bash
cd web
npm run dev
```

## Ingest a Repository

You can ingest a local repository from the CLI:

```bash
uv run ccg ingest /path/to/repository
```

To clear the existing graph before ingesting:

```bash
uv run ccg ingest /path/to/repository --clear
```

To clone and ingest a GitHub repository:

```bash
uv run ccg clone https://github.com/owner/repo.git
```

You can also ingest repositories from the web UI using the add-repository form.

### COBOL support

COBOL is parsed by a bundled Java extractor (built on the ProLeap parser). It is **not** a separate service — the backend runs it as a one-shot subprocess during ingestion, so you use the same single API and web UI as for any other language. Setup is one-time:

1. Build the extractor JAR (requires JDK 17 and Maven):

   ```bash
   mvn -f tools/cobol-extractor/pom.xml package
   ```

   This produces `tools/cobol-extractor/target/ccg-cobol-extractor.jar`. Rebuild only if you change the extractor's Java code.

2. In `.env`, set `JAVA_HOME`, `CCG_COBOL_EXTRACTOR_JAR`, and — for `COPY` resolution — `CCG_COBOL_COPYBOOK_DIRS` (see step 1 of the Quick Start).

3. Ingest a folder containing `.cbl` / `.cob` / `.cobol` files, via the CLI or the web UI's add-repository form:

   ```bash
   uv run ccg ingest /path/to/cobol-sources
   ```

   COBOL programs, sections, paragraphs, and `PERFORM` / `CALL` / `COPY` relationships appear in the graph alongside other languages. `CALL`/`COPY` targets that are not in the ingested set show as external nodes.

If the JAR or a working JVM is unavailable, COBOL files are skipped with a warning and other languages still ingest normally. v1 produces a structural call graph; data items, CICS, and embedded SQL are not yet modeled.

## Query the Graph

Show graph statistics:

```bash
uv run ccg stats
```

Search entities:

```bash
uv run ccg search "query text"
```

Run a predefined query:

```bash
uv run ccg query MyFunction --kind calls
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

With `ANTHROPIC_API_KEY` in `.env`, enrich graph entities with semantic tags via Claude:

```bash
uv run ccg enrich --limit 50
```

## Ask the Codebase

The repo detail page includes an LLM-backed ad-hoc question panel. It generates read-only Cypher, validates the query, executes it, and summarizes the rows.

Set these values in `.env` before using it. They are picked up automatically by the backend:

```bash
ANTHROPIC_API_KEY=sk-ant-...
ASK_MODEL=                    # optional: defaults to CODE_GRAPH_LLM_MODEL (Haiku tier)
```

Then start the backend and frontend from the Quick Start steps.

## Troubleshooting

If the backend fails with `Connection refused` for Neo4j, check that the container is running:

```bash
docker compose ps
```

If it is not running, start it:

```bash
docker compose up -d neo4j
```

If the backend fails with an authentication error, make sure `.env` matches `docker-compose.yml`:

```bash
NEO4J_URI=bolt://localhost:7689
NEO4J_USER=neo4j
NEO4J_PASSWORD=please-change-me
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
