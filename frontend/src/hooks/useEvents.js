import { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";

export function useEvents(homeId = "home_001", hours = 24, pollMs = 30000) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const data = await api.getEvents(homeId, hours);
      setEvents(data.reverse());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [homeId, hours]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, pollMs);
    return () => clearInterval(id);
  }, [fetchData, pollMs]);

  return { events, loading, error, refresh: fetchData };
}

export function usePatterns(homeId = "home_001", days = 7, flaggedOnly = false, pollMs = 30000) {
  const [patterns, setPatterns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const data = await api.getPatterns(homeId, days, flaggedOnly);
      setPatterns(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [homeId, days, flaggedOnly]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, pollMs);
    return () => clearInterval(id);
  }, [fetchData, pollMs]);

  return { patterns, loading, error, refresh: fetchData };
}

export function useRingStatus(pollMs = 30000) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const data = await api.getRingStatus();
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, pollMs);
    return () => clearInterval(id);
  }, [fetchData, pollMs]);

  return { status, loading };
}
