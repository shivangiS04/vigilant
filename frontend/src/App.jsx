import { useState } from "react";
import { EventTimeline } from "./components/EventTimeline";
import { PatternList } from "./components/PatternCard";
import { usePatterns } from "./hooks/useEvents";

const HOME_ID = "home_001";

export default function App() {
  const [tab, setTab] = useState("patterns");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const { patterns, loading, error } = usePatterns(HOME_ID, 7, flaggedOnly);

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <h1 style={styles.logo}>VIGILANT</h1>
        <span style={styles.sub}>Behavioral Intelligence for Connected Homes</span>
      </header>

      <nav style={styles.nav}>
        {["patterns", "events"].map((t) => (
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
            <label style={styles.filter}>
              <input
                type="checkbox"
                checked={flaggedOnly}
                onChange={(e) => setFlaggedOnly(e.target.checked)}
              />
              {" "}Show flagged only
            </label>
            <PatternList patterns={patterns} loading={loading} error={error} />
          </>
        )}
        {tab === "events" && <EventTimeline homeId={HOME_ID} />}
      </main>
    </div>
  );
}

const styles = {
  app: { maxWidth: 720, margin: "0 auto", padding: "0 16px 40px", fontFamily: "sans-serif" },
  header: { padding: "24px 0 8px", borderBottom: "2px solid #2d3748" },
  logo: { margin: 0, fontSize: 28, letterSpacing: 2, color: "#1a202c" },
  sub: { fontSize: 13, color: "#718096" },
  nav: { display: "flex", gap: 4, padding: "12px 0" },
  tab: {
    padding: "6px 16px",
    border: "1px solid #cbd5e0",
    background: "#fff",
    borderRadius: 4,
    cursor: "pointer",
    fontSize: 14,
  },
  tabActive: { background: "#2d3748", color: "#fff", borderColor: "#2d3748" },
  main: { paddingTop: 16 },
  filter: { display: "block", marginBottom: 12, fontSize: 14, color: "#4a5568", cursor: "pointer" },
};
