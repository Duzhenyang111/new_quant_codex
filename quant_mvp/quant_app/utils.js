const fmt = {
  money: (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 }),
  pct: (value) => `${(Number(value || 0) * 100).toFixed(2)}%`,
  price: (value) => Number(value || 0).toFixed(2),
  esc: (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]),
};

function pathFor(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
}

function scale(value, min, max, outMin, outMax) {
  if (max === min) return (outMin + outMax) / 2;
  return outMax - ((value - min) / (max - min)) * (outMax - outMin);
}
