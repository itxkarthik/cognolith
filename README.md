# Personal AI Knowledge Assistant

Private AI for agents, assistants, and enterprise knowledge workflows.

Personal AI Knowledge Assistant is an open-source platform for building intelligent assistants over your private knowledge. It combines document ingestion, note management, semantic retrieval, and conversational AI in a full-stack architecture using FastAPI and Next.js. Deploy locally or in your own infrastructure with full control over data and model providers.

[![GitHub stars](https://img.shields.io/github/stars/Karthik-Git763/Personal-AI-Knowledge-Assistant?style=for-the-badge)](https://github.com/Karthik-Git763/Personal-AI-Knowledge-Assistant/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/Karthik-Git763/Personal-AI-Knowledge-Assistant?style=for-the-badge)](https://github.com/Karthik-Git763/Personal-AI-Knowledge-Assistant/network/members)
[![License](https://img.shields.io/github/license/Karthik-Git763/Personal-AI-Knowledge-Assistant?style=for-the-badge)](https://github.com/Karthik-Git763/Personal-AI-Knowledge-Assistant/blob/main/LICENSE)
<!-- [![Discord](https://img.shields.io/badge/Discord-Community-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/)
[![X](https://img.shields.io/badge/X-Follow-000000?style=for-the-badge&logo=x&logoColor=white)](https://x.com/) -->

Quickstart: [Self-Hosted Setup](#quickstart)
Cloud Version: Coming soon
<!-- Community: [Discord](https://discord.gg/) -->

Contribute: Open issues and pull requests in this repository

<!-- ## Demo -->

## Key Features

- Wide file support: ingest and process text-centric formats such as PDF, DOCX, Markdown, and plain text with extensible file processing in the backend.
- AI-assisted workflows: architecture is prepared for RAG, embeddings, vector search, and model abstraction across local and cloud providers.
- Unified experience: manage documents, notes, chats, and search from a single web application.
- Source-aware retrieval: backend models include chunking and metadata structures to support cited, grounded responses.
- Modular APIs: FastAPI route and service structure designed for clean extension and integration.
- Secure by design direction: JWT auth, role-aware user management, and security hardening checklist.
- Flexible deployment: local development and multi-service container deployment via Docker Compose.
- Scalable foundation: PostgreSQL-backed data model with room for vector extensions and enterprise deployment patterns.

## Quickstart

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose)
- Node.js 20+
- Python 3.11+

### Option 1: Run with Docker Compose (recommended)

1. Clone the repository:

```bash
git clone https://github.com/Karthik-Git763/Personal-AI-Knowledge-Assistant.git
cd Personal-AI-Knowledge-Assistant
```

2. Start services:

```bash
docker compose up --build
```

3. Open the application:

- Frontend: http://localhost:8080
- Backend API: http://localhost:3000
- API docs: http://localhost:3000/docs

4. Stop services:

```bash
docker compose down
```

### Option 2: Run backend and frontend locally

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Frontend (new terminal, repository root):

```bash
pnpm install
pnpm dev
```

Then open http://localhost:8080.

## Development Notes

- Environment variables are read from `.env` and `.env.docker` depending on run mode.
- Current implementation includes core auth/data models with additional feature modules in progress.

## Contributing

Contributions are welcome.

1. Fork this repository
2. Create a feature branch
3. Commit your changes with clear messages
4. Open a pull request describing scope, rationale, and test coverage

## Architecture

- Frontend: Next.js App Router with React and TypeScript
- Backend: FastAPI with SQLModel and Pydantic
- Database: PostgreSQL
- AI pipeline (in progress): embeddings, vector store, retrieval, and chat orchestration

## Project Structure

- `app/`: Next.js application routes
- `components/`: UI and feature components
- `backend/`: FastAPI application, models, services, and API routes
- `lib/`: frontend utilities, hooks, and API client helpers
- `store/`: Zustand state stores
- `types/`: shared TypeScript types

<!-- ## License -->
