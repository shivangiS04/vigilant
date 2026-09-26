export function PatternDetail({ pattern, onBack }) {
  if (!pattern) return null;

  const time = new Date(pattern.detected_at).toLocaleString([], {
    weekday: "short", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });

  const score = pattern.salience_score;
  const scoreColor = score >= 7 ? "#e53e3e" : score >= 4 ? "#dd6b20" : "#38a169";
  const pct = (score / 10) * 100;

  const layers = [
    { label: "Novelty",     value: pattern.novelty_score,    desc: "How different from learned baseline" },
    { label: "Adaptation",  value: pattern.adaptation_score, desc: "How many times seen before" },
    { label: "Competition", value: null,                     desc: "Attention vs other patterns today" },
  ].filter(l => l.value != null);

  return (
    <div style={styles.wrap}>
      <button style={styles.back} onClick={onBack}>← Back</button>

      <div style={{ ...styles.card, borderLeft: pattern.flagged ? "4px solid #e53e3e" : "4px solid #cbd5e0" }}>
        <div style={styles.header}>
          <span style={styles.type}>{pattern.pattern_type.replace(/_/g, " ")}</span>
          {pattern.flagged && <span style={styles.badge}>FLAGGED</span>}
        </div>
        <div style={styles.time}>{time}</div>

        <div style={styles.salienceRow}>
          <span style={styles.salienceLabel}>Salience</span>
          <div style={styles.barWrap}>
            <div style={{ ...styles.bar, width: `${pct}%`, background: scoreColor }} />
          </div>
          <span style={{ ...styles.salienceVal, color: scoreColor }}>{score.toFixed(1)}/10</span>
        </div>

        {pattern.explanation && (
          <div style={styles.explanationBox}>
            <div style={styles.explanationLabel}>AI Explanation</div>
            <p style={styles.explanation}>{pattern.explanation}</p>
          </div>
        )}

        {layers.length > 0 && (
          <div style={styles.layers}>
            <div style={styles.layersTitle}>Score Breakdown</div>
            {layers.map(l => (
              <div key={l.label} style={styles.layerRow}>
                <div style={styles.layerLeft}>
                  <span style={styles.layerName}>{l.label}</span>
                  <span style={styles.layerDesc}>{l.desc}</span>
                </div>
                <div style={styles.layerBarWrap}>
                  <div style={{ ...styles.layerBar, width: `${(l.value / 10) * 100}%` }} />
                </div>
                <span style={styles.layerVal}>{l.value?.toFixed(1)}</span>
              </div>
            ))}
          </div>
        )}

        <div style={styles.meta}>
          {pattern.event_count} events in sequence
        </div>
      </div>
    </div>
  );
}

const styles = {
  wrap: { maxWidth: 600 },
  back: {
    background: "none", border: "none", cursor: "pointer",
    color: "#4a5568", fontSize: 14, padding: "0 0 12px", display: "block",
  },
  card: {
    background: "#fafafa", borderRadius: 8,
    padding: "20px 24px", fontFamily: "sans-serif",
  },
  header: { display: "flex", alignItems: "center", gap: 10, marginBottom: 4 },
  type: { fontWeight: 700, fontSize: 20, textTransform: "capitalize", flex: 1 },
  badge: {
    background: "#e53e3e", color: "#fff", fontSize: 10,
    padding: "2px 6px", borderRadius: 3, fontWeight: 700, letterSpacing: 1,
  },
  time: { color: "#718096", fontSize: 13, marginBottom: 20 },
  salienceRow: { display: "flex", alignItems: "center", gap: 10, marginBottom: 20 },
  salienceLabel: { fontSize: 13, color: "#4a5568", width: 60, flexShrink: 0 },
  barWrap: { flex: 1, background: "#e2e8f0", borderRadius: 4, height: 10 },
  bar: { height: "100%", borderRadius: 4, transition: "width 0.4s" },
  salienceVal: { fontSize: 14, fontWeight: 700, width: 48, textAlign: "right" },
  explanationBox: {
    background: "#fff", border: "1px solid #e2e8f0",
    borderRadius: 6, padding: "12px 16px", marginBottom: 20,
  },
  explanationLabel: { fontSize: 11, fontWeight: 600, color: "#a0aec0", letterSpacing: 1, marginBottom: 6 },
  explanation: { margin: 0, fontSize: 15, color: "#2d3748", lineHeight: 1.6, fontStyle: "italic" },
  layers: { marginBottom: 16 },
  layersTitle: { fontSize: 11, fontWeight: 600, color: "#a0aec0", letterSpacing: 1, marginBottom: 10 },
  layerRow: { display: "flex", alignItems: "center", gap: 10, marginBottom: 8 },
  layerLeft: { width: 100, flexShrink: 0 },
  layerName: { display: "block", fontSize: 13, fontWeight: 600, color: "#2d3748" },
  layerDesc: { display: "block", fontSize: 11, color: "#a0aec0" },
  layerBarWrap: { flex: 1, background: "#e2e8f0", borderRadius: 3, height: 6 },
  layerBar: { height: "100%", borderRadius: 3, background: "#667eea" },
  layerVal: { fontSize: 12, color: "#718096", width: 28, textAlign: "right" },
  meta: { fontSize: 12, color: "#a0aec0", borderTop: "1px solid #e2e8f0", paddingTop: 12 },
};
