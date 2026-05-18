const reportUrl = "../quant_workspace/reports/latest.json";
const reportsUrl = "../quant_workspace/backtests/latest_year_backtest.json";
const dataStatusUrl = "../quant_workspace/data/status.json";
const initialCapital = 100000;

let reports = [];
let currentIndex = 0;
let chartMode = "day";
let activePlanOrder = null;

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

function currentPayload() {
  return reports[currentIndex] || { review: {}, next_plan: {} };
}

function htmlEmpty(cols, text) {
  return `<tr><td colspan="${cols}" class="empty-state">${esc(text)}</td></tr>`;
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
  setText("todayReturnLabel", todayReturn >= 0 ? "今日盈利" : "今日亏损");
  setText("cumulativeReturn", pct(cumulativeReturn));
  setText("cash", money(review.cash));
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
  setText("positionSummary", `${portfolio.position_count || 0} 只 / ${money(portfolio.stock_market_value)} 市值`);
  const stockBar = byId("stockBar");
  const cashBar = byId("cashBar");
  stockBar.style.setProperty("--stock-width", `${Math.max(stockWeight * 100, stockWeight > 0 ? 8 : 0)}%`);
  cashBar.style.setProperty("--cash-width", `${Math.max(cashWeight * 100, cashWeight > 0 ? 8 : 0)}%`);
  stockBar.textContent = `股票 ${pct(stockWeight)}`;
  cashBar.textContent = `现金 ${pct(cashWeight)}`;
}

function renderActionSummary(review, plan) {
  const orders = plan.orders || [];
  const buyCount = orders.filter((order) => order.action === "buy").length;
  const sellCount = orders.filter((order) => order.action === "sell").length;
  const trades = review.trades || [];
  const skipped = review.skipped || {};
  const actionItems = [
    {
      tone: orders.length ? "warning" : "",
      title: orders.length ? `明日计划 ${orders.length} 笔：买入 ${buyCount}，卖出 ${sellCount}` : "明日暂无调仓计划",
      body: orders.length ? "先检查目标仓位、因子解释和数据新鲜度，再进入执行。" : "当前组合无需主动交易，重点观察持仓和风险。"
    },
    {
      tone: trades.length ? "" : "warning",
      title: trades.length ? `今日已模拟成交 ${trades.length} 笔` : "今日无模拟成交",
      body: trades.length ? "成交按今日开盘价、手续费、印花税和整手规则入账。" : "可能因为昨日无计划、停牌、涨跌停或现金不足。"
    },
    {
      tone: Object.keys(skipped).length ? "danger" : "",
      title: Object.keys(skipped).length ? `有 ${Object.keys(skipped).length} 笔订单被跳过` : "执行约束正常",
      body: Object.keys(skipped).length ? Object.entries(skipped).map(([symbol, reason]) => `${symbol}: ${reason}`).join("；") : "未发现停牌、涨跌停或缺失开盘价导致的跳单。"
    }
  ];
  byId("actionSummary").innerHTML = actionItems.map((item) => `
    <div class="action-item ${item.tone}">
      <strong>${esc(item.title)}</strong>
      <span>${esc(item.body)}</span>
    </div>
  `).join("");
}

function renderRiskAlerts(review, status) {
  const alerts = [];
  const risk = review.risk || {};
  const drawdown = Number(risk.max_drawdown || 0);
  const cashWeight = Number(review.portfolio?.cash_weight || 0);
  if (drawdown <= -0.1) alerts.push({ tone: "danger", title: "回撤进入警戒区", body: `最大回撤 ${pct(drawdown)}，建议降低单票权重或暂停加仓。` });
  if (cashWeight < 0.03) alerts.push({ tone: "warning", title: "现金缓冲偏低", body: `现金仓位 ${pct(cashWeight)}，明日买入可能受资金约束。` });
  if (status?.end_date && review.trade_date && status.end_date < review.trade_date) {
    alerts.push({ tone: "danger", title: "行情数据可能滞后", body: `数据结束于 ${status.end_date}，当前报告日为 ${review.trade_date}。` });
  }
  if (!alerts.length) alerts.push({ tone: "", title: "未触发核心风险提示", body: "回撤、现金缓冲和数据日期均未触发工作台阈值。" });
  byId("riskAlerts").innerHTML = alerts.map((item) => `
    <div class="alert-item ${item.tone}">
      <strong>${esc(item.title)}</strong>
      <span>${esc(item.body)}</span>
    </div>
  `).join("");
}

