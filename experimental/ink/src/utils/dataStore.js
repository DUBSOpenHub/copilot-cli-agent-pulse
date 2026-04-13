/**
 * Agent Pulse - Historical Data Persistence Layer
 * Stores agent tracking data in ~/.copilot/agent-pulse/
 */

import fs from 'fs';
import path from 'path';
import os from 'os';

const DATA_DIR = path.join(os.homedir(), '.copilot', 'agent-pulse');
const HISTORY_FILE = path.join(DATA_DIR, 'history.json');
const EVENTS_FILE = path.join(DATA_DIR, 'events.json');

// Ensure data directory exists
function ensureDataDir() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
}

// Load historical data
export function loadHistory() {
  ensureDataDir();
  try {
    if (fs.existsSync(HISTORY_FILE)) {
      const data = JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf-8'));
      return data;
    }
  } catch (e) {
    // Corrupted file, start fresh
  }
  return {
    daily: {},      // { "2024-01-15": { sessions: 5, agents: 12, subAgents: 34 } }
    hourly: [],     // Last 24 hours of samples
    allTime: {
      totalSessions: 0,
      totalAgents: 0,
      totalSubAgents: 0,
      firstSeen: null,
      peakConcurrentSessions: 0,
      peakConcurrentAgents: 0
    }
  };
}

// Save historical data
export function saveHistory(history) {
  ensureDataDir();
  fs.writeFileSync(HISTORY_FILE, JSON.stringify(history, null, 2));
}

// Load event log
export function loadEvents() {
  ensureDataDir();
  try {
    if (fs.existsSync(EVENTS_FILE)) {
      return JSON.parse(fs.readFileSync(EVENTS_FILE, 'utf-8'));
    }
  } catch (e) {
    // Corrupted file, start fresh
  }
  return [];
}

// Save events (keep last 1000)
export function saveEvents(events) {
  ensureDataDir();
  const trimmed = events.slice(-1000);
  fs.writeFileSync(EVENTS_FILE, JSON.stringify(trimmed, null, 2));
}

// Add a new event
export function addEvent(type, details) {
  const events = loadEvents();
  events.push({
    timestamp: new Date().toISOString(),
    type,
    details
  });
  saveEvents(events);
  return events;
}

// Update daily stats
export function updateDailyStats(sessions, agents, subAgents) {
  const history = loadHistory();
  const today = new Date().toISOString().split('T')[0];
  
  // Ensure daily object exists
  if (!history.daily) {
    history.daily = {};
  }
  
  if (!history.daily[today]) {
    history.daily[today] = { sessions: 0, agents: 0, subAgents: 0, samples: 0 };
  }
  
  // Ensure allTime object exists
  if (!history.allTime) {
    history.allTime = {
      totalSessions: 0,
      totalAgents: 0,
      totalSubAgents: 0,
      firstSeen: null,
      peakConcurrentSessions: 0,
      peakConcurrentAgents: 0
    };
  }
  
  // Ensure hourly array exists
  if (!history.hourly) {
    history.hourly = [];
  }
  
  const day = history.daily[today];
  day.sessions = Math.max(day.sessions, sessions);
  day.agents = Math.max(day.agents, agents);
  day.subAgents += subAgents;
  day.samples++;
  
  // Update all-time stats
  history.allTime.totalSessions += sessions > 0 ? 1 : 0;
  history.allTime.totalAgents += agents;
  history.allTime.totalSubAgents += subAgents;
  history.allTime.peakConcurrentSessions = Math.max(history.allTime.peakConcurrentSessions, sessions);
  history.allTime.peakConcurrentAgents = Math.max(history.allTime.peakConcurrentAgents, agents);
  
  if (!history.allTime.firstSeen) {
    history.allTime.firstSeen = new Date().toISOString();
  }
  
  // Update hourly samples (keep last 24 hours worth at 1 per minute)
  history.hourly.push({
    timestamp: Date.now(),
    sessions,
    agents,
    subAgents
  });
  history.hourly = history.hourly.slice(-1440); // 24 hours * 60 minutes
  
  saveHistory(history);
  return history;
}

// Get stats for different time periods
export function getStats(history) {
  if (!history) {
    return {
      today: { sessions: 0, agents: 0, subAgents: 0 },
      weekly: { sessions: 0, agents: 0, subAgents: 0 },
      monthly: { sessions: 0, agents: 0, subAgents: 0 },
      allTime: { totalSessions: 0, totalAgents: 0, totalSubAgents: 0, peakConcurrentSessions: 0, peakConcurrentAgents: 0 }
    };
  }
  
  const now = new Date();
  const today = now.toISOString().split('T')[0];
  const daily = history.daily || {};
  const allTime = history.allTime || { totalSessions: 0, totalAgents: 0, totalSubAgents: 0, peakConcurrentSessions: 0, peakConcurrentAgents: 0 };
  
  // Calculate weekly stats (last 7 days)
  const weeklyStats = { sessions: 0, agents: 0, subAgents: 0 };
  for (let i = 0; i < 7; i++) {
    const date = new Date(now - i * 86400000).toISOString().split('T')[0];
    if (daily[date]) {
      weeklyStats.sessions += daily[date].sessions || 0;
      weeklyStats.agents += daily[date].agents || 0;
      weeklyStats.subAgents += daily[date].subAgents || 0;
    }
  }
  
  // Calculate monthly stats (last 30 days)
  const monthlyStats = { sessions: 0, agents: 0, subAgents: 0 };
  for (let i = 0; i < 30; i++) {
    const date = new Date(now - i * 86400000).toISOString().split('T')[0];
    if (daily[date]) {
      monthlyStats.sessions += daily[date].sessions || 0;
      monthlyStats.agents += daily[date].agents || 0;
      monthlyStats.subAgents += daily[date].subAgents || 0;
    }
  }
  
  return {
    today: daily[today] || { sessions: 0, agents: 0, subAgents: 0 },
    weekly: weeklyStats,
    monthly: monthlyStats,
    allTime: allTime
  };
}

// Get sparkline data (last N samples)
export function getSparklineData(history, field, count = 60) {
  if (!history || !history.hourly || !Array.isArray(history.hourly)) {
    return [];
  }
  const samples = history.hourly.slice(-count);
  return samples.map(s => s[field] || 0);
}

export default {
  loadHistory,
  saveHistory,
  loadEvents,
  saveEvents,
  addEvent,
  updateDailyStats,
  getStats,
  getSparklineData
};
