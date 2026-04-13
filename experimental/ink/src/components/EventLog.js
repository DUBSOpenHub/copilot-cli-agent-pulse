/**
 * EventLog Component - Scrolling log of agent start/stop events
 */

import React from 'react';
import { Box, Text } from 'ink';
import Gradient from 'ink-gradient';

const e = React.createElement;

// Event type configuration
const EVENT_TYPES = {
  'session_started': { emoji: '🟢', color: 'green', label: 'Session Started' },
  'session_ended': { emoji: '🔴', color: 'red', label: 'Session Ended' },
  'agent_spawned': { emoji: '🚀', color: 'cyan', label: 'Agent Spawned' },
  'agent_completed': { emoji: '✅', color: 'green', label: 'Agent Completed' },
  'agent_error': { emoji: '❌', color: 'red', label: 'Agent Error' },
  'subagent_created': { emoji: '🔄', color: 'magenta', label: 'Sub-Agent Created' },
  'scan_complete': { emoji: '📡', color: 'blue', label: 'Scan Complete' }
};

// Format timestamp as relative time
function formatTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  
  if (diffSec < 60) {
    return diffSec + 's ago';
  } else if (diffMin < 60) {
    return diffMin + 'm ago';
  } else if (diffHour < 24) {
    return diffHour + 'h ago';
  }
  return date.toLocaleTimeString();
}

// Single event row
function EventRow({ event, index }) {
  const config = EVENT_TYPES[event.type] || { emoji: '❓', color: 'gray', label: event.type };
  const timeStr = formatTime(event.timestamp);
  const isRecent = (Date.now() - new Date(event.timestamp).getTime()) < 10000;
  
  let details = '';
  if (event.details?.count !== undefined) {
    details = 'count=' + event.details.count;
  }
  if (event.details?.breakdown) {
    const breakdown = Object.entries(event.details.breakdown)
      .filter(([k, v]) => v > 0)
      .map(([k, v]) => k + ':' + v)
      .join(', ');
    if (breakdown) details += ' [' + breakdown + ']';
  }
  
  return e(Box, null,
    e(Box, { width: 3 },
      e(Text, { color: 'gray', dimColor: true }, String(index + 1).padStart(2, '0'))
    ),
    e(Box, { width: 9 },
      e(Text, { color: 'gray' }, timeStr.padEnd(8))
    ),
    e(Box, { width: 3 },
      e(Text, null, config.emoji)
    ),
    e(Box, { width: 18 },
      e(Text, { color: config.color }, config.label)
    ),
    e(Box, null,
      e(Text, { color: 'gray', dimColor: true }, details)
    ),
    isRecent && e(Box, null,
      e(Text, { color: 'yellow', bold: true }, ' NEW')
    )
  );
}

// Empty state
function EmptyState() {
  return e(Box, { flexDirection: 'column', alignItems: 'center', paddingY: 2 },
    e(Text, { color: 'gray' }, '📭 No events yet'),
    e(Text, { color: 'gray', dimColor: true }, 'Events will appear as agents are spawned')
  );
}

export default function EventLog({ events, maxVisible = 8 }) {
  const visibleEvents = events.slice(0, maxVisible);
  
  return e(Box, { flexDirection: 'column', borderStyle: 'round', borderColor: 'magenta', padding: 1 },
    e(Box, { justifyContent: 'center', marginBottom: 1 },
      e(Gradient, { name: 'passion' },
        e(Text, { bold: true }, ' 📋 EVENT LOG ')
      ),
      e(Text, { color: 'gray' }, ' (' + events.length + ' total)')
    ),
    e(Box, { marginBottom: 1 },
      e(Box, { width: 3 }, e(Text, { color: 'gray', dimColor: true }, '#')),
      e(Box, { width: 9 }, e(Text, { color: 'gray', dimColor: true }, 'Time')),
      e(Box, { width: 3 }, e(Text, { color: 'gray', dimColor: true }, ' ')),
      e(Box, { width: 18 }, e(Text, { color: 'gray', dimColor: true }, 'Event')),
      e(Box, null, e(Text, { color: 'gray', dimColor: true }, 'Details'))
    ),
    visibleEvents.length === 0 
      ? e(EmptyState)
      : visibleEvents.map((event, i) => e(EventRow, { key: i, event, index: i })),
    events.length > maxVisible && e(Box, { marginTop: 1, justifyContent: 'center' },
      e(Text, { color: 'gray', dimColor: true }, '... and ' + (events.length - maxVisible) + ' more events')
    )
  );
}
