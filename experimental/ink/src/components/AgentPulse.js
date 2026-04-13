/**
 * AgentPulse - Root App Component
 * Real-time agent tracking dashboard for GitHub Copilot CLI
 */

import React, { useState, useEffect } from 'react';
import { Box, Text, useApp, useInput } from 'ink';
import Header from './Header.js';
import LiveMetrics from './LiveMetrics.js';
import AgentTypeBreakdown from './AgentTypeBreakdown.js';
import SparklinePanel from './SparklinePanel.js';
import HistoryTable from './HistoryTable.js';
import EventLog from './EventLog.js';
import StatusBar from './StatusBar.js';
import { useScanner, useHistory, useEvents, useUptime } from '../hooks/useScanner.js';

const e = React.createElement;

// Configuration
const SCAN_INTERVAL = 2000; // 2 seconds

export default function AgentPulse() {
  const { exit } = useApp();
  const [isScanning, setIsScanning] = useState(false);
  const [previousData, setPreviousData] = useState(null);
  
  // Hooks for data
  const data = useScanner(SCAN_INTERVAL);
  const { history, stats, getSparkline } = useHistory();
  const events = useEvents(50);
  const uptime = useUptime();
  
  // Track previous data for trend indicators
  useEffect(() => {
    const timer = setTimeout(() => {
      setPreviousData(data);
    }, SCAN_INTERVAL);
    return () => clearTimeout(timer);
  }, [data]);
  
  // Scanning indicator
  useEffect(() => {
    setIsScanning(true);
    const timer = setTimeout(() => setIsScanning(false), 500);
    return () => clearTimeout(timer);
  }, [data.timestamp]);
  
  // Keyboard shortcuts
  useInput((input, key) => {
    if (input === 'q' || (key.ctrl && input === 'c')) {
      exit();
    }
  });
  
  const isActive = data.sessions.count > 0 || data.agents.count > 0;
  
  return e(Box, { flexDirection: 'column', padding: 1 },
    // Header with gradient title
    e(Header, { isActive }),
    // Main content grid
    e(Box, { flexDirection: 'row' },
      // Left column - Live metrics and breakdown
      e(Box, { flexDirection: 'column', flexGrow: 1, marginRight: 1 },
        e(LiveMetrics, { data, previousData }),
        e(AgentTypeBreakdown, { breakdown: data.agents.breakdown })
      ),
      // Right column - Sparklines and history
      e(Box, { flexDirection: 'column', width: 60 },
        e(SparklinePanel, { history, getSparkline }),
        e(HistoryTable, { stats })
      )
    ),
    // Event log - full width
    e(EventLog, { events, maxVisible: 6 }),
    // Status bar
    e(StatusBar, { 
      uptime,
      scanInterval: SCAN_INTERVAL,
      lastScan: data.timestamp,
      isScanning
    })
  );
}
