# Contributing Guide

Thank you for taking the time to contribute. This document outlines the process and standards we expect contributors to follow.

---

## Table of Contents

- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Branch Naming](#branch-naming)
- [Commit Messages](#commit-messages)
- [Pull Requests](#pull-requests)
- [Code Style](#code-style)
- [Documentation](#documentation)
- [Reporting Issues](#reporting-issues)

---

## Getting Started

1. **Fork** the repository to your own GitHub account.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/crypto-autonomous-portfolio-management.git
   cd crypto-autonomous-portfolio-management
   ```
3. Add the upstream remote so you can stay in sync:
   ```bash
   git remote add upstream https://github.com/<org>/crypto-autonomous-portfolio-management.git
   ```
4. Install dependencies and set up the project following the instructions in [README.md](./README.md).

---

## How to Contribute

- **Bug fixes**, **new features**, **documentation improvements**, and **research notes** are all welcome.
- Before starting significant work, open an **Issue** first to discuss the proposed change. This prevents duplicate effort and ensures the work fits the project direction.
- Keep each contribution focused on a single concern. Avoid bundling unrelated changes in one pull request.

---

## Branch Naming

Create a new branch from `main` for every contribution. Use the following naming conventions:

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<short-description>` | `feat/lstm-portfolio-agent` |
| Bug fix | `fix/<short-description>` | `fix/rebalance-calculation` |
| Documentation | `docs/<short-description>` | `docs/update-api-reference` |
| Research / analysis | `research/<short-description>` | `research/sharpe-ratio-study` |
| Refactor | `refactor/<short-description>` | `refactor/data-pipeline` |

---

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <short summary>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples:**
```
feat(agent): add PPO-based trading agent with risk constraints
fix(data): handle missing OHLCV values in preprocessing step
docs(contributing): add branch naming conventions
```

- Use the **imperative mood** in the summary ("add feature", not "added feature").
- Keep the summary line under **72 characters**.
- Reference related issues in the footer: `Closes #42`

---

## Pull Requests

1. Sync your branch with upstream before opening a PR:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```
2. Push your branch and **open a Pull Request** against `main`.
3. Fill in the PR template completely:
   - **What** does this PR do?
   - **Why** is this change needed?
   - **How** was it tested?
   - Link any related issues.
4. A PR must be reviewed and approved by **at least one** other team member before merging.
5. Address all review comments before requesting a re-review.
6. Squash or clean up commits if the reviewer requests it.
7. Do not merge your own PR without a review, except for trivial typo/doc fixes.

---

## Code Style

- Follow the existing code conventions of the language/framework in use.
- Run linters and formatters before committing. If a configuration file (`.eslintrc`, `pyproject.toml`, etc.) exists, adhere to it.
- Do not leave commented-out code or debug print statements in the final commit.
- Prefer descriptive variable and function names over terse abbreviations.
- Keep functions small and focused on a single responsibility.

---

## Documentation

Good documentation is treated as a first-class deliverable in this project.

- **Every public function, class, and module** must have a docstring or JSDoc comment explaining:
  - What it does
  - Parameters and their types
  - Return value and type
  - Any exceptions it may raise
- If you introduce a new concept, algorithm, or model, add a brief explanation in the relevant `docs/` directory.
- Update the `README.md` if your change affects setup steps, dependencies, or overall project structure.
- Research notes and experiment results should be stored under `docs/` with a clear filename and date.

---

## Reporting Issues

- Search existing issues before opening a new one.
- Provide a **clear title** and a **detailed description**.
- For bugs, include:
  - Steps to reproduce
  - Expected vs. actual behavior
  - Environment details (OS, language version, etc.)
- For feature requests, explain the motivation and the expected outcome.

---

We appreciate every contribution, big or small. When in doubt, open an issue and ask — communication is always welcome.
