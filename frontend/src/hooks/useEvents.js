import { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";

export function useEvents(homeId = "home_001", hours = 24, pollMs = 30000) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
    try {
      const data = await api.getEvents(homeId, hours);
      setEvents(data.reverse()); // newest first
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [homeId, hours]);

  useEffect(() => {
    fetch();
    const id = setInterval(fetch, pollMs);
    return () => clearInterval(id);
  }, [fetch, pollMs]);

  return { events, loading, error, refresh: fetch };
}

export function usePatterns(homeId = "home_001", days = 7, flaggedOnly = false, pollMs = 30000) {
  const [patterns, setPatterns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
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
    fetch();
    const id = setInterval(fetch, pollMs);
    return () => clearInterval(id);
  }, [fetch, pollMs]);

  return { patterns, loading, error, refresh: fetch };
}
