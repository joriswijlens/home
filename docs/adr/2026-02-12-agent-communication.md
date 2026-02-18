# Agent Communication

## Context

We need a two-way chat interface with the autonomous AI agent accessible from phone and laptop. The solution must be privacy-respecting and self-hosted, aligning with the project's principles.

**Requirements:**
- Access from phone and laptop browsers
- No third-party messaging services
- Privacy-focused and self-hosted
- Works with existing WireGuard VPN
- Supports future multi-agent scenarios
- Low infrastructure overhead

**Discarded alternatives:**
- **Signal**: Requires a second SIM card for the agent, complex setup
- **Telegram**: Russian-owned, privacy concerns, third-party dependency
- **Matrix**: Too heavy for Pi 3, overkill for single-user chat
- **Third-party services**: Conflicts with self-hosted privacy requirements

## Decision

We will implement a Progressive Web App (PWA) web chat served by the agent's FastAPI backend, accessed via WireGuard VPN. MQTT (existing Mosquitto on Mars) serves as the group chat backbone for inter-agent communication.

**Architecture:**
- **User interface**: PWA web chat (`apps/webchat/`)
- **Backend**: FastAPI serving the PWA and WebSocket API
- **Message backbone**: MQTT on Mars (existing Mosquitto broker)
- **Access method**: WireGuard VPN (already deployed)
- **Future bots**: Subscribe to MQTT topics to join conversations

**Communication flow:**
1. User accesses PWA via `https://venus.home:8080` (through WireGuard)
2. PWA connects to FastAPI WebSocket endpoint
3. FastAPI publishes user messages to MQTT topic
4. Agent subscribes to MQTT, processes messages, publishes responses
5. FastAPI forwards agent responses to PWA via WebSocket
6. Future agents join by subscribing to same MQTT topics

**Technical details:**
- MQTT topics: `minion/chat/user`, `minion/chat/agent`, `minion/chat/system`
- FastAPI handles WebSocket connections and MQTT bridge
- PWA uses modern browser APIs (installable, offline capable)
- All traffic secured by WireGuard VPN

## Consequences

**Positive:**
- No third-party messaging dependency - fully self-hosted
- Works on any device with a browser (phone, laptop, tablet)
- Zero additional infrastructure (uses existing MQTT and WireGuard)
- Future multi-agent group chat built-in via MQTT topics
- PWA provides app-like experience (installable, works offline)
- Privacy-respecting - all data stays on home network
- Low resource overhead on Pi 3

**Negative:**
- No push notifications (must check actively for new messages)
- Requires WireGuard connection for access (not accessible outside VPN)
- Manual browser access (not as seamless as native messaging app)
- WebSocket connection drops when browser closes

**Neutral:**
- Need to implement WebSocket reconnection logic in PWA
- MQTT message persistence depends on broker configuration
- Future feature: push notifications via Progressive Web App APIs
