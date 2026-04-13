# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | ✅         |

## Reporting a Vulnerability

If you discover a security vulnerability in Agent Pulse, please report it responsibly:

1. **Do NOT** open a public issue
2. Email the maintainers or use [GitHub Security Advisories](https://github.com/DUBSOpenHub/copilot-cli-agent-pulse/security/advisories/new)
3. Include a description of the vulnerability and steps to reproduce

## Security Considerations

Agent Pulse is a **read-only monitoring tool**. It:

- Reads process information via `ps aux`
- Reads the Copilot CLI session store (`~/.copilot/session-store.db`) in read-only mode
- Reads session event files from `~/.copilot/session-state/`
- Writes only to its own history file at `~/.copilot/agent-pulse/history.json`

It does **not**:

- Send data to any external service
- Modify Copilot CLI state or configuration
- Access any network resources
- Store or transmit credentials

## Dependencies

- **Python**: `rich>=13.0.0` (MIT licensed)
- No network-dependent packages
