/**
 * AgentTypeBreakdown Component - Colored bars per agent type
 */

import React from 'react';
import { Box, Text } from 'ink';
import Gradient from 'ink-gradient';

const e = React.createElement;

// Agent type configuration with colors and emojis
const AGENT_TYPES = {
  'task': { emoji: '⚡', color: 'yellow', gradient: 'morning', label: 'Task Agents' },
  'explore': { emoji: '🔍', color: 'blue', gradient: 'atlas', label: 'Explore Agents' },
  'general-purpose': { emoji: '🎯', color: 'green', gradient: 'mind', label: 'General Purpose' },
  'rubber-duck': { emoji: '🦆', color: 'yellow', gradient: 'fruit', label: 'Rubber Duck' },
  'code-review': { emoji: '📝', color: 'magenta', gradient: 'passion', label: 'Code Review' },
  'custom': { emoji: '🎨', color: 'cyan', gradient: 'cristal', label: 'Custom Agents' }
};

// Horizontal bar renderer
function AgentBar({ type, count, maxCount }) {
  const config = AGENT_TYPES[type] || { emoji: '❓', color: 'gray', gradient: 'rainbow', label: type };
  const barWidth = maxCount > 0 ? Math.floor((count / maxCount) * 30) : 0;
  const bar = '█'.repeat(barWidth) + '░'.repeat(30 - barWidth);
  
  return e(Box, null,
    e(Box, { width: 20 },
      e(Text, { color: config.color }, config.emoji + ' ' + config.label)
    ),
    e(Box, { width: 35 },
      e(Gradient, { name: config.gradient },
        e(Text, null, bar)
      )
    ),
    e(Box, { width: 8, justifyContent: 'flex-end' },
      e(Text, { color: config.color, bold: true }, String(count).padStart(3, ' '))
    )
  );
}

// Mini chart summary
function MiniChart({ breakdown }) {
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  if (total === 0) {
    return e(Box, { flexDirection: 'column', alignItems: 'center' },
      e(Text, { color: 'gray' }, '   ╭───╮'),
      e(Text, { color: 'gray' }, '   │ 0 │'),
      e(Text, { color: 'gray' }, '   ╰───╯'),
      e(Text, { color: 'gray' }, 'No agents')
    );
  }
  
  const segments = Object.entries(breakdown)
    .filter(([_, count]) => count > 0)
    .map(([type, count]) => ({ type, count, config: AGENT_TYPES[type] }));
  
  return e(Box, { flexDirection: 'column', alignItems: 'center' },
    e(Text, { color: 'white', bold: true }, 'Distribution'),
    e(Box, { marginY: 1 },
      ...segments.map((s, i) => 
        e(Text, { key: i, color: s.config?.color || 'gray' }, 
          (s.config?.emoji || '?') + (s.count > 1 ? s.count : ''))
      )
    ),
    e(Text, { color: 'gray' }, 'Total: ' + total)
  );
}

export default function AgentTypeBreakdown({ breakdown }) {
  const maxCount = Math.max(...Object.values(breakdown), 1);
  const totalAgents = Object.values(breakdown).reduce((a, b) => a + b, 0);
  
  return e(Box, { flexDirection: 'column', borderStyle: 'round', borderColor: 'blue', padding: 1, marginBottom: 1 },
    e(Box, { justifyContent: 'center', marginBottom: 1 },
      e(Gradient, { name: 'rainbow' },
        e(Text, { bold: true }, ' 🤖 AGENT TYPE BREAKDOWN ')
      )
    ),
    e(Box, null,
      e(Box, { flexDirection: 'column', flexGrow: 1 },
        ...Object.keys(AGENT_TYPES).map(type =>
          e(AgentBar, { key: type, type, count: breakdown[type] || 0, maxCount })
        )
      ),
      e(Box, { flexDirection: 'column', alignItems: 'center', paddingX: 2, borderStyle: 'single', borderColor: 'gray', marginLeft: 2 },
        e(MiniChart, { breakdown }),
        e(Box, { marginTop: 1 },
          e(Text, { color: 'cyan', bold: true }, totalAgents + ' active')
        )
      )
    )
  );
}
