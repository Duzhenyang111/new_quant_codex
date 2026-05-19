const reportUrl = "../quant_workspace/reports/latest.json";
const reportsUrl = "../quant_workspace/backtests/latest_year_backtest.json";
const dataStatusUrl = "../quant_workspace/data/status.json";
const initialCapital = 100000;

let reports = [];
let currentIndex = 0;
let chartMode = "day";

const money = (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
const price = (value) => Number(value || 0).toFixed(2);
const pct = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  byId(id).textContent = value;
}

function toneClass(value) {
  return Number(value || 0) >= 0 ? "positive" : "negative";
}

function emptyRow(cols, text) {
  return `<tr><td colspan="${cols}" class="muted">${esc(text)}</td></tr>`;
}

function renderDatePicker() {
  const select = byId("reportDateSelect");
  select.innerHTML = reports.map((item, index) => `<option value="${index}">${esc(item.review?.trade_date || `日报 ${index + 1}`)}</option>`).join("");
  select.value = String(currentIndex);
  byId("prevDayButton").disabled = currentIndex <= 0;
  byId("nextDayButton").disabled = currentIndex >= reports.length - 1;
}

function renderMetrics(review) {
  const totalAssets = Number(review.total_assets || review.equity_at_open || 0);
  const todayReturn = Number(review.today_return || 0);
  const cumulativeReturn = totalAssets / initialCapital - 1;
  setText("tradeDate", review.trade_date || "--");
  setText("totalAssets", money(totalAssets));
  setText("todayReturn", pct(todayReturn));
  setText("todayReturnLabel", todayReturn >= 0 ? "盈利" : "亏损");
  setText("cumulativeReturn", pct(cumulativeReturn));
  setText("cash", money(review.cash));
  setText("cashWeight", `现金仓位 ${pct(review.portfolio?.cash_weight)}`);
  byId("todayReturn").className = toneClass(todayReturn);
  byId("cumulativeReturn").className = toneClass(cumulativeReturn);

  const risk = review.risk || {};
  setText("maxDrawdown", pct(risk.max_drawdown));
  setText("volatility", pct(risk.annualized_volatility));
  setText("sharpe", Number(risk.sharpe || 0).toFixed(2));
  setText("winRate", pct(risk.win_rate));
}

function renderAllocation(review) {
  const portfolio = review.portfolio || {};
  const stockWeight = Math.max(0, Math.min(1, Number(portfolio.stock_weight || 0)));
  const cashWeight = Math.max(0, Math.min(1, Number(portfolio.cash_weight || 0)));
  setText("positionSummary", `持仓数量 ${portfolio.position_count || 0} 只 · 可用现金 ${money(portfolio.cash)} · 持仓市值 ${money(portfolio.stock_market_value)}`);
  const stockBar = byId("stockBar");
  const cashBar = byId("cashBar");
  stockBar.style.setProperty("--stock-width", `${Math.max(stockWeight * 100, stockWeight > 0 ? 10 : 0)}%`);
  cashBar.style.setProperty("--cash-width", `${Math.max(cashWeight * 100, cashWeight > 0 ? 10 : 0)}%`);
  stockBar.textContent = `股票 ${pct(stockWeight)}`;
  cashBar.textContent = `现金 ${pct(cashWeight)}`;
}

function renderHoldings(review) {
  const rows = review.holdings || [];
  byId("holdingRows").innerHTML = rows.length === 0 ? emptyRow(8, "暂无持仓") : rows.map((item) => `
    <tr>
      <td><span class="symbol">${esc(item.symbol)}</span><span class="subtext">${esc(item.industry || "未知")}</span></td>
      <td>${Number(item.quantity || 0).toLocaleString("zh-CN")}</td>
      <td>${price(item.cost_basis)}</td>
      <td>${price(item.close_price)}</td>
      <td class="${toneClass(item.daily_return)}">${pct(item.daily_return)}</td>
      <td class="${toneClass(item.position_pnl_pct)}">${pct(item.position_pnl_pct)}</td>
      <td>${money(item.market_value)}</td>
      <td>${pct(item.weight)}</td>
    </tr>
  `).join("");
}

