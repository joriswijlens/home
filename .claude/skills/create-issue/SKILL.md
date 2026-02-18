---
name: create-issue
description: Create or update a GitHub issue with clarifying questions
allowed-tools: Bash, Read, Glob, Grep, WebSearch, AskUserQuestion
---

Create or update a GitHub issue. **Do NOT implement — only create/update the issue.**

## Mode

- Argument is a **number or URL** → update mode
- Otherwise → create mode

## Create

1. Get feature/bug/task description from user (argument or ask)
2. Explore codebase for context
3. Ask 2-4 clarifying questions via `AskUserQuestion` — keep it focused
4. Create with `gh issue create`

## Update

1. Fetch with `gh issue view <number>`
2. Clarify what to change if not obvious
3. Apply with `gh issue edit` or `gh issue comment` (comment for additions, edit for rewrites)
4. Summarize what changed before applying

## Issue Body Structure

```markdown
## Summary
[1-2 sentences — what and why]

## Context
[What exists today, why this change is needed]

## Requirements
- [ ] [Specific, verifiable requirement]

## Affected Areas
- [File paths or modules]

## Out of Scope
[What this does NOT cover]

## Acceptance Criteria
- [ ] [Concrete, testable criterion]
```

Omit sections that aren't relevant. Keep it tight.

## Rules

- Title: imperative, under 70 chars
- Add labels if they exist (`gh label list`)
- Be specific: file paths, concrete criteria, no vague language
- Show the issue URL when done
