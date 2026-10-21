import { useEffect, useState } from "react";
import { api } from "../utils/api";

const PATTERN_LABELS = {
  rapid_return:       "Rapid Return",
  delivery:           "Delivery",
  unusual_entrance:   "Unusual Entrance",
  late_night_activity:"Late Night",
  loitering:          "Loitering",
  multi_camera_activity: "Multi-Camera",
  late_first_activity:"Late First Activity",
  standard_activity:  "Standard",
};

export function DailySummary({ homeId = "home_001" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fallback7d, setFallback7d] = useState(false);

  useEffect(() => {
    let mounted = true;
    const fetch = () =>
      api.getDailySummary(homeId, 24)
        .then(async (res) => {
          if (!mounted) return;
          if (res.total_events === 0 && res.total_patterns === 0) {
            // Today is empty — auto-switch to 7-day view
            const res7 = await api.getDailySummary(homeId, 168);
            if (mounted) { setData(res7); setFallback7d(true); setError(null); }
          } else {
            setData(res); setFallback7d(false); setError(null);
          }
        })
        .catch((err) => { if (mounted) setError(err.message); })
        .finally(() => { if (mounted) setLoading(false); });

    fetch();
    const id = setInterval(fetch, 5 * 60 * 1000);
    return () => { mounted = false; clearInterval(id); };
  }, [homeId]);

  if (loading) return <p style={s.muted}>Loading daily digest…</p>;
  if (error) return <p style={{ color: "#e53e3e", fontSize: 13 }}>{error}</p>;
  if (!data) return null;

  const {
    date,
    total_events,
    total_patterns,
    flagged_count,
    noise_reduction_pct,
    avg_salience,
    pattern_breakdown,
    top_pattern,
  } = data;

  return (
    <div style={s.card}>
      <div style={s.header}>
        <div>
          <h3 style={s.title}>{fallback7d ? "Last 7 Days" : "Today's Digest"}</h3>
          {fallback7d && <span style={s.fallbackNote}>No events today — showing last 7 days</span>}
        </div>
        <span style={s.date}>{date}</span>
      </div>

      {/* Stat row */}
      <div style={s.statRow}>
        <Stat value={total_events} label="raw events" />
        <Arrow />
        <Stat value={total_patterns} label="patterns" />
        <Arrow />
        <Stat
          value={flagged_count}
          label="flagged"
          highlight={flagged_count > 0}
        />
        {noise_reduction_pct !== null && (
          <div style={s.pill}>{noise_reduction_pct}% noise suppressed</div>
        )}
      </div>

      {/* Avg salience */}
      {total_patterns > 0 && (
        <div style={s.salienceRow}>
          <span style={s.muted}>Avg salience today:</span>
          <SalienceBar value={avg_salience} />
          <span style={{ ...s.salienceNum, color: salienceColor(avg_salience) }}>
            {avg_salience}/10
          </span>
        </div>
      )}

      {/* Pattern breakdown */}
      {Object.keys(pattern_breakdown).length > 0 && (
        <div style={s.breakdownRow}>
          {Object.entries(pattern_breakdown).map(([type, count]) => (
            <span key={type} style={s.chip}>
              {PATTERN_LABELS[type] || type} <b>{count}</b>
            </span>
          ))}
        </div>
      )}

      {/* Top pattern */}
      {top_pattern && (
        <div style={{ ...s.topBox, borderColor: flagged_count > 0 ? "#fed7d7" : "#e2e8f0" }}>
          <div style={s.topLabel}>
            Top alert · {PATTERN_LABELS[top_pattern.type] || top_pattern.type}
            <span style={{ ...s.salBadge, background: salienceColor(top_pattern.salience) }}>
              {top_pattern.salience}
            </span>
          </div>
          {top_pattern.explanation && (
            <p style={s.topExpl}>{top_pattern.explanation}</p>
          )}
        </div>
      )}

      {total_patterns === 0 && (
        <p style={s.muted}>No patterns detected in the {fallback7d ? "last 7 days" : "last 24 hours"}.</p>
      )}
    </div>
  );
}

function Stat({ value, label, highlight }) {
  return (
    <div style={{ ...s.stat, ...(highlight ? s.statHighlight : {}) }}>
      <span style={{ ...s.statNum, color: highlight ? "#e53e3e" : "#2d3748" }}>{value}</span>
      <span style={s.statLbl}>{label}</span>
    </div>
  );
}

function Arrow() {
  return <span style={s.arrow}>→</span>;
}

function SalienceBar({ value }) {
  const pct = Math.min((value / 10) * 100, 100);
  return (
    <div style={s.barTrack}>
      <div style={{ ...s.barFill, width: `${pct}%`, background: salienceColor(value) }} />
    </div>
  );
}

function salienceColor(v) {
  if (v >= 8) return "#e53e3e";
  if (v >= 6) return "#dd6b20";
  if (v >= 4) return "#d69e2e";
  return "#48bb78";
}

const s = {
  card: { background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "20px 16px 16px", marginBottom: 16, overflowX: "hidden" },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 },
  title: { margin: 0, fontSize: 16, fontWeight: 700, color: "#1a202c" },
  date: { fontSize: 12, color: "#a0aec0" },
  fallbackNote: { fontSize: 11, color: "#c05621", display: "block", marginTop: 2 },
  statRow: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 12 },
  stat: { display: "flex", flexDirection: "column", alignItems: "center", minWidth: 64 },
  statHighlight: { background: "#fff5f5", borderRadius: 6, padding: "4px 10px", border: "1px solid #fed7d7" },
  statNum: { fontSize: 24, fontWeight: 700, lineHeight: 1 },
  statLbl: { fontSize: 11, color: "#718096", marginTop: 2 },
  arrow: { fontSize: 16, color: "#a0aec0" },
  pill: { marginLeft: "auto", background: "#f0fff4", color: "#276749", borderRadius: 12, padding: "4px 12px", fontSize: 12, fontWeight: 600, border: "1px solid #c6f6d5" },
  salienceRow: { display: "flex", alignItems: "center", gap: 8, marginBottom: 10, fontSize: 13 },
  muted: { color: "#718096", fontSize: 13, margin: "6px 0" },
  salienceNum: { fontWeight: 600, fontSize: 13, minWidth: 40 },
  barTrack: { flex: 1, height: 8, background: "#e2e8f0", borderRadius: 4, overflow: "hidden" },
  barFill: { height: "100%", borderRadius: 4, transition: "width 0.4s" },
  breakdownRow: { display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 },
  chip: { fontSize: 12, background: "#f7fafc", border: "1px solid #e2e8f0", borderRadius: 12, padding: "3px 10px", color: "#4a5568" },
  topBox: { border: "1px solid", borderRadius: 6, padding: "10px 12px", background: "#fffaf0", marginTop: 4 },
  topLabel: { fontSize: 12, fontWeight: 600, color: "#744210", display: "flex", alignItems: "center", gap: 6, marginBottom: 4 },
  salBadge: { color: "#fff", borderRadius: 8, padding: "1px 7px", fontSize: 11, fontWeight: 700 },
  topExpl: { margin: 0, fontSize: 13, color: "#4a5568", lineHeight: 1.5 },
};
