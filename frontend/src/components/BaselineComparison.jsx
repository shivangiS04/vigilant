import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { api } from "../utils/api";

const DOT_RADIUS = 5;

function ColoredDot(props) {
  const { cx, cy, payload } = props;
  const above = payload.actual_activity > payload.baseline_activity;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={DOT_RADIUS}
      fill={above ? "#ef4444" : "#10b981"}
      stroke="#fff"
      strokeWidth={2}
    />
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div style={tt.box}>
      <strong style={tt.label}>{label}</strong>
      <div>Actual: <b style={{ color: d.actual_activity > d.baseline_activity ? "#ef4444" : "#10b981" }}>{d.actual_activity}%</b></div>
      <div>Baseline: <b style={{ color: "#9ca3af" }}>{d.baseline_activity}%</b></div>
      <div>Events: {d.event_count}</div>
      {d.flags_count > 0 && (
        <div style={{ color: "#ef4444", marginTop: 4 }}>⚑ {d.flags_count} flag{d.flags_count > 1 ? "s" : ""}</div>
      )}
    </div>
  );
}

const tt = {
  box: { background: "#fff", border: "1px solid #e2e8f0", borderRadius: 6, padding: "8px 12px", fontSize: 13, lineHeight: 1.6 },
  label: { display: "block", marginBottom: 4, color: "#1a202c" },
};

export function BaselineComparison({ homeId = "home_001" }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetch = () =>
      api.getBaselineComparison(homeId)
        .then((res) => { if (mounted) { setData(res.days || []); setError(null); } })
        .catch((err) => { if (mounted) setError(err.message); })
        .finally(() => { if (mounted) setLoading(false); });

    fetch();
    const id = setInterval(fetch, 5 * 60 * 1000);
    return () => { mounted = false; clearInterval(id); };
  }, [homeId]);

  if (loading) return <p style={s.muted}>Loading baseline…</p>;
  if (error) return <p style={{ color: "#e53e3e" }}>{error}</p>;
  if (!data.length) return <p style={s.muted}>No data yet — seed demo data or wait for events.</p>;

  const flagDays = data.filter((d) => d.flags_count > 0).length;

  return (
    <div style={s.card}>
      <div style={s.header}>
        <h3 style={s.title}>7-Day Activity vs. Baseline</h3>
        {flagDays > 0 && (
          <span style={s.badge}>{flagDays} flagged day{flagDays > 1 ? "s" : ""}</span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gradActual" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.18} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />

          <XAxis
            dataKey="day_name"
            tick={{ fontSize: 12, fill: "#718096" }}
            tickFormatter={(v) => v.slice(0, 3)}
          />

          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "#718096" }}
            tickFormatter={(v) => `${v}%`}
            width={38}
          />

          <Tooltip content={<CustomTooltip />} />

          <Legend
            wrapperStyle={{ fontSize: 13, paddingTop: 8 }}
            formatter={(value) => value}
          />

          {/* Baseline — dashed grey */}
          <Area
            type="monotone"
            dataKey="baseline_activity"
            name="Baseline"
            stroke="#9ca3af"
            strokeDasharray="5 5"
            strokeWidth={2}
            fill="none"
            dot={false}
            isAnimationActive={false}
          />

          {/* Actual — blue fill + color-coded dots */}
          <Area
            type="monotone"
            dataKey="actual_activity"
            name="Actual Activity"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="url(#gradActual)"
            dot={<ColoredDot />}
            activeDot={{ r: 6 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Per-day flag badges */}
      {flagDays > 0 && (
        <div style={s.flagRow}>
          {data.filter((d) => d.flags_count > 0).map((d) => (
            <span key={d.date} style={s.flagBadge}>
              {d.day_name.slice(0, 3)} · {d.flags_count} ⚑
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const s = {
  card: { background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "20px 16px 16px", marginBottom: 16 },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 },
  title: { margin: 0, fontSize: 16, fontWeight: 700, color: "#1a202c" },
  badge: { fontSize: 12, background: "#fff5f5", color: "#c53030", border: "1px solid #feb2b2", borderRadius: 12, padding: "2px 10px" },
  muted: { color: "#718096", fontSize: 14, textAlign: "center", padding: "20px 0" },
  flagRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 },
  flagBadge: { fontSize: 12, background: "#fff5f5", color: "#c53030", borderRadius: 12, padding: "2px 10px", border: "1px solid #fed7d7" },
};