function filteredHoldings(review) {
  const query = byId("holdingSearch").value.trim().toLowerCase();
  const rows = review.holdings || [];
  if (!query) return rows;
  return rows.filter((item) => [item.symbol, item.name, item.industry].some((value) => String(value || "").toLowerCase().includes(query)));
}

function renderHoldings(review) {
  const rows = filteredHoldings(review);
  byId("holdingRows").innerHTML = rows.length === 0 ? htmlEmpty(8, "暂无匹配持仓") : rows.map((item) => `
    <tr>
      <td><span class="symbol">${esc(item.symbol)}</span><span class="subtext">${esc(item.industry || "未知行业")}</span></td>
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
  const filter = byId("tradeActionFilter").value;
  const rows = (review.trades || []).filter((trade) => filter === "all" || trade.action === filter);
  byId("tradeRows").innerHTML = rows.length === 0 ? htmlEmpty(6, "暂无匹配成交") : rows.map((trade) => `
    <tr>
      <td><span class="symbol">${esc(trade.symbol)}</span></td>
      <td><span class="tag ${trade.action === "sell" ? "sell" : ""}">${esc(String(trade.action || "").toUpperCase())}</span></td>
      <td>${Number(trade.quantity || 0).toLocaleString("zh-CN")}</td>
      <td>${price(trade.price)}</td>
      <td>${money(trade.amount)}</td>
      <td>${esc(trade.reason || "")}</td>
    </tr>
  `).join("");
}

function filteredPlan(plan) {
  const filter = byId("planActionFilter").value;
  return (plan.orders || []).filter((order) => filter === "all" || order.action === filter);
}

function renderPlan(plan) {
  const rows = filteredPlan(plan);
  byId("planRows").innerHTML = rows.length === 0 ? htmlEmpty(6, "暂无匹配交易计划") : rows.map((order, index) => `
    <tr>
      <td><span class="symbol">${esc(order.symbol)}</span></td>
      <td><span class="tag ${order.action === "sell" ? "sell" : ""}">${esc(String(order.action || "").toUpperCase())}</span></td>
      <td>${pct(order.target_weight)}</td>
      <td>${Number(order.score || 0).toFixed(4)}</td>
      <td>${esc(order.reason || "")}</td>
      <td><button class="detail-button" type="button" data-plan-index="${index}">因子</button></td>
    </tr>
  `).join("");
  byId("planRows").querySelectorAll("[data-plan-index]").forEach((button) => {
    button.addEventListener("click", () => {
      activePlanOrder = rows[Number(button.dataset.planIndex)];
      renderFactorDrawer(activePlanOrder);
    });
  });
  if (activePlanOrder) renderFactorDrawer(activePlanOrder);
}

function metricLabel(key) {
  return {
    momentum_20: "20日动量",
    momentum_60: "60日动量",
    trend: "均线趋势",
    liquidity: "流动性",
    low_volatility: "低波动"
  }[key] || key;
}

function metricValue(key, value) {
  return key === "liquidity" ? Number(value || 0).toFixed(2) : pct(value);
}

function renderFactorDrawer(order) {
  const drawer = byId("factorDrawer");
  if (!order) {
    drawer.hidden = true;
    return;
  }
  const metrics = order.metrics || {};
  drawer.hidden = false;
  drawer.innerHTML = `
    <strong>${esc(order.symbol)} 因子拆解</strong>
    <p class="muted">${esc(order.reason || "暂无解释")}</p>
    <div class="factor-grid">
      ${Object.entries(metrics).map(([key, value]) => `
        <div>
          <span>${esc(metricLabel(key))}</span>
          <strong>${esc(metricValue(key, value))}</strong>
        </div>
      `).join("") || `<div><span>暂无因子</span><strong>--</strong></div>`}
    </div>
  `;
}

function renderPool(review, plan) {
  const pool = review.stock_pool?.length ? review.stock_pool : plan.orders || [];
  setText("poolTitle", `AI 动量选股池 (Top ${pool.length})`);
  byId("stockPool").innerHTML = pool.length === 0 ? `<p class="empty-state">暂无选股</p>` : pool.slice(0, 15).map((item) => `
    <article class="pool-card">
      <strong>${esc(item.symbol)}</strong>
      <span>分数 ${Number(item.score || 0).toFixed(4)}</span>
      <span>目标 ${pct(item.target_weight)}</span>
      <span>${esc(item.reason || "")}</span>
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
  `;
  const wrap = byId("chartWrap").getBoundingClientRect();
  tooltip.style.left = `${Math.min(event.clientX - wrap.left + 14, wrap.width - 244)}px`;
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
  const width = 960;
  const height = 320;
  const pad = { left: 66, right: 34, top: 34, bottom: 56 };
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
    <circle id="equityFocusDot" class="chart-focus-dot" cx="0" cy="0" r="4" stroke="#1e40af" />
    <circle id="marketFocusDot" class="chart-focus-dot" cx="0" cy="0" r="4" stroke="#f59e0b" />
    <text class="chart-legend" x="${pad.left}" y="24">账户 ${equity.at(-1).toFixed(2)}%</text>
    <text class="chart-legend" x="${width - 250}" y="24">${esc(data.at(-1).marketName)} ${market.at(-1).toFixed(2)}%</text>
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
  setText("dataSource", `数据源: ${status.source || "--"}`);
  setText("dataRange", `范围: ${status.start_date || "--"} 至 ${status.end_date || "--"}`);
  setText("dataRows", `股票行数: ${Number(status.merged_rows || status.rows || 0).toLocaleString("zh-CN")}`);
  setText("dataNote", status.note || `完成 ${status.done_symbols || 0}/${status.total_symbols || 0} 只股票`);
}

async function loadDataStatus() {
  try {
    const response = await fetch(`${dataStatusUrl}?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    return { source: "status_missing", note: `读取数据状态失败: ${error.message}` };
  }
}

