# Docs-as-Code

https://www.writethedocs.org/guide/docs-as-code/

One of the drivers for this is [AI-Assisted Development](ai-assisted-development.md) for the foundational principles that apply to any project.

> **Actor** — a developer or an AI agent. The principles, workflows, and structures in this document apply equally to both. An actor picks up an issue, opens a workspace, reads the standing docs, and delivers work.

**Legend:**  ✅ Exists  |  🗺️ Roadmap

## Principles — Applied

- **Single source of truth in version control** — standing docs (session reports, post-mortems, architecture docs) live in Git. Issues *reference* them, never duplicate. If it's not in the repo, it's not authoritative.
- **Docs as close to code as possible** — all docs live in the same monorepo as the code they describe. Proximity is context.
- **Reviewed like code** — all doc changes go through branches and pull requests. The PR diff shows exactly what changed in the architecture or contract. PR links from issues give actors the full evolution. 
- **Validated in CI** — linting, template compliance, link checking, and diagram syntax validation run automatically. Broken or incomplete docs don't reach the main branch.
- **Skills encode best practices** — repeatable workflows are codified as skills that live in the repo. The skill *is* the best practice — executable, versioned, reviewed. New actors follow team standards from the first invocation.
- **Issues provide focus** — a GitHub Issue describes *what* to do and *why*, scoping the actor's work. Standing docs provide the *how* and *constraints*. The issue focuses, the repo gives context.
- **Domain-driven structure** — subdomains and bounded contexts define the landscape. Each bounded context maps to a directory in the monorepo. Architecture models visualize the system with links between components. The domain model is the map.

## Formats and Notation Methods

### Spec Inputs (humans write)

| Format | Purpose | Notation | Status |
|--------|---------|----------|--------|
| **GitHub Issues** | What to build, acceptance criteria, scope | Markdown | ✅ |
| **Domain model** | Entities, relationships, ubiquitous language | Markdown tables, Mermaid diagrams | ✅ Partial |
| **Behavior specs** | What the system does — scenarios with expected outcomes | Gherkin (`.feature`) | 🗺️ |
| **Architecture decisions** | Why choices were made — immutable, append-only | Nygard ADR | ✅ |
| **Architecture models** | System structure at increasing zoom levels | C4 Model (Mermaid) | 🗺️ |
| **External contracts** | Third-party APIs and integrations we consume | Markdown with examples | ✅ Partial |

### Derived Outputs (AI generates)

| Output | Derived from |
|--------|-------------|
| Application code | Issues + domain model + CLAUDE.md constraints |
| Tests (unit + e2e) | Issue scenarios, edge cases |
| Internal API contracts | Issue scenarios + domain model |
| Database schema | Domain model + existing conventions |
| Infrastructure (Terraform) | Architecture constraints + parameters |
| GitHub Actions workflows | Deployment requirements |
| Session reports | Work performed during a session |

### Repo Artifacts

| Format | Purpose | Lives in | Lifecycle | Status |
|--------|---------|----------|-----------|--------|
| **CLAUDE.md** | Agent context — architecture, conventions, constraints | Repo root | Persistent | ✅ |
| **Session reports** | What was done, findings, decisions, next steps | `doc/sessions/` | Persistent | ✅ |
| **Post-mortems** | Incident analysis and root causes | `doc/post-mortems/` | Persistent | ✅ |
| **Markdown** (`.md`) | All prose documentation | `doc/`, `apps/*/` | Persistent | ✅ |
| **Skills** | Codified best practices as executable commands | `.claude/skills/` | Persistent | ✅ |
| **Agents** | Specialized agent configurations with memory | `.claude/agents/` | Persistent | ✅ |
| **ADR** (Nygard) | Architecture decisions — immutable, append-only | `doc/adr/` | Immutable | ✅ |
| **Gherkin** (`.feature`) | Executable behavior specs | `doc/specs/` | Living | 🗺️ |
| **Mermaid** | Diagrams as code — rendered natively by GitHub | Inline in `.md` files | Persistent | ✅ |
| **C4 Model** (Mermaid flowcharts) | Architecture at 4 zoom levels | Inline in `doc/domain-model.md` | Persistent | ✅ Partial |

### Diagrams

Mermaid diagrams are authored as inline fenced code blocks — GitHub renders them natively.

- **Single use** — inline the diagram in the document that needs it. No separate file.
- **Multiple references** — place the diagram in its own file under `doc/diagrams/` and link to it from each consumer. The diagram file is the single source of truth.

