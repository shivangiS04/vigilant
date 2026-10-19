import { useEvents } from "../hooks/useEvents";

const TYPE_ICON = {
  person_detected: "🧍",
  motion_detected: "〰️",
  vehicle_detected: "🚗",
  doorbell: "🔔",
};

function EventRow({ event }) {
  const icon = TYPE_ICON[event.type] || "📷";
  const time = new Date(event.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <div style={styles.row}>
      <span style={styles.icon}>{icon}</span>
      <span style={styles.time}>{time}</span>
      <span style={styles.camera}>{event.camera_name.replace(/_/g, " ")}</span>
      <span style={styles.type}>{event.type.replace(/_/g, " ")}</span>
      <span style={styles.confidence}>
        {event.confidence == null ? "—" : `${(event.confidence * 100).toFixed(0)}%`}
      </span>
    </div>
  );
}

export function EventTimeline({ homeId }) {
  const { events, loading, error } = useEvents(homeId);

  if (loading) return <div style={styles.state}>Loading events…</div>;
  if (error) return <div style={styles.stateError}>Error: {error}</div>;
  if (!events.length) return <div style={styles.state}>No events in last 24 hours</div>;

  return (
    <div style={styles.container}>
      <h2 style={styles.heading}>Event Timeline</h2>
      {events.map((e) => (
        <EventRow key={e.id} event={e} />
      ))}
    </div>
  );
}

const styles = {
  container: { fontFamily: "monospace", maxWidth: 600, overflowX: "hidden" },
  heading: { fontSize: 16, marginBottom: 8 },
  row: {
    display: "flex",
    gap: 8,
    padding: "6px 0",
    borderBottom: "1px solid #eee",
    alignItems: "center",
    minWidth: 0,
  },
  icon: { fontSize: 18, width: 20, flexShrink: 0 },
  time: { color: "#666", width: 52, flexShrink: 0, fontSize: 12 },
  camera: { flex: 1, textTransform: "capitalize", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  type: { flex: 1, color: "#333", textTransform: "capitalize", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  confidence: { color: "#888", width: 36, textAlign: "right", flexShrink: 0, fontSize: 12 },
  state: { color: "#666", padding: 16 },
  stateError: { color: "#c00", padding: 16 },
};