function renderReport(status = {}) {
  const payload = currentPayload();
  const review = payload.review || {};
  const plan = payload.next_plan || {};
  renderDatePicker();
  renderMetrics(review);
  renderAllocation(review);
  renderActionSummary(review, plan);
  renderRiskAlerts(review, status);
  renderGlobalChart();
  renderHoldings(review);
  renderTrades(review);
  renderPlan(plan);
  renderPool(review, plan);
  renderInsights(review);
  renderDataStatus(status);
}

async function loadReport() {
  const response = await fetch(`${reportsUrl}?t=${Date.now()}`);
  if (response.ok) {
    const payload = await response.json();
    reports = Array.isArray(payload) ? payload : payload.reports || [];
    currentIndex = Math.max(0, reports.length - 1);
    return;
  }
  const latest = await fetch(`${reportUrl}?t=${Date.now()}`);
  if (!latest.ok) throw new Error(`HTTP ${latest.status}`);
  reports = [await latest.json()];
  currentIndex = 0;
}

async function refresh() {
  const [, status] = await Promise.all([loadReport(), loadDataStatus()]);
  renderReport(status);
}

function switchView(view) {
  document.querySelectorAll("[data-view-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.viewPanel === view));
  document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
}

byId("refreshButton").addEventListener("click", refresh);
byId("reportDateSelect").addEventListener("change", (event) => {
  currentIndex = Number(event.target.value);
  activePlanOrder = null;
  loadDataStatus().then(renderReport).catch(showLoadError);
});
byId("prevDayButton").addEventListener("click", () => {
  currentIndex = Math.max(0, currentIndex - 1);
  activePlanOrder = null;
  loadDataStatus().then(renderReport).catch(showLoadError);
});
byId("nextDayButton").addEventListener("click", () => {
  currentIndex = Math.min(reports.length - 1, currentIndex + 1);
  activePlanOrder = null;
  loadDataStatus().then(renderReport).catch(showLoadError);
});
byId("holdingSearch").addEventListener("input", () => renderHoldings(currentPayload().review || {}));
byId("tradeActionFilter").addEventListener("change", () => renderTrades(currentPayload().review || {}));
byId("planActionFilter").addEventListener("change", () => {
  activePlanOrder = null;
  renderPlan(currentPayload().next_plan || {});
  renderFactorDrawer(null);
});
document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});
document.querySelectorAll("[data-chart-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    chartMode = button.dataset.chartMode;
    document.querySelectorAll("[data-chart-mode]").forEach((item) => item.classList.toggle("active", item === button));
    renderGlobalChart();
  });
});

function showLoadError(error) {
  document.body.insertAdjacentHTML("beforeend", `<div class="panel">加载工作台失败：${esc(error.message)}</div>`);
}

refresh().catch(showLoadError);
