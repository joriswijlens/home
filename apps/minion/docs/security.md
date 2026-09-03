# Security

What is protected, what is not, and in which order to close the gaps. Recorded
2026-09-02, while the priority was getting the principle working end to end.

## What holds today

Webhook endpoints (`/hooks/<source>`) are built for being reachable from outside, not
only from the LAN:

| Attack | Response |
|---|---|
| No credential | 401 — a source without a secret refuses to register at all |
| Wrong secret | 401, compared in constant time |
| Body altered in flight | 401 — the signature covers the body |
| Request replayed | 401 — timestamp is signed, plus a seen-signature cache |
| Captured request used later | 401 — outside the 5 minute skew window |
| Flooding to drain the budget | 429, rate limited per source |
| Oversized POST | 413, refused before parsing |

Default is an HMAC over `timestamp.body`, so the secret never travels. Bearer auth is
opt-in per source and only appropriate for LAN senders that cannot sign. Secrets come
from the environment, never a committed file. TLS is a reverse proxy's job.

Spend has its own bounds: one run at a time, a hard per-run timeout, a rolling 24h
token budget checked before claiming, and bounded retries.

## What does not hold

**The transport is secured; the agent's execution environment is not.** In rough order
of severity:

### 1. `ShellTool` is unrestricted execution on the host

`create_subprocess_shell(command)` with no allowlist, no working-directory limit, and
the parent process environment inherited. So `env` prints `GITHUB_TOKEN` and the
Anthropic key, `cat ~/.ssh/id_*` reads the deploy key, and `curl` sends either
anywhere. `allowed_paths` constrains only the file tools — it reads like a sandbox and
is not one.

### 2. Untrusted text reaches that shell

`joriswijlens/home` is public, so anyone can open an issue, and the body goes
unfiltered into the plan prompt. The same will hold for Grafana and Home Assistant
payloads. The only gate is a human applying the label — which makes one pair of eyes
the entire boundary, against text written to look ordinary. Untrusted input, access to
secrets, and an outbound channel is the combination that matters.

### 3. The container runs as root on the host network

No `USER` in the Dockerfile, `network_mode: host`, and `GITHUB_TOKEN` passed into the
environment.

### 4. The path check is bypassable

`str(resolved).startswith(str(allowed))` lets `/opt/smartworkx-evil` through an
allowlist of `/opt/smartworkx`. Should compare path components (`is_relative_to`).

### 5. Secrets can reach Loki

The shell command is logged verbatim, tool inputs are logged, and event payloads go to
stdout as JSON — all of which ships to Jupiter.

## Order to fix

| Fix | Why this order |
|---|---|
| `is_relative_to` in the path check | Unambiguous bug, two lines, no design decision |
| A scrubbed environment for tools | Small, and removes most of the exfiltration value |
| Command allowlist per flow | Needs a decision: read-only (`git`, `gh`) or build and test commands too |
| Non-root user, `GITHUB_TOKEN` out of the agent environment | Use a git credential helper rather than a token in the process |
| Per-run subprocess with a memory cap and no network unless required | The actual fence; the largest piece of work |

Prompt-level mitigation — delimiting provider text and telling the model it is
untrusted — is hygiene, not a control. It belongs alongside the list above, never
instead of it.
