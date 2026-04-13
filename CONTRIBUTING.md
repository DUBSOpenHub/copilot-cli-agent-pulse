# Contributing to Agent Pulse

Thanks for your interest in contributing! 🎉

## Quick Start

```bash
git clone https://github.com/DUBSOpenHub/copilot-cli-agent-pulse.git
cd copilot-cli-agent-pulse
pip install -r requirements.txt
python agent_pulse.py --live
```

## Guidelines

### Code Style
- Agent Pulse is a **single-file Python application**. Keep it that way unless explicitly changing the architecture.
- Use Rich for all TUI rendering.
- Wrap panel builders in try/except — a broken panel should never crash the dashboard.

### Pull Requests
1. Fork the repo and create a feature branch
2. Ensure `python agent_pulse.py --help` exits cleanly
3. Test both `--live` and snapshot modes
4. Keep the commit history clean
5. Describe what you changed and why

### What We're Looking For
- New dashboard panels or visualizations
- Performance improvements to data collection
- Better error handling and edge cases
- Linux platform support
- Documentation improvements

### What We're NOT Looking For
- Refactoring into a multi-file package (unless discussed first)
- Adding new Python dependencies
- Telemetry or analytics
- Changes that break existing CLI flags

## Code of Conduct

Be kind. Be constructive. We're all here to build cool things.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
