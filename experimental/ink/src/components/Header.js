/**
 * Header Component - Gradient ASCII art title with pulse animation
 */

import React from 'react';
import { Box, Text } from 'ink';
import Gradient from 'ink-gradient';
import { usePulse } from '../hooks/useScanner.js';

const e = React.createElement;

// ASCII art for "AGENT PULSE"
const ASCII_ART = `
   █████╗  ██████╗ ███████╗███╗   ██╗████████╗    ██████╗ ██╗   ██╗██╗     ███████╗███████╗
  ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝    ██╔══██╗██║   ██║██║     ██╔════╝██╔════╝
  ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║       ██████╔╝██║   ██║██║     ███████╗█████╗  
  ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║       ██╔═══╝ ██║   ██║██║     ╚════██║██╔══╝  
  ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║       ██║     ╚██████╔╝███████╗███████║███████╗
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝       ╚═╝      ╚═════╝ ╚══════╝╚══════╝╚══════╝
`.trim();

// Pulse animation frames
const GRADIENT_FRAMES = ['rainbow', 'cristal', 'teen', 'mind', 'morning', 'vice', 'passion', 'fruit', 'instagram', 'atlas'];
const PULSE_CHARS = ['◉', '◎', '○', '◎'];

export default function Header({ isActive }) {
  const frame = usePulse(300);
  const gradientName = GRADIENT_FRAMES[frame % GRADIENT_FRAMES.length];
  const pulseChar = PULSE_CHARS[Math.floor(frame / 2) % PULSE_CHARS.length];
  
  return e(Box, { flexDirection: 'column', alignItems: 'center', marginBottom: 1 },
    e(Gradient, { name: gradientName }, e(Text, null, ASCII_ART)),
    e(Box, { marginTop: 1 },
      e(Text, { color: isActive ? 'green' : 'yellow' }, pulseChar + ' ' + (isActive ? 'LIVE MONITORING' : 'SCANNING...') + ' ' + pulseChar),
      e(Text, { color: 'gray' }, ' │ '),
      e(Text, { color: 'cyan' }, 'GitHub Copilot CLI Agent Tracker'),
      e(Text, { color: 'gray' }, ' │ '),
      e(Text, { color: 'magenta' }, 'Havoc Hackathon #51')
    ),
    e(Box, null, e(Text, { color: 'gray' }, '─'.repeat(96)))
  );
}
