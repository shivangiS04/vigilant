import { useState } from "react";
import { api } from "../utils/api";

export function PatternDetail({ pattern, onBack }) {
  const [feedback, setFeedback] = useState(null);
  const [feedbackMsg, setFeedbackMsg] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (!pattern) return null;

  const time = new Date(pattern.detected_at).toLocaleString([], {
    weekday: "short", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });

  const score = pattern.salience_score;
  const scoreColor = score >= 7 ? "#e53e3e" : score >= 4 ? "#dd6b20" : "#38a169";
  const pct = (score / 10) * 100;

  const layers = [
    { label: "Novelty",     value: pattern.novelty_score,    desc: "How different from learned baseline (Jaccard)" },
    { label: "Adaptation",  value: pattern.adaptation_score, desc: "How many times seen before" },
  ].filter((l) => l.value != null);

  const isSample = pattern.explanation?.startsWith("[Sample]");
  const explanationText = isSample
    ? pattern.explanation.replace(/^\[Sample\]\s*/, "")
    : pattern.explanation;

  async function handleFeedback(choice) {
    if (submitting || feedback) return;
    setSubmitting(true);
    try {
      const result = await api.submitFeedback(pattern.id, choice);
      setFeedback(choice);
      setFeedbackMsg(result.effect);
    } catch {
      setFeedbackMsg("Could not save feedback — try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={styles.wrap}>
      <button style={styles.back} onClick={onBack}>← Back to patterns</button>

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

        {pattern.explanation ? (
          <div style={styles.explanationBox}>
            <div style={styles.explanationLabel}>
              {isSample ? "SAMPLE EXPLANATION" : "AI EXPLANATION (AWS Bedrock)"}
            </div>
            <p style={styles.explanation}>{explanationText}</p>
            {isSample && (
              <div style={styles.sampleNote}>
                ⚠ This is demo data. Live patterns generate real Bedrock explanations.
              </div>
            )}
          </div>
        ) : (
          <div style={styles.explanationBox}>
            <div style={styles.explanationLabel}>AI EXPLANATION</div>
            <p style={{ ...styles.explanation, color: "#a0aec0", fontStyle: "normal" }}>
              Explanation unavailable — AWS Bedrock credentials not configured.
            </p>
          </div>
        )}

        {layers.length > 0 && (
          <div style={styles.layers}>
            <div style={styles.layersTitle}>SCORE BREAKDOWN</div>
            {layers.map((l) => (
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

        {pattern.flagged && (
          <div style={styles.feedbackBox}>
            <div style={styles.feedbackTitle}>Was this correct?</div>
            {feedback ? (
              <div style={styles.feedbackDone}>
                <span style={feedback === "normal" ? styles.feedbackOk : styles.feedbackAlert}>
                  {feedback === "normal" ? "✓ Marked as normal" : "✓ Marked as concerning"}
                </span>
                {feedbackMsg && <span style={styles.feedbackMsg}> — {feedbackMsg}</span>}
              </div>
            ) : (
              <div style={styles.feedbackBtns}>
                <button
                  style={{ ...styles.fbBtn, ...styles.fbNormal }}
                  onClick={() => handleFeedback("normal")}
                  disabled={submitting}
                >
                  This was normal
                </button>
                <button
                  style={{ ...styles.fbBtn, ...styles.fbConcerning }}
                  onClick={() => handleFeedback("concerning")}
                  disabled={submitting}
                >
                  This was concerning
                </button>
              </div>
            )}
            <div style={styles.feedbackHint}>
              "This was normal" teaches the system — similar patterns will score lower next time.
            </div>
          </div>
        )}

        <div style={styles.meta}>{pattern.event_count} events in sequence</div>
      </div>
    </div>
  );
}

const styles = {
  wrap: { maxWidth: 640 },
  back: {
    background: "none", border: "none", cursor: "pointer",
    color: "#4a5568", fontSize: 14, padding: "0 0 12px", display: "block",
  },
  card: { background: "#fafafa", borderRadius: 8, padding: "20px 24px", fontFamily: "sans-serif" },
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
  explanationLabel: { fontSize: 10, fontWeight: 700, color: "#a0aec0", letterSpacing: 1, marginBottom: 6 },
  explanation: { margin: 0, fontSize: 15, color: "#2d3748", lineHeight: 1.6, fontStyle: "italic" },
  sampleNote: { fontSize: 11, color: "#c05621", marginTop: 8, background: "#fffaf0", padding: "4px 8px", borderRadius: 3 },
  layers: { marginBottom: 16 },
  layersTitle: { fontSize: 10, fontWeight: 700, color: "#a0aec0", letterSpacing: 1, marginBottom: 10 },
  layerRow: { display: "flex", alignItems: "center", gap: 10, marginBottom: 8 },
  layerLeft: { width: 110, flexShrink: 0 },
  layerName: { display: "block", fontSize: 13, fontWeight: 600, color: "#2d3748" },
  layerDesc: { display: "block", fontSize: 11, color: "#a0aec0" },
  layerBarWrap: { flex: 1, background: "#e2e8f0", borderRadius: 3, height: 6 },
  layerBar: { height: "100%", borderRadius: 3, background: "#667eea" },
  layerVal: { fontSize: 12, color: "#718096", width: 28, textAlign: "right" },
  feedbackBox: {
    background: "#f7fafc", border: "1px solid #e2e8f0",
    borderRadius: 6, padding: "12px 16px", marginBottom: 16,
  },
  feedbackTitle: { fontSize: 13, fontWeight: 600, color: "#4a5568", marginBottom: 8 },
  feedbackBtns: { display: "flex", gap: 8, flexWrap: "wrap" },
  fbBtn: { padding: "6px 14px", borderRadius: 4, fontSize: 13, cursor: "pointer", border: "1px solid" },
  fbNormal: { background: "#f0fff4", color: "#276749", borderColor: "#c6f6d5" },
  fbConcerning: { background: "#fff5f5", color: "#9b2c2c", borderColor: "#fed7d7" },
  feedbackDone: { display: "flex", alignItems: "center", gap: 4, fontSize: 13 },
  feedbackOk: { color: "#276749", fontWeight: 600 },
  feedbackAlert: { color: "#9b2c2c", fontWeight: 600 },
  feedbackMsg: { color: "#4a5568" },
  feedbackHint: { fontSize: 11, color: "#a0aec0", marginTop: 8 },
  meta: { fontSize: 12, color: "#a0aec0", borderTop: "1px solid #e2e8f0", paddingTop: 12 },
};
