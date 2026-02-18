# Autonomous AI Agent

## Context

We need an autonomous AI agent for software development tasks that can grow capabilities over time. The agent must run on existing Raspberry Pi 3 hardware (Venus, 1GB RAM) without requiring new infrastructure. The system must be privacy-focused and fully self-hosted, aligning with the zero emissions and self-sufficiency principles of this project.

Key requirements:
- Autonomous operation for development tasks (coding, infrastructure changes, documentation)
- Runs on resource-constrained Pi 3 hardware (1GB RAM)
- Scalable to multiple Raspberry Pis without duplicating codebases
- Self-hosted and privacy-respecting
- Low operational cost
- Can grow capabilities over time as new tools and integrations are added

## Decision

We will build a lightweight Python agent called "Minion" using the Anthropic API with tool use. The same `apps/minion` codebase will be deployable to any Raspberry Pi, with each instance getting its own identity via environment configuration (e.g., `AGENT_NAME=venus`). Version 1 starts on Venus.

**Architecture:**
- **Agent runtime**: Python application with Anthropic SDK
- **API approach**: Direct Anthropic API calls with tool use (not Agent SDK)
- **Communication**: MQTT for inter-agent messaging, FastAPI for web interface
- **Deployment**: Docker container, same pattern as other services
- **Hosting**: Venus (Pi 3, 1GB RAM) for V1
- **Identity**: Per-instance config allows same code to run on multiple Pis

**Rationale:**
- Anthropic API with tool use provides full control and transparency
- No local model needed - cloud API works on 1GB RAM
- Python ecosystem rich with tools for git, file ops, shell execution
- MQTT backbone enables future multi-agent group chat
- Reusable codebase scales horizontally by deploying more instances
- Low cost (~$3-15/month API usage based on moderate daily use)

**Discarded alternatives:**
- Agent SDK: Too opaque, limited control over tool implementation
- Local models: Require more RAM than Pi 3 provides
- Jupiter hosting: Venus is available and sufficient for V1
- Complex frameworks: Overkill for initial needs

## Consequences

**Positive:**
- Zero new hardware required - uses existing Venus Pi
- Low operational cost (~$3-15/month API)
- Full control over tool implementation and agent behavior
- Self-hosted messaging and communication
- Horizontal scaling: deploy same codebase to any Pi with different config
- Each Pi can have different capabilities via environment config
- Async task processing via MQTT
- Future multi-agent scenarios built-in (all instances join same MQTT group chat)

**Negative:**
- Requires internet connectivity for API calls
- Dependency on Anthropic API availability
- Need to implement tool execution layer manually
- API costs scale with usage (mitigated by monitoring)

**Neutral:**
- Each agent instance needs its own API key configured
- Learning curve for Anthropic API and tool use patterns
- Manual deployment and monitoring initially (can automate later)
