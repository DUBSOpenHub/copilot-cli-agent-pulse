/**
 * LiveMetrics Component - Big number displays for sessions/agents/sub-agents
 */

import React from 'react';
import { Box, Text } from 'ink';
import Gradient from 'ink-gradient';

const e = React.createElement;

// Trend indicator
function TrendIndicator({ current, previous }) {
  if (current > previous) {
    return e(Text, { color: 'green' }, '▲ +' + (current - previous));
  } else if (current < previous) {
    return e(Text, { color: 'red' }, '▼ -' + (previous - current));
  }
  return e(Text, { color: 'gray' }, '━ 0');
}

export default function LiveMetrics({ data, previousData }) {
  const { sessions, agents, subAgents } = data;
  const prev = previousData || { sessions: { count: 0 }, agents: { count: 0 }, subAgents: { count: 0 } };
  
  return e(Box, { flexDirection: 'column', marginBottom: 1 },
    e(Box, { justifyContent: 'center', marginBottom: 1 },
      e(Text, { color: 'white', bold: true }, ' 📊 LIVE METRICS ')
    ),
    e(Box, { justifyContent: 'space-around' },
      // Sessions box
      e(Box, { flexDirection: 'column', alignItems: 'center', borderStyle: 'round', borderColor: 'green', paddingX: 4, paddingY: 1 },
        e(Text, { color: 'green', bold: true }, '🖥️  ACTIVE SESSIONS'),
        e(Box, { marginY: 1 },
          e(Text, { color: 'greenBright', bold: true }, '█'.repeat(Math.min(sessions.count * 3, 15)) || '░')
        ),
        e(Gradient, { name: 'mind' },
          e(Text, { bold: true }, '[ ' + String(sessions.count).padStart(3, ' ') + ' ]')
        ),
        e(TrendIndicator, { current: sessions.count, previous: prev.sessions?.count || 0 })
      ),
      // Agents box
      e(Box, { flexDirection: 'column', alignItems: 'center', borderStyle: 'round', borderColor: 'cyan', paddingX: 4, paddingY: 1 },
        e(Text, { color: 'cyan', bold: true }, '🤖 RUNNING AGENTS'),
        e(Box, { marginY: 1 },
          e(Text, { color: 'cyanBright', bold: true }, '█'.repeat(Math.min(agents.count * 2, 15)) || '░')
        ),
        e(Gradient, { name: 'cristal' },
          e(Text, { bold: true }, '[ ' + String(agents.count).padStart(3, ' ') + ' ]')
        ),
        e(TrendIndicator, { current: agents.count, previous: prev.agents?.count || 0 })
      ),
      // Sub-Agents box
      e(Box, { flexDirection: 'column', alignItems: 'center', borderStyle: 'round', borderColor: 'magenta', paddingX: 4, paddingY: 1 },
        e(Text, { color: 'magenta', bold: true }, '🔄 TOTAL SUB-AGENTS'),
        e(Box, { marginY: 1 },
          e(Text, { color: 'magentaBright', bold: true }, '█'.repeat(Math.min(Math.floor(subAgents.count / 5), 15)) || '░')
        ),
        e(Gradient, { name: 'passion' },
          e(Text, { bold: true }, '[ ' + String(subAgents.count).padStart(3, ' ') + ' ]')
        ),
        e(TrendIndicator, { current: subAgents.count, previous: prev.subAgents?.count || 0 })
      )
    )
  );
}