function renderTrades(review) {
  const rows = review.trades || [];
  byId("tradeRows").innerHTML = rows.length === 0 ? emptyRow(6, "今日无交易记录") : rows.map((trade) => `
    <tr>
      <td><span class="symbol">${esc(trade.symbol)}</span></td>
      <td class="${trade.action === "buy" ? "positive" : "negative"}">${esc(String(trade.action || "").toUpperCase())}</td>
      <td>${Number(trade.quantity || 0).toLocaleString("zh-CN")}</td>
      <td>${price(trade.price)}</td>
      <td>${money(trade.amount)}</td>
      <td>${esc(trade.reason || "")}</td>
    </tr>
  `).join("");
}

function renderPlan(plan) {
  const rows = plan.orders || [];
  byId("planRows").innerHTML = rows.length === 0 ? emptyRow(5, "明日无交易计划，继续持有") : rows.map((order) => `
    <tr>
      <td><span class="symbol">${esc(order.symbol)}</span></td>
      <td>${esc(String(order.action || "").toUpperCase())}</td>
      <td>${pct(order.target_weight)}</td>
      <td>${Number(order.score || 0).toFixed(4)}</td>
      <td>${esc(order.reason || "")}</td>
    </tr>
  `).join("");
}

function renderPool(review, plan) {
  const pool = review.stock_pool?.length ? review.stock_pool : plan.orders || [];
  setText("poolTitle", `AI 动量选股池 (Top ${pool.length})`);
  byId("stockPool").innerHTML = pool.length === 0 ? `<p class="muted">暂无选股</p>` : pool.slice(0, 10).map((item) => `
    <article class="pool-card">
      <strong>${esc(item.symbol)}</strong>
      <span>分数 ${Number(item.score || 0).toFixed(4)}</span>
      <span class="muted">目标 ${pct(item.target_weight)}</span>
    </article>
  `).join("");
}

function renderInsights(review) {
  const insights = review.insights || [];
  byId("insights").innerHTML = insights.length === 0 ? `<div class="insight-item">暂无策略洞察</div>` : insights.map((text) => `<div class="insight-item">${esc(text)}</div>`).join("");
}

function chartKey(date) {
  if (chartMode === "year") return date.slice(0, 4);
  if (chartMode === "month") return date.slice(0, 7);
  return date;
}

function aggregateReports() {
  const buckets = new Map();
  for (const item of reports) {
    const review = item.review || {};
    const market = review.market || {};
    const key = chartKey(review.trade_date || "");
    if (!buckets.has(key)) {
      buckets.set(key, {
        label: key,
        startDate: review.trade_date,
        endDate: review.trade_date,
        equityEnd: Number(review.total_assets || 0),
        marketName: market.name || market.symbol || "大盘指数",
        marketStart: Number(market.open || market.close || 0),
        marketEnd: Number(market.close || 0),
        marketDailyReturn: Number(market.daily_return ?? market.average_return ?? 0),
      });
    }
    const bucket = buckets.get(key);
    bucket.endDate = review.trade_date;
    bucket.equityEnd = Number(review.total_assets || 0);
    if (market.close || market.open) {
      if (!bucket.marketStart) bucket.marketStart = Number(market.open || market.close || 0);
      bucket.marketEnd = Number(market.close || 0);
      bucket.marketDailyReturn = Number(market.daily_return ?? market.average_return ?? 0);
      bucket.marketName = market.name || bucket.marketName;
    }
  }
  const first = [...buckets.values()].find((bucket) => bucket.marketEnd || bucket.marketStart);
  const marketBase = first?.marketStart || first?.marketEnd || 0;
  return [...buckets.values()].map((bucket) => ({
    ...bucket,
    equityReturn: bucket.equityEnd / initialCapital - 1,
    marketReturn: marketBase && bucket.marketEnd ? bucket.marketEnd / marketBase - 1 : bucket.marketDailyReturn,
    marketPeriodReturn: bucket.marketStart && bucket.marketEnd ? bucket.marketEnd / bucket.marketStart - 1 : bucket.marketDailyReturn,
  }));
}

