import { useRingStatus } from "../hooks/useEvents";

const dot = (ok) => ({
  display: "inline-block",
  width: 9,
  height: 9,
  borderRadius: "50%",
  background: ok ? "#38a169" : "#e53e3e",
  marginRight: 6,
  flexShrink: 0,
});

export function RingStatus() {
  const { status, loading } = useRingStatus(15000);

  if (loading) return <div style={styles.panel}><span style={styles.dim}>Checking Ring connection…</span></div>;
  if (!status) return <div style={styles.panel}><span style={styles.dim}>Ring status unavailable</span></div>;

  const linked = status.linked_account_count > 0;
  const configured = status.ring_configured;

  return (
    <div style={styles.panel}>
      <div style={styles.row}>
        <span style={styles.label}>Ring API</span>
        <span style={dot(configured)} />
        <span style={configured ? styles.ok : styles.warn}>
          {configured ? "Credentials configured" : "Not configured"}
        </span>
      </div>

      <div style={styles.row}>
        <span style={styles.label}>Account</span>
        <span style={dot(linked)} />
        <span style={linked ? styles.ok : styles.warn}>
          {linked
            ? `${status.linked_account_count} linked (${status.linked_accounts[0]?.account_identifier || "—"})`
            : status.account_link_configured
              ? "Not yet linked — visit /ring to authorize"
              : "Account linking not configured"}
        </span>
      </div>

      <div style={styles.row}>
        <span style={styles.label}>Devices</span>
        {linked && status.devices.length > 0 ? (
          <>
            <span style={{ ...dot(true), background: "#3182ce" }} />
            <span style={styles.dim}>
              {status.devices.map((d) => d.name).join(" · ")}
            </span>
          </>
        ) : (
          <>
            <span style={dot(false)} />
            <span style={styles.warn}>
              {linked ? "No devices reported yet" : "No Ring devices — link your account"}
            </span>
          </>
        )}
      </div>

      {status.simulator_device_count > 0 && (
        <div style={styles.row}>
          <span style={styles.label}>Sample data</span>
          <span style={{ ...dot(false), background: "#ed8936" }} />
          <span style={styles.dim}>
            {status.simulator_device_count} simulated camera{status.simulator_device_count !== 1 ? "s" : ""} in DB — not from Ring
          </span>
        </div>
      )}

      <div style={styles.row}>
        <span style={styles.label}>Last webhook</span>
        <span style={dot(!!status.last_webhook)} />
        {status.last_webhook ? (
          <span style={styles.dim}>
            {new Date(status.last_webhook.received_at).toLocaleTimeString()} — signature{" "}
            <span style={status.last_webhook.processed ? styles.ok : styles.warn}>
              {status.last_webhook.processed ? "verified ✓" : "pending"}
            </span>
          </span>
        ) : (
          <span style={styles.warn}>
            {status.mode === "simulator"
              ? "Waiting for simulator to start…"
              : "No webhooks received yet"}
          </span>
        )}
      </div>

      {status.mode === "simulator" && (
        <div style={styles.badge}>DEV — Simulator mode: webhooks are HMAC-signed locally</div>
      )}
    </div>
  );
}

const styles = {
  panel: {
    background: "#f7fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    padding: "10px 14px",
    marginBottom: 16,
    fontSize: 13,
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    marginBottom: 4,
  },
  label: {
    color: "#718096",
    minWidth: 90,
    fontWeight: 500,
  },
  ok: { color: "#276749" },
  warn: { color: "#9b2335" },
  dim: { color: "#4a5568" },
  badge: {
    marginTop: 6,
    fontSize: 11,
    color: "#2b6cb0",
    background: "#ebf8ff",
    borderRadius: 3,
    padding: "2px 6px",
    display: "inline-block",
  },
};
