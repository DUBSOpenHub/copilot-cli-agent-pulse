#!/usr/bin/env node

/**
 * Agent Pulse - Entry Point
 * Real-time agent tracking dashboard for GitHub Copilot CLI
 * 
 * Havoc Hackathon #51 - Contestant E
 * 
 * Usage:
 *   npm start
 *   node src/index.js
 *   npx agent-pulse
 */

import React from 'react';
import { render } from 'ink';
import AgentPulse from './components/AgentPulse.js';

// ASCII art startup banner
const STARTUP_BANNER = `
╔═══════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                                   ║
║     █████╗  ██████╗ ███████╗███╗   ██╗████████╗    ██████╗ ██╗   ██╗██╗     ███████╗███████╗     ║
║    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝    ██╔══██╗██║   ██║██║     ██╔════╝██╔════╝     ║
║    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║       ██████╔╝██║   ██║██║     ███████╗█████╗       ║
║    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║       ██╔═══╝ ██║   ██║██║     ╚════██║██╔══╝       ║
║    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║       ██║     ╚██████╔╝███████╗███████║███████╗     ║
║    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝       ╚═╝      ╚═════╝ ╚══════╝╚══════╝╚══════╝     ║
║                                                                                                   ║
║                   Real-time Agent Tracking Dashboard for GitHub Copilot CLI                       ║
║                                                                                                   ║
║                              🏆 Havoc Hackathon #51 │ Contestant E 🏆                             ║
║                                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════════════════════╝
`;

// Print startup banner
console.log('\x1b[36m%s\x1b[0m', STARTUP_BANNER);
console.log('\x1b[33m%s\x1b[0m', '  ⚡ Initializing Agent Pulse...\n');

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n\x1b[32m%s\x1b[0m', '  👋 Agent Pulse shutting down gracefully...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\n\x1b[32m%s\x1b[0m', '  👋 Agent Pulse terminated.');
  process.exit(0);
});

// Render the app
const { waitUntilExit } = render(React.createElement(AgentPulse));

// Wait for exit
waitUntilExit().then(() => {
  console.log('\x1b[32m%s\x1b[0m', '\n  ✅ Agent Pulse has exited. Goodbye!\n');
});
