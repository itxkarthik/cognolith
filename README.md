# Personal Knowledge Assistant

A self-hosted workspace for Markdown notes, documents, knowledge graphs, and contextual chat. The application runs as a Next.js frontend, FastAPI backend, and PostgreSQL database.

## Features

- Markdown notes with Obsidian-style live preview
- `[[Wiki links]]`, backlinks, and automatic graph relationships
- Full and local knowledge graph views
- Nested note folders and tags
- PDF, DOCX, Markdown, and text document ingestion
- Authenticated, user-isolated workspaces
- Optional local model integration through Ollama

## Quick Start

### Requirements

- Docker Desktop or Docker Engine with Compose
- Git

### Run the stack

```bash
git clone https://github.com/Karthik-Git763/Personal-AI-Knowledge-Assistant.git
cd Personal-AI-Knowledge-Assistant
docker compose up --build -d
```

Open:

- Application: [http://localhost:8080](http://localhost:8080)
- API documentation: [http://localhost:3000/docs](http://localhost:3000/docs)
- Backend health: [http://localhost:3000/health/ready](http://localhost:3000/health/ready)

Check service health:

```bash
docker compose ps
```

Stop the stack:

```bash
docker compose down
```

Database data is stored in the `postgres_data` Docker volume and is preserved between restarts.

## Configuration

Copy the example environment file and set secure local values before deployment:

```bash
cp backend/.env.example backend/.env
```

The main settings are:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_USER` | PostgreSQL user |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `POSTGRES_DB` | Database name |
| `SECRET_KEY` | Token-signing secret |
| `FRONTEND_HOST` | Allowed frontend origin |
| `OLLAMA_BASE_URL` | Optional Ollama endpoint |

Ollama is optional for notes, documents, authentication, and graph features. AI requests require a reachable Ollama server and an installed model.

## Notes and Graphs

Notes are stored as Markdown. Link notes by title:

```markdown
This idea extends [[Distributed Systems]].
```

Saving the note creates a directed graph relationship. Renaming or deleting the wiki link updates that relationship. The graph also supports manually created `related`, `parent`, and `child` links.

## Development

Install dependencies from the repository root:

```bash
pnpm install
python -m pip install -r requirements.txt
```

Run the frontend:

```bash
pnpm --dir frontend dev
```

Run the backend in another terminal:

```bash
cd backend
python run.py
```

The local frontend expects PostgreSQL and the backend to be available. Docker Compose is the recommended development path when working across the full stack.

## Verification

```bash
frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit
frontend/node_modules/.bin/vitest run
docker compose build frontend backend
docker compose up -d
docker compose ps
```

## Architecture

```text
Browser
  |
  v
Next.js frontend :8080
  |
  v
FastAPI backend :3000
  |
  +--> PostgreSQL + pgvector :5432
  |
  +--> Ollama (optional)
```

Key directories:

```text
frontend/app/          Next.js routes
frontend/components/   UI and feature components
frontend/lib/          API clients, hooks, and utilities
frontend/store/        Zustand stores
backend/app/api/       FastAPI routes
backend/app/services/  Application services
backend/app/models/    SQLModel database models
backend/app/schemas/   Request and response schemas
```

## Contributing

Keep pull requests focused, include verification steps, and document any environment or schema changes. Use clear commit messages that describe behavior rather than implementation detail.
