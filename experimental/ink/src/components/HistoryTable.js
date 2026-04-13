/**
 * HistoryTable Component - Daily/weekly/monthly/all-time stats table
 */

import React from 'react';
import { Box, Text } from 'ink';
import Gradient from 'ink-gradient';

const e = React.createElement;

// Format large numbers with K/M suffix
function formatNumber(n) {
  if (n >= 1000000) {
    return (n / 1000000).toFixed(1) + 'M';
  }
  if (n >= 1000) {
    return (n / 1000).toFixed(1) + 'K';
  }
  return String(n);
}

// Table cell with consistent width
function Cell({ children, width = 15, align = 'right', color }) {
  const content = String(children);
  const padded = align === 'right' 
    ? content.padStart(width - 2) 
    : content.padEnd(width - 2);
  
  return e(Box, { width },
    e(Text, { color }, padded)
  );
}

// Table row
function Row({ label, sessions, agents, subAgents, labelColor = 'white', highlight = false }) {
  return e(Box, null,
    e(Box, { width: 2 },
      e(Text, null, highlight ? '▶' : ' ')
    ),
    e(Cell, { width: 14, align: 'left', color: labelColor }, label),
    e(Text, { color: 'gray' }, '│'),
    e(Cell, { width: 12, color: 'green' }, formatNumber(sessions)),
    e(Text, { color: 'gray' }, '│'),
    e(Cell, { width: 12, color: 'cyan' }, formatNumber(agents)),
    e(Text, { color: 'gray' }, '│'),
    e(Cell, { width: 12, color: 'magenta' }, formatNumber(subAgents))
  );
}

// Table header
function TableHeader() {
  return e(React.Fragment, null,
    e(Box, null,
      e(Cell, { width: 16, align: 'left', color: 'white' }, 'Period'),
      e(Text, { color: 'gray' }, '│'),
      e(Cell, { width: 12, color: 'green' }, '🖥️ Sessions'),
      e(Text, { color: 'gray' }, '│'),
      e(Cell, { width: 12, color: 'cyan' }, '🤖 Agents'),
      e(Text, { color: 'gray' }, '│'),
      e(Cell, { width: 12, color: 'magenta' }, '🔄 Sub-Agents')
    ),
    e(Box, null,
      e(Text, { color: 'gray' }, '─'.repeat(16) + '┼' + '─'.repeat(12) + '┼' + '─'.repeat(12) + '┼' + '─'.repeat(12))
    )
  );
}

export default function HistoryTable({ stats }) {
  if (!stats) {
    return e(Box, { flexDirection: 'column', borderStyle: 'round', borderColor: 'yellow', padding: 1 },
      e(Text, { color: 'yellow' }, 'Loading historical data...')
    );
  }
  
  const { today, weekly, monthly, allTime } = stats;
  
  return e(Box, { flexDirection: 'column', borderStyle: 'round', borderColor: 'yellow', padding: 1, marginBottom: 1 },
    e(Box, { justifyContent: 'center', marginBottom: 1 },
      e(Gradient, { name: 'morning' },
        e(Text, { bold: true }, ' 📅 HISTORICAL USAGE STATS ')
      )
    ),
    e(TableHeader),
    e(Row, { label: '📆 Today', sessions: today?.sessions || 0, agents: today?.agents || 0, subAgents: today?.subAgents || 0, labelColor: 'greenBright', highlight: true }),
    e(Row, { label: '📅 This Week', sessions: weekly?.sessions || 0, agents: weekly?.agents || 0, subAgents: weekly?.subAgents || 0, labelColor: 'cyanBright' }),
    e(Row, { label: '🗓️  This Month', sessions: monthly?.sessions || 0, agents: monthly?.agents || 0, subAgents: monthly?.subAgents || 0, labelColor: 'yellowBright' }),
    e(Box, null,
      e(Text, { color: 'gray' }, '─'.repeat(16) + '┼' + '─'.repeat(12) + '┼' + '─'.repeat(12) + '┼' + '─'.repeat(12))
    ),
    e(Row, { label: '🏆 All Time', sessions: allTime?.totalSessions || 0, agents: allTime?.totalAgents || 0, subAgents: allTime?.totalSubAgents || 0, labelColor: 'magentaBright' }),
    e(Box, { marginTop: 1 },
      e(Text, { color: 'gray' }, 'Peak concurrent: Sessions=' + (allTime?.peakConcurrentSessions || 0) + ' │ Agents=' + (allTime?.peakConcurrentAgents || 0))
    ),
    allTime?.firstSeen && e(Box, null,
      e(Text, { color: 'gray', dimColor: true }, 'Tracking since: ' + new Date(allTime.firstSeen).toLocaleDateString())
    )
  );
}