function pathFor(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
}

function scale(value, min, max, outMin, outMax) {
  if (max === min) return (outMin + outMax) / 2;
  return outMax - ((value - min) / (max - min)) * (outMax - outMin);
}

function showChartTooltip(event, point) {
  const tooltip = byId("chartTooltip");
  tooltip.hidden = false;
  tooltip.innerHTML = `
    <strong>${esc(point.label)}</strong>
    <span>${esc(point.startDate)}${point.startDate !== point.endDate ? ` 至 ${esc(point.endDate)}` : ""}</span>
    <span>总资产：${money(point.equityEnd)}</span>
    <span>账户累计收益：${pct(point.equityReturn)}</span>
    <span>${esc(point.marketName)}累计收益：${pct(point.marketReturn)}</span>
    <span>${esc(point.marketName)}区间涨跌：${pct(point.marketPeriodReturn)}</span>
    <span>指数收盘：${price(point.marketEnd)}</span>
  `;
  const wrap = byId("chartWrap").getBoundingClientRect();
  tooltip.style.left = `${Math.min(event.clientX - wrap.left + 14, wrap.width - 230)}px`;
  tooltip.style.top = `${Math.max(event.clientY - wrap.top - 18, 12)}px`;
}

function hideChartTooltip() {
  byId("chartTooltip").hidden = true;
}

function renderGlobalChart() {
  const svg = byId("globalChart");
  const data = aggregateReports();
  if (!data.length) {
    svg.innerHTML = "";
    return;
  }
  const width = 900;
  const height = 300;
  const pad = { left: 64, right: 34, top: 32, bottom: 54 };
  const equity = data.map((item) => Number(item.equityReturn || 0) * 100);
  const market = data.map((item) => Number(item.marketReturn || 0) * 100);
  const minValue = Math.min(...equity, ...market, -1);
  const maxValue = Math.max(...equity, ...market, 1);
  const x = (index) => pad.left + (index / Math.max(1, data.length - 1)) * (width - pad.left - pad.right);
  const equityPoints = equity.map((value, index) => ({ x: x(index), y: scale(value, minValue, maxValue, pad.top, height - pad.bottom) }));
  const marketPoints = market.map((value, index) => ({ x: x(index), y: scale(value, minValue, maxValue, pad.top, height - pad.bottom) }));
  const step = Math.max(1, Math.floor(data.length / 10));
  svg.innerHTML = `
    <line class="chart-axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" />
    <line class="chart-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" />
    <line class="chart-grid" x1="${pad.left}" y1="${pad.top}" x2="${width - pad.right}" y2="${pad.top}" />
    <line class="chart-grid" x1="${pad.left}" y1="${(height - pad.bottom + pad.top) / 2}" x2="${width - pad.right}" y2="${(height - pad.bottom + pad.top) / 2}" />
    <path class="chart-equity" d="${pathFor(equityPoints)}" />
    <path class="chart-market" d="${pathFor(marketPoints)}" />
    ${data.map((item, index) => {
      const startX = index === 0 ? pad.left : (x(index - 1) + x(index)) / 2;
      const endX = index === data.length - 1 ? width - pad.right : (x(index) + x(index + 1)) / 2;
      return `
        <rect class="chart-hit" data-point-index="${index}" x="${startX}" y="${pad.top}" width="${endX - startX}" height="${height - pad.top - pad.bottom}" />
        <line class="chart-hover-line" data-hover-line="${index}" x1="${equityPoints[index].x}" y1="${pad.top}" x2="${equityPoints[index].x}" y2="${height - pad.bottom}" />
        ${index % step === 0 || index === data.length - 1 ? `<text class="chart-label" x="${x(index)}" y="${height - 20}" text-anchor="middle">${esc(item.label.slice(5) || item.label)}</text>` : ""}
      `;
    }).join("")}
    <circle id="equityFocusDot" class="chart-focus-dot" cx="0" cy="0" r="4" stroke="#2563eb" />
    <circle id="marketFocusDot" class="chart-focus-dot" cx="0" cy="0" r="4" stroke="#16a34a" />
    <text class="chart-legend" x="${pad.left}" y="22">账户累计收益 ${equity.at(-1).toFixed(2)}%</text>
    <text class="chart-legend" x="${width - 270}" y="22">${esc(data.at(-1).marketName)} ${market.at(-1).toFixed(2)}%</text>
  `;
  svg.querySelectorAll("[data-point-index]").forEach((node) => {
    node.addEventListener("mousemove", (event) => {
      const index = Number(node.dataset.pointIndex);
      const equityDot = svg.querySelector("#equityFocusDot");
      const marketDot = svg.querySelector("#marketFocusDot");
      equityDot.setAttribute("cx", equityPoints[index].x);
      equityDot.setAttribute("cy", equityPoints[index].y);
      marketDot.setAttribute("cx", marketPoints[index].x);
      marketDot.setAttribute("cy", marketPoints[index].y);
      equityDot.classList.add("visible");
      marketDot.classList.add("visible");
      svg.querySelectorAll("[data-hover-line]").forEach((line) => line.classList.toggle("visible", line.dataset.hoverLine === String(index)));
      showChartTooltip(event, data[index]);
    });
    node.addEventListener("mouseleave", () => {
      svg.querySelectorAll("[data-hover-line]").forEach((line) => line.classList.remove("visible"));
      svg.querySelectorAll(".chart-focus-dot").forEach((dot) => dot.classList.remove("visible"));
      hideChartTooltip();
    });
  });
}

