import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const chartColors = ["#55b991", "#7798dc", "#e4a957", "#b07bd0", "#e47e73"];
const emptyAuthors = [];
const emptyWeeks = [];

function TimelineChart({ timeline }) {
  const authors = timeline?.authors || emptyAuthors;
  const weeks = timeline?.weeks || emptyWeeks;
  const data = useMemo(() => weeks.map((week, index) => {
    const row = { week };
    authors.forEach((author) => {
      row[author.author_key] = author.meaningful_lines?.[index] || 0;
    });
    return row;
  }), [authors, weeks]);

  if (!data.length) return <div className="chart-empty">Weekly activity will appear here when available.</div>;
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="#edf1f3" strokeDasharray="3 4" vertical={false} />
          <XAxis
            dataKey="week"
            tickFormatter={(value) => {
              const [year, month, day] = value.split("-").map(Number);
              return new Date(year, month - 1, day).toLocaleDateString(undefined, { month: "short", day: "numeric" });
            }}
            tick={{ fill: "#98a3ad", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            minTickGap={22}
          />
          <YAxis tick={{ fill: "#98a3ad", fontSize: 9 }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ border: "1px solid #e8edf0", borderRadius: 9, fontSize: 10 }}
            labelFormatter={(value) => `Week of ${value}`}
          />
          {authors.slice(0, 5).map((author, index) => (
            <Line
              key={author.author_key}
              type="monotone"
              dataKey={author.author_key}
              name={author.display_name || author.author_key}
              stroke={chartColors[index % chartColors.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default TimelineChart;
