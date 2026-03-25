# CLAUDE.md

This file provides guidance for AI assistants working on the **permit-miner** repository.

## Project Overview

**permit-miner** is a new project. The repository is currently in its initial setup phase with no source code yet committed. This document should be updated as the codebase evolves.

## Repository Structure

```
permit-miner/
├── CLAUDE.md          # AI assistant guidance (this file)
└── (empty)            # No source code yet
```

> **Note:** Update this section as files and directories are added.

## Development Workflow

### Branch Strategy

- The default branch is `main`.
- Feature branches should be created off `main` and merged via pull requests.
- Branch naming convention: `<type>/<short-description>` (e.g., `feat/add-parser`, `fix/handle-null-permits`).

### Commit Messages

- Use clear, concise commit messages that describe the "why" not just the "what".
- Prefix with a category when applicable: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

### Getting Started

```bash
git clone https://github.com/hfscdogg/permit-miner.git
cd permit-miner
```

> **Note:** Add setup instructions (dependencies, environment variables, build steps) once the tech stack is chosen.

## Key Conventions

- Keep code simple and focused; avoid over-engineering.
- Write tests alongside new features.
- Do not commit secrets, credentials, or `.env` files.

## AI Assistant Guidelines

- **Read before editing.** Always read a file before modifying it.
- **Minimal changes.** Only change what is requested; do not refactor surrounding code unprompted.
- **Test your work.** Run any available tests after making changes.
- **Update this file.** When adding significant new structure, dependencies, or workflows, update this CLAUDE.md to keep it current.
- **No guessing.** If the codebase does not yet have enough context to answer a question, say so rather than speculating.