function renderDataStatus(status) {
  setText("dataSource", `数据源: ${status.source || "--"} + akshare_free_index_daily`);
  setText("dataRange", `范围: ${status.start_date || "--"} 至 ${status.end_date || "--"}`);
  setText("dataRows", `股票行数: ${Number(status.merged_rows || status.rows || 0).toLocaleString("zh-CN")}`);
  setText("dataNote", status.note || "指数数据来自免费 AkShare 日线");
}

async function loadDataStatus() {
  try {
    const response = await fetch(`${dataStatusUrl}?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderDataStatus(await response.json());
  } catch (error) {
    renderDataStatus({ source: "status_missing", note: `读取数据状态失败: ${error.message}` });
  }
}

function renderReport(payload) {
  const review = payload.review || {};
  const plan = payload.next_plan || {};
  renderDatePicker();
  renderMetrics(review);
  renderGlobalChart();
  renderAllocation(review);
  renderHoldings(review);
  renderTrades(review);
  renderPlan(plan);
  renderPool(review, plan);
  renderInsights(review);
}

async function loadReport() {
  const response = await fetch(`${reportsUrl}?t=${Date.now()}`);
  if (response.ok) {
    const payload = await response.json();
    reports = Array.isArray(payload) ? payload : payload.reports || [];
    currentIndex = Math.max(0, reports.length - 1);
    renderReport(reports[currentIndex]);
    return;
  }
  const latest = await fetch(`${reportUrl}?t=${Date.now()}`);
  if (!latest.ok) throw new Error(`HTTP ${latest.status}`);
  reports = [await latest.json()];
  currentIndex = 0;
  renderReport(reports[currentIndex]);
}

async function refresh() {
  await Promise.all([loadReport(), loadDataStatus()]);
}

byId("refreshButton").addEventListener("click", refresh);
byId("reportDateSelect").addEventListener("change", (event) => {
  currentIndex = Number(event.target.value);
  renderReport(reports[currentIndex]);
});
byId("prevDayButton").addEventListener("click", () => {
  currentIndex = Math.max(0, currentIndex - 1);
  renderReport(reports[currentIndex]);
});
byId("nextDayButton").addEventListener("click", () => {
  currentIndex = Math.min(reports.length - 1, currentIndex + 1);
  renderReport(reports[currentIndex]);
});
document.querySelectorAll("[data-chart-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    chartMode = button.dataset.chartMode;
    document.querySelectorAll("[data-chart-mode]").forEach((item) => item.classList.toggle("active", item === button));
    renderGlobalChart();
  });
});

refresh().catch((error) => {
  document.body.insertAdjacentHTML("beforeend", `<div class="section">加载日报失败：${esc(error.message)}</div>`);
});
