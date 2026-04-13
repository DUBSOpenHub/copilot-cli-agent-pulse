/**
 * SparklinePanel Component - Sparkline charts for activity over time
 */

import React from 'react';
import { Box, Text } from 'ink';
import Gradient from 'ink-gradient';

const e = React.createElement;

// Characters for sparkline rendering (low to high)
const SPARK_CHARS = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];

// Render a sparkline from data array
function renderSparkline(data, width = 40) {
  if (!data || data.length === 0) {
    return '░'.repeat(width);
  }
  
  const normalizedData = data.slice(-width);
  const min = Math.min(...normalizedData);
  const max = Math.max(...normalizedData);
  const range = max - min || 1;
  
  return normalizedData.map(v => {
    const normalized = (v - min) / range;
    const index = Math.floor(normalized * (SPARK_CHARS.length - 1));
    return SPARK_CHARS[Math.max(0, Math.min(index, SPARK_CHARS.length - 1))];
  }).join('');
}

// Individual sparkline with label
function Sparkline({ label, data, color, gradient, emoji }) {
  const sparkline = renderSparkline(data, 50);
  const current = data.length > 0 ? data[data.length - 1] : 0;
  const avg = data.length > 0 ? Math.round(data.reduce((a, b) => a + b, 0) / data.length) : 0;
  const max = data.length > 0 ? Math.max(...data) : 0;
  
  return e(Box, { marginBottom: 1 },
    e(Box, { width: 18 },
      e(Text, { color, bold: true }, emoji + ' ' + label)
    ),
    e(Box, { width: 52 },
      e(Gradient, { name: gradient },
        e(Text, null, sparkline)
      )
    ),
    e(Box, { width: 25 },
      e(Text, { color: 'gray' }, 'now:'),
      e(Text, { color }, String(current).padStart(3)),
      e(Text, { color: 'gray' }, ' avg:'),
      e(Text, { color: 'gray' }, String(avg).padStart(3)),
      e(Text, { color: 'gray' }, ' max:'),
      e(Text, { color: 'white' }, String(max).padStart(3))
    )
  );
}

// Generate demo data if history is empty
function generateDemoData(length = 50) {
  const data = [];
  let value = Math.random() * 3;
  for (let i = 0; i < length; i++) {
    value += (Math.random() - 0.5) * 2;
    value = Math.max(0, Math.min(10, value));
    data.push(Math.round(value));
  }
  return data;
}

export default function SparklinePanel({ history, getSparkline }) {
  // Get sparkline data for each metric
  const sessionsData = getSparkline ? getSparkline('sessions', 50) : [];
  const agentsData = getSparkline ? getSparkline('agents', 50) : [];
  const subAgentsData = getSparkline ? getSparkline('subAgents', 50) : [];
  
  // If no data, show placeholder or demo data
  const sessions = sessionsData.length > 5 ? sessionsData : generateDemoData();
  const agents = agentsData.length > 5 ? agentsData : generateDemoData();
  const subAgents = subAgentsData.length > 5 ? subAgentsData : generateDemoData();
  
  return e(Box, { flexDirection: 'column', borderStyle: 'round', borderColor: 'cyan', padding: 1, marginBottom: 1 },
    e(Box, { justifyContent: 'center', marginBottom: 1 },
      e(Gradient, { name: 'teen' },
        e(Text, { bold: true }, ' 📈 ACTIVITY SPARKLINES (Last Hour) ')
      )
    ),
    e(Sparkline, { label: 'Sessions', data: sessions, color: 'green', gradient: 'mind', emoji: '🖥️' }),
    e(Sparkline, { label: 'Agents', data: agents, color: 'cyan', gradient: 'cristal', emoji: '🤖' }),
    e(Sparkline, { label: 'Sub-Agents', data: subAgents, color: 'magenta', gradient: 'passion', emoji: '🔄' }),
    e(Box, { justifyContent: 'center', marginTop: 1 },
      e(Text, { color: 'gray', dimColor: true }, '▁ low │ ▄ medium │ █ high')
    )
  );
}
