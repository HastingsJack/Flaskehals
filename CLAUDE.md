# CLAUDE.md

## Project
PR Review Assistant is a Python application that helps teams understand pull request activity, developer workload, and reviewer allocation.

The goal is to explore how GitHub data, graph modelling, and AI-supported recommendations can improve code review workflows.

## Tech Stack
- Python
- Streamlit
- Neo4j
- GitHub API and webhooks
- LLM integration
- pytest

## Architecture
- Keep UI, business logic, integrations, and database access separate.
- Prefer simple, maintainable solutions over unnecessary abstractions.
- Use type hints and write testable code.
- Keep business logic independent of Streamlit where practical.

## Development Workflow
1. Read the relevant Gherkin feature file and inspect the existing code.
2. Identify ambiguities and propose an implementation plan.
3. Wait for approval before substantial implementation.
4. Implement only what is required by the feature.
5. Add or update tests and run them.
6. Summarise changes, test results, and remaining issues.

Do not silently change feature requirements or implement unrelated functionality.

## Project Conventions
- Gherkin files in `features/` define expected behaviour.
- Tests belong in `tests/`.
- Keep configuration in environment variables.
- Never commit secrets or `.env` files.
- Keep `.env.example` updated when configuration changes.
- Use pytest for automated tests.

## GitHub & Neo4j
- Start with read-only GitHub access where possible.
- Handle API errors and rate limits.
- Use Neo4j for meaningful relationships between developers, PRs, files, reviews, and technologies.
- Avoid storing data in Neo4j when a simpler solution is sufficient.

## Recommendations & AI
- Reviewer rankings must be deterministic and explainable.
- Consider expertise, review history, workload, and availability.
- Use the LLM primarily for explanations and assistance, not as the sole source of ranking decisions.
- Base AI responses on retrieved project data.

## Security
- Follow least-privilege access.
- Never expose credentials or secrets.
- Validate external input.
- Fail securely when required configuration is missing.

## Code Style
This is a datamatiker final project, so the code must stay simple and easy to read.
- Follow DRY, SOLID and KISS: no duplicated logic, one responsibility per module, no clever or over-engineered solutions.
- Write only comments that explain why, never what. Keep docstrings short and skip them when the name says it all.
- Do not add tests that only restate the implementation or mock data. Test behaviour from the Gherkin files.

## General
- Avoid unnecessary dependencies and complexity.
- Follow existing project conventions.
- Explain important technical decisions so they can be understood and justified.
- Ask before making significant architectural changes.