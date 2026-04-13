/**
 * Agent Pulse - Custom React Hooks
 */

import { useState, useEffect, useCallback } from 'react';
import { fullScan } from '../utils/scanner.js';
import { loadHistory, updateDailyStats, getStats, getSparklineData, loadEvents, addEvent } from '../utils/dataStore.js';

// Hook for real-time scanning
export function useScanner(intervalMs = 2000) {
  const [data, setData] = useState({
    sessions: { count: 0, list: [] },
    agents: { count: 0, list: [], breakdown: {} },
    subAgents: { count: 0 },
    timestamp: Date.now()
  });
  
  const [prevData, setPrevData] = useState(null);
  
  useEffect(() => {
    const scan = () => {
      const newData = fullScan();
      
      // Track changes for events
      if (prevData) {
        if (newData.sessions.count > prevData.sessions.count) {
          addEvent('session_started', { count: newData.sessions.count });
        } else if (newData.sessions.count < prevData.sessions.count) {
          addEvent('session_ended', { count: newData.sessions.count });
        }
        
        if (newData.agents.count > prevData.agents.count) {
          addEvent('agent_spawned', { 
            count: newData.agents.count,
            breakdown: newData.agents.breakdown
          });
        } else if (newData.agents.count < prevData.agents.count) {
          addEvent('agent_completed', { count: newData.agents.count });
        }
      }
      
      setPrevData(data);
      setData(newData);
      
      // Update historical data
      updateDailyStats(
        newData.sessions.count,
        newData.agents.count,
        newData.subAgents.count
      );
    };
    
    scan(); // Initial scan
    const interval = setInterval(scan, intervalMs);
    
    return () => clearInterval(interval);
  }, [intervalMs]);
  
  return data;
}

// Hook for historical data
export function useHistory() {
  const [history, setHistory] = useState(loadHistory());
  const [stats, setStats] = useState(null);
  
  useEffect(() => {
    const refresh = () => {
      const h = loadHistory();
      setHistory(h);
      setStats(getStats(h));
    };
    
    refresh();
    const interval = setInterval(refresh, 5000); // Refresh every 5 seconds
    
    return () => clearInterval(interval);
  }, []);
  
  const getSparkline = useCallback((field, count = 60) => {
    return getSparklineData(history, field, count);
  }, [history]);
  
  return { history, stats, getSparkline };
}

// Hook for event log
export function useEvents(maxEvents = 50) {
  const [events, setEvents] = useState([]);
  
  useEffect(() => {
    const refresh = () => {
      const allEvents = loadEvents();
      setEvents(allEvents.slice(-maxEvents).reverse());
    };
    
    refresh();
    const interval = setInterval(refresh, 2000);
    
    return () => clearInterval(interval);
  }, [maxEvents]);
  
  return events;
}

// Hook for uptime tracking
export function useUptime() {
  const [startTime] = useState(Date.now());
  const [uptime, setUptime] = useState('0s');
  
  useEffect(() => {
    const update = () => {
      const elapsed = Date.now() - startTime;
      const seconds = Math.floor(elapsed / 1000);
      const minutes = Math.floor(seconds / 60);
      const hours = Math.floor(minutes / 60);
      
      if (hours > 0) {
        setUptime(`${hours}h ${minutes % 60}m`);
      } else if (minutes > 0) {
        setUptime(`${minutes}m ${seconds % 60}s`);
      } else {
        setUptime(`${seconds}s`);
      }
    };
    
    update();
    const interval = setInterval(update, 1000);
    
    return () => clearInterval(interval);
  }, [startTime]);
  
  return uptime;
}

// Hook for animation frame counter (for pulse effect)
export function usePulse(intervalMs = 500) {
  const [frame, setFrame] = useState(0);
  
  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % 10);
    }, intervalMs);
    
    return () => clearInterval(interval);
  }, [intervalMs]);
  
  return frame;
}

export default {
  useScanner,
  useHistory,
  useEvents,
  useUptime,
  usePulse
};
