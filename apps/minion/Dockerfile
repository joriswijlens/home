FROM python:3.11-slim-bookworm AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

FROM python:3.11-slim-bookworm

# The agent backend: one static binary, arm64 for Venus, x64 for a laptop build.
ARG OPENCODE_VERSION=1.18.30
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && case "$TARGETARCH" in arm64) oc_arch=arm64 ;; *) oc_arch=x64 ;; esac \
    && curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${oc_arch}.tar.gz" \
       | tar -xz -C /usr/local/bin opencode \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

WORKDIR /app
COPY config/ config/
COPY src/ src/

EXPOSE 8080

CMD ["python", "-m", "minion"]
