/**
 * Agent Pulse - Process & Session Scanner
 * Detects running Copilot CLI sessions and agents
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

const SESSION_STATE_DIR = path.join(os.homedir(), '.copilot', 'session-state');
const COPILOT_DIR = path.join(os.homedir(), '.copilot');

// Agent type patterns for classification
const AGENT_PATTERNS = {
  task: /\b(task|task-agent)\b/i,
  explore: /\b(explore|exploration)\b/i,
  'general-purpose': /\b(general-purpose|gp-agent)\b/i,
  'rubber-duck': /\b(rubber-duck|rubduck)\b/i,
  'code-review': /\b(code-review|review)\b/i,
  custom: /\b(custom|user-agent)\b/i
};

// Scan for running Copilot CLI processes
export function scanProcesses() {
  try {
    // Find all Copilot CLI processes - looking for the main copilot binary
    const psOutput = execSync(
      'ps aux | grep -E "copilot" | grep -v grep | grep -v agent-pulse',
      { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();
    
    const lines = psOutput.split('\n').filter(l => l.trim());
    
    const sessions = [];
    const agents = [];
    const seenPids = new Set();
    
    for (const line of lines) {
      const parts = line.split(/\s+/);
      const pid = parts[1];
      const cmdLine = parts.slice(10).join(' ');
      
      // Skip duplicates and non-copilot processes
      if (seenPids.has(pid)) continue;
      
      // Only count main copilot processes (not gh copilot wrapper or API calls)
      const isMainCopilot = cmdLine.includes('/copilot') && 
                            !cmdLine.includes('gh copilot') &&
                            !cmdLine.includes('gh api') &&
                            !cmdLine.includes('fswatch') &&
                            !cmdLine.includes('Microsoft Teams');
      
      if (!isMainCopilot) continue;
      seenPids.add(pid);
      
      // Check if this is a sub-agent based on command line args
      if (cmdLine.includes('--task') || cmdLine.includes('task-agent') || cmdLine.includes('agent_type=task')) {
        agents.push({ pid, type: 'task', cmd: cmdLine });
      } else if (cmdLine.includes('--explore') || cmdLine.includes('agent_type=explore')) {
        agents.push({ pid, type: 'explore', cmd: cmdLine });
      } else if (cmdLine.includes('--general-purpose') || cmdLine.includes('gp-agent')) {
        agents.push({ pid, type: 'general-purpose', cmd: cmdLine });
      } else if (cmdLine.includes('--rubber-duck')) {
        agents.push({ pid, type: 'rubber-duck', cmd: cmdLine });
      } else if (cmdLine.includes('--code-review')) {
        agents.push({ pid, type: 'code-review', cmd: cmdLine });
      } else if (cmdLine.includes('--agent')) {
        agents.push({ pid, type: 'custom', cmd: cmdLine });
      } else {
        // Main CLI session (not a sub-agent)
        sessions.push({ pid, cmd: cmdLine });
      }
    }
    
    return { sessions, agents };
  } catch (e) {
    // No matching processes found
    return { sessions: [], agents: [] };
  }
}

// Scan session state files for additional metadata
export function scanSessionFiles() {
  const sessionData = [];
  
  try {
    if (!fs.existsSync(SESSION_STATE_DIR)) {
      return sessionData;
    }
    
    const files = fs.readdirSync(SESSION_STATE_DIR);
    
    for (const file of files) {
      if (file.endsWith('.json')) {
        try {
          const filePath = path.join(SESSION_STATE_DIR, file);
          const stat = fs.statSync(filePath);
          const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
          
          sessionData.push({
            id: file.replace('.json', ''),
            lastModified: stat.mtime,
            ...content
          });
        } catch (e) {
          // Skip corrupted files
        }
      }
    }
  } catch (e) {
    // Directory might not exist yet
  }
  
  return sessionData;
}

// Count total sub-agents from session files
export function countSubAgents() {
  let total = 0;
  
  try {
    const sessions = scanSessionFiles();
    for (const session of sessions) {
      if (session.agents && Array.isArray(session.agents)) {
        total += session.agents.length;
      }
      if (session.subAgentCount) {
        total += session.subAgentCount;
      }
    }
  } catch (e) {
    // Ignore errors
  }
  
  return total;
}

// Get agent breakdown by type
export function getAgentBreakdown(agents) {
  const breakdown = {
    task: 0,
    explore: 0,
    'general-purpose': 0,
    'rubber-duck': 0,
    'code-review': 0,
    custom: 0
  };
  
  for (const agent of agents) {
    if (breakdown.hasOwnProperty(agent.type)) {
      breakdown[agent.type]++;
    }
  }
  
  return breakdown;
}

// Full scan combining all data sources
export function fullScan() {
  const { sessions, agents } = scanProcesses();
  const sessionFiles = scanSessionFiles();
  const subAgentCount = countSubAgents();
  const breakdown = getAgentBreakdown(agents);
  
  // Also count agents from active session files
  const recentSessionFiles = sessionFiles.filter(s => {
    const age = Date.now() - new Date(s.lastModified).getTime();
    return age < 300000; // Last 5 minutes
  });
  
  return {
    sessions: {
      count: Math.max(sessions.length, recentSessionFiles.length),
      list: sessions
    },
    agents: {
      count: agents.length,
      list: agents,
      breakdown
    },
    subAgents: {
      count: subAgentCount
    },
    timestamp: Date.now()
  };
}

export default {
  scanProcesses,
  scanSessionFiles,
  countSubAgents,
  getAgentBreakdown,
  fullScan
};
