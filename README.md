# Agent-bridge
use for communication between different AI agent

## Contents

- `docs/grok-email-bridge.md`: how the Kalshi platform and a Grok bot talk over email (`[KTASK id]` tasks, reply format, Gmail setup).
- `inbox_agent/`: reads Grok's replies, checks the X links and source trust, and publishes observations. See `inbox_agent/README.md`.
