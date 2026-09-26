function SalienceBar({ score }) {
  const pct = (score / 10) * 100;
  const color = score >= 7 ? "#e53e3e" : score >= 4 ? "#dd6b20" : "#38a169";
  return (
    <div style={styles.barWrap}>
      <div style={{ ...styles.bar, width: `${pct}%`, background: color }} />
    </div>
  );
}

export function PatternCard({ pattern, onSelect }) {
  const time = new Date(pattern.detected_at).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const score = pattern.salience_score;
  const scoreColor = score >= 7 ? "#e53e3e" : score >= 4 ? "#dd6b20" : "#38a169";

  return (
    <div
      style={{ ...styles.card, borderLeft: pattern.flagged ? "4px solid #e53e3e" : "4px solid #eee", cursor: onSelect ? "pointer" : "default" }}
      onClick={() => onSelect && onSelect(pattern)}
    >
      <div style={styles.header}>
        <span style={styles.type}>{pattern.pattern_type.replace(/_/g, " ")}</span>
        {pattern.flagged && <span style={styles.badge}>FLAGGED</span>}
        <span style={{ ...styles.score, color: scoreColor }}>{score.toFixed(1)}/10</span>
        <span style={styles.time}>{time}</span>
      </div>

      <SalienceBar score={score} />

      {pattern.explanation && (
        <p style={styles.explanation}>{pattern.explanation}</p>
      )}

      <div style={styles.footer}>
        {pattern.event_count} events
      </div>
    </div>
  );
}

export function PatternList({ patterns, loading, error, onSelect }) {
  if (loading) return <div style={styles.state}>Loading patterns…</div>;
  if (error) return <div style={styles.stateError}>Error: {error}</div>;
  if (!patterns.length) return <div style={styles.state}>No patterns detected yet</div>;

  return (
    <div>
      <h2 style={{ fontSize: 16, marginBottom: 8 }}>Detected Patterns</h2>
      {patterns.map((p) => (
        <PatternCard key={p.id} pattern={p} onSelect={onSelect} />
      ))}
    </div>
  );
}

const styles = {
  card: {
    background: "#fafafa",
    borderRadius: 6,
    padding: "12px 16px",
    marginBottom: 12,
    fontFamily: "sans-serif",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginBottom: 8,
  },
  type: { fontWeight: 600, textTransform: "capitalize", flex: 1 },
  badge: {
    background: "#e53e3e",
    color: "#fff",
    fontSize: 10,
    padding: "2px 6px",
    borderRadius: 3,
    fontWeight: 700,
    letterSpacing: 1,
  },
  score: { fontSize: 12, fontWeight: 600, flexShrink: 0 },
  time: { color: "#888", fontSize: 12, flexShrink: 0 },
  barWrap: {
    background: "#e2e8f0",
    borderRadius: 4,
    height: 8,
    marginBottom: 10,
  },
  bar: { height: "100%", borderRadius: 4, transition: "width 0.3s" },
  explanation: {
    margin: "8px 0 4px",
    fontSize: 14,
    color: "#2d3748",
    lineHeight: 1.5,
    fontStyle: "italic",
  },
  footer: { fontSize: 12, color: "#aaa", marginTop: 4 },
  state: { color: "#666", padding: 16 },
  stateError: { color: "#c00", padding: 16 },
};
