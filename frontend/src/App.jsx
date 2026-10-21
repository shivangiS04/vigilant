import { useState } from "react";
import { EventTimeline } from "./components/EventTimeline";
import { PatternList } from "./components/PatternCard";
import { PatternDetail } from "./components/PatternDetail";
import { BaselineComparison } from "./components/BaselineComparison";
import { DailySummary } from "./components/DailySummary";
import { RingStatus } from "./components/RingStatus";
import { usePatterns, useEvents } from "./hooks/useEvents";

const HOME_ID = "home_001";

function NoiseReductionBanner({ patterns, events }) {
  const total = events.length;
  const flagged = patterns.filter((p) => p.flagged).length;
  const totalPatterns = patterns.length;
  const reductionPct = total > 0 ? Math.round(((total - flagged) / total) * 100) : null;

  return (
    <div style={bannerStyles.wrap}>
      <span style={bannerStyles.window}>Last 7 days</span>
      <div style={bannerStyles.stat}>
        <span style={bannerStyles.num}>{total}</span>
        <span style={bannerStyles.lbl}>raw events</span>
      </div>
      <div style={bannerStyles.arrow}>→</div>
      <div style={bannerStyles.stat}>
        <span style={bannerStyles.num}>{totalPatterns}</span>
        <span style={bannerStyles.lbl}>patterns detected</span>
      </div>
      <div style={bannerStyles.arrow}>→</div>
      <div style={{ ...bannerStyles.stat, ...bannerStyles.highlight }}>
        <span style={{ ...bannerStyles.num, color: "#e53e3e" }}>{flagged}</span>
        <span style={bannerStyles.lbl}>worth your attention</span>
      </div>
      {reductionPct !== null && (
        <div style={bannerStyles.pill}>
          {reductionPct}% noise suppressed
        </div>
      )}
    </div>
  );
}

const bannerStyles = {
  wrap: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 8,
    padding: "12px 16px",
    marginBottom: 16,
    flexWrap: "wrap",
  },
  window: {
    fontSize: 11,
    fontWeight: 600,
    color: "#a0aec0",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginRight: 4,
  },
  stat: { display: "flex", flexDirection: "column", alignItems: "center", minWidth: 80 },
  highlight: {
    background: "#fff5f5",
    borderRadius: 6,
    padding: "4px 10px",
    border: "1px solid #fed7d7",
  },
  num: { fontSize: 24, fontWeight: 700, color: "#2d3748", lineHeight: 1 },
  lbl: { fontSize: 11, color: "#718096", marginTop: 2 },
  arrow: { fontSize: 18, color: "#a0aec0" },
  pill: {
    marginLeft: "auto",
    background: "#f0fff4",
    color: "#276749",
    borderRadius: 12,
    padding: "4px 12px",
    fontSize: 13,
    fontWeight: 600,
    border: "1px solid #c6f6d5",
  },
};

function SalienceLegend() {
  return (
    <div style={legendStyles.wrap}>
      <span style={legendStyles.title}>Salience scale:</span>
      {[
        { range: "0–4", label: "Normal", color: "#e2e8f0", text: "#4a5568" },
        { range: "4–6", label: "Unusual", color: "#fefcbf", text: "#744210" },
        { range: "6–8", label: "Flagged", color: "#fed7d7", text: "#9b2c2c" },
        { range: "8–10", label: "High alert", color: "#fc8181", text: "#742a2a" },
      ].map(({ range, label, color, text }) => (
        <span key={range} style={{ ...legendStyles.item, background: color, color: text }}>
          {range} {label}
        </span>
      ))}
    </div>
  );
}

const legendStyles = {
  wrap: { display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 12 },
  title: { fontSize: 12, color: "#718096", marginRight: 4 },
  item: { fontSize: 11, borderRadius: 4, padding: "2px 8px", fontWeight: 500 },
};

export default function App() {
  const [tab, setTab] = useState("patterns");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [selected, setSelected] = useState(null);
  const { patterns, loading: pLoading, error: pError, refresh } = usePatterns(HOME_ID, 7, flaggedOnly);
  const { events } = useEvents(HOME_ID, 168); // 7 days = 168 h, same window as patterns

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <h1 style={styles.logo}>VIGILANT</h1>
        <span style={styles.sub}>Behavioral Intelligence for Connected Homes</span>
      </header>

      {selected ? (
        <PatternDetail pattern={selected} onBack={() => { setSelected(null); refresh(); }} />
      ) : (
        <>
          <NoiseReductionBanner patterns={patterns} events={events} />
          <RingStatus />

          <nav style={styles.nav}>
            {["patterns", "analytics", "events"].map((t) => (
              <button
                key={t}
                style={{ ...styles.tab, ...(tab === t ? styles.tabActive : {}) }}
                onClick={() => setTab(t)}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </nav>

          <main style={styles.main}>
            {tab === "patterns" && (
              <>
                <div style={styles.filterRow}>
                  <label style={styles.filter}>
                    <input
                      type="checkbox"
                      checked={flaggedOnly}
                      onChange={(e) => setFlaggedOnly(e.target.checked)}
                    />
                    {" "}Show flagged only
                  </label>
                  <SalienceLegend />
                </div>
                <PatternList
                  patterns={patterns}
                  loading={pLoading}
                  error={pError}
                  onSelect={setSelected}
                />
              </>
            )}
            {tab === "analytics" && (
              <>
                <DailySummary homeId={HOME_ID} />
                <BaselineComparison homeId={HOME_ID} />
              </>
            )}
            {tab === "events" && <EventTimeline homeId={HOME_ID} />}
          </main>
          <footer style={styles.footer}>
            <a href={`${import.meta.env.VITE_API_URL || ""}/privacy`} style={styles.footerLink} target="_blank" rel="noreferrer">Privacy</a>
          </footer>
        </>
      )}
    </div>
  );
}

const styles = {
  app: { maxWidth: 760, margin: "0 auto", padding: "0 16px 40px", fontFamily: "sans-serif" },
  footer: { marginTop: 24, paddingTop: 12, borderTop: "1px solid #e2e8f0", textAlign: "center" },
  footerLink: { fontSize: 12, color: "#a0aec0", textDecoration: "none" },
  header: { padding: "24px 0 8px", borderBottom: "2px solid #2d3748", marginBottom: 16 },
  logo: { margin: 0, fontSize: 28, letterSpacing: 2, color: "#1a202c" },
  sub: { fontSize: 13, color: "#718096" },
  nav: { display: "flex", gap: 4, padding: "8px 0" },
  tab: {
    padding: "6px 16px", border: "1px solid #cbd5e0",
    background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 14,
  },
  tabActive: { background: "#2d3748", color: "#fff", borderColor: "#2d3748" },
  main: { paddingTop: 12 },
  filterRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
    flexWrap: "wrap",
    gap: 8,
  },
  filter: { fontSize: 14, color: "#4a5568", cursor: "pointer" },
};
