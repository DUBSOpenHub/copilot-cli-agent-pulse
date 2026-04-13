/**
 * StatusBar Component - Bottom bar with uptime, refresh rate, last scan time
 */

import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import Gradient from 'ink-gradient';
import { usePulse } from '../hooks/useScanner.js';

const e = React.createElement;

// Animated spinner
const SPINNERS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

// System info
function getSystemInfo() {
  return {
    platform: process.platform,
    nodeVersion: process.version,
    pid: process.pid,
    memoryMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024)
  };
}

export default function StatusBar({ uptime, scanInterval, lastScan, isScanning }) {
  const frame = usePulse(100);
  const spinner = SPINNERS[frame % SPINNERS.length];
  const [clock, setClock] = useState(new Date().toLocaleTimeString());
  const sysInfo = getSystemInfo();
  
  useEffect(() => {
    const interval = setInterval(() => {
      setClock(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(interval);
  }, []);
  
  const lastScanTime = lastScan ? new Date(lastScan).toLocaleTimeString() : '--:--:--';
  
  return e(Box, { flexDirection: 'column' },
    // Divider
    e(Box, null,
      e(Gradient, { name: 'vice' },
        e(Text, null, '━'.repeat(96))
      )
    ),
    // Status bar content
    e(Box, { justifyContent: 'space-between', paddingX: 1 },
      // Left section
      e(Box, null,
        e(Text, { color: 'gray' }, isScanning ? spinner : '●'),
        e(Text, { color: isScanning ? 'yellow' : 'green' }, ' ' + (isScanning ? 'SCANNING' : 'READY')),
        e(Text, { color: 'gray' }, ' │ '),
        e(Text, { color: 'cyan' }, '⏱️ Uptime: '),
        e(Text, { color: 'white', bold: true }, uptime)
      ),
      // Center section
      e(Box, null,
        e(Text, { color: 'gray' }, 'Refresh: '),
        e(Text, { color: 'yellow' }, (scanInterval / 1000) + 's'),
        e(Text, { color: 'gray' }, ' │ '),
        e(Text, { color: 'gray' }, 'Last scan: '),
        e(Text, { color: 'white' }, lastScanTime)
      ),
      // Right section
      e(Box, null,
        e(Text, { color: 'gray' }, '🖥️ ' + sysInfo.platform),
        e(Text, { color: 'gray' }, ' │ '),
        e(Text, { color: 'gray' }, 'Node ' + sysInfo.nodeVersion),
        e(Text, { color: 'gray' }, ' │ '),
        e(Text, { color: 'gray' }, 'PID: ' + sysInfo.pid),
        e(Text, { color: 'gray' }, ' │ '),
        e(Text, { color: 'magenta' }, sysInfo.memoryMB + 'MB'),
        e(Text, { color: 'gray' }, ' │ '),
        e(Text, { color: 'cyan' }, '🕐 ' + clock)
      )
    ),
    // Branding
    e(Box, { justifyContent: 'center', marginTop: 1 },
      e(Gradient, { name: 'rainbow' },
        e(Text, null, 'Agent Pulse v1.0.0 │ Havoc Hackathon #51 │ Contestant E │ Press Ctrl+C to exit')
      )
    )
  );
}
