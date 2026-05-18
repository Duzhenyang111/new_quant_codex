const reportsUrl = "../quant_workspace/backtests/latest_year_backtest.json";
const statusUrl = "../quant_workspace/data/status.json";
const manifestUrl = "../quant_workspace/data/symbol_manifest.json";
const indicesUrl = "../quant_workspace/data/indices.csv";
const symbolBaseUrl = "../quant_workspace/data/symbols";
const initialCapital = 100000;

let reports = [];
let symbols = [];
let indexRows = [];
let chartMode = "day";
let selectedIndex = "000001.SH";

const money = (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
const pct = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;
const price = (value) => Number(value || 0).toFixed(2);

function pathFor(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
}

function scale(value, min, max, outMin, outMax) {
  if (max === min) return (outMin + outMax) / 2;
  return outMax - ((value - min) / (max - min)) * (outMax - outMin);
}

function parseCsv(text) {
  const [headerLine, ...lines] = text.trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines.filter(Boolean).map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  });
}

function groupKey(date) {
  if (chartMode === "year") return date.slice(0, 4);
  if (chartMode === "month") return date.slice(0, 7);
  return date;
}

function rowsForSelectedIndex() {
  return indexRows
    .filter((row) => row.symbol === selectedIndex)
    .map((row) => ({
      ...row,
      open: Number(row.open || 0),
      close: Number(row.close || 0),
      high: Number(row.high || 0),
      low: Number(row.low || 0),
      daily_return: Number(row.daily_return || 0),
      volume: Number(row.volume || 0),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

function indexByDate() {
  return new Map(rowsForSelectedIndex().map((row) => [row.date, row]));
}

function aggregateReports() {
  const buckets = new Map();
  const indexMap = indexByDate();
  for (const item of reports) {
    const review = item.review || {};
    const date = review.trade_date || "";
    const indexRow = indexMap.get(date);
    const key = groupKey(date);
    if (!buckets.has(key)) {
      buckets.set(key, {
        label: key,
        startDate: date,
        endDate: date,
        equityEnd: Number(review.total_assets || 0),
        indexStart: indexRow?.open || indexRow?.close || 0,
        indexEnd: indexRow?.close || 0,
        dailyIndexReturn: indexRow?.daily_return || 0,
        count: 0,
      });
    }
    const bucket = buckets.get(key);
    bucket.endDate = date;
    bucket.equityEnd = Number(review.total_assets || 0);
    if (indexRow) {
      if (!bucket.indexStart) bucket.indexStart = indexRow.open || indexRow.close;
      bucket.indexEnd = indexRow.close;
      bucket.dailyIndexReturn = indexRow.daily_return;
    }
    bucket.count += 1;
  }
  const first = [...buckets.values()].find((bucket) => bucket.indexEnd || bucket.indexStart);
  const baseClose = first?.indexStart || first?.indexEnd || 0;
  return [...buckets.values()].map((bucket) => ({
    ...bucket,
    accountCumReturn: Number(bucket.equityEnd || 0) / initialCapital - 1,
    indexCumReturn: baseClose && bucket.indexEnd ? bucket.indexEnd / baseClose - 1 : 0,
    indexPeriodReturn: bucket.indexStart && bucket.indexEnd ? bucket.indexEnd / bucket.indexStart - 1 : bucket.dailyIndexReturn,
  }));
}

function tooltip(id, wrapId, event, html) {
  const node = document.getElementById(id);
  const wrap = document.getElementById(wrapId).getBoundingClientRect();
  node.hidden = false;
  node.innerHTML = html;
  node.style.left = `${Math.min(event.clientX - wrap.left + 14, wrap.width - 245)}px`;
  node.style.top = `${Math.max(event.clientY - wrap.top - 18, 12)}px`;
}

function hideTooltip(id) {
  document.getElementById(id).hidden = true;
}

function selectedIndexName() {
  return rowsForSelectedIndex()[0]?.name || selectedIndex;
}

function renderKpis(status) {
  const latest = reports.at(-1)?.review || {};
  const latestAssets = Number(latest.total_assets || 0);
  const selectedRows = rowsForSelectedIndex();
  const latestIndex = selectedRows.find((row) => row.date === latest.trade_date) || selectedRows.at(-1) || {};
  document.getElementById("latestAssets").textContent = money(latestAssets);
  document.getElementById("latestDate").textContent = latest.trade_date || "--";
  document.getElementById("cumulativeReturn").textContent = pct(latestAssets / initialCapital - 1);
  document.getElementById("latestIndexName").textContent = latestIndex.name || selectedIndexName();
  document.getElementById("latestIndexReturn").textContent = pct(latestIndex.daily_return || 0);
  document.getElementById("indexCoverage").textContent = `${new Set(indexRows.map((row) => row.symbol)).size} 条指数`;
  document.getElementById("dataRange").textContent = `${status.start_date || "--"} 至 ${status.end_date || "--"}`;
}

function renderOverviewChart() {
  const svg = document.getElementById("overviewChart");
  const data = aggregateReports();
  const indexName = selectedIndexName();
  if (!data.length) {
    svg.innerHTML = "";
    return;
  }
  const width = 980;
  const height = 330;
  const pad = { left: 70, right: 36, top: 34, bottom: 58 };
  const account = data.map((item) => item.accountCumReturn * 100);
  const market = data.map((item) => item.indexCumReturn * 100);
  const minValue = Math.min(...account, ...market, -1);
  const maxValue = Math.max(...account, ...market, 1);
  const x = (index) => pad.left + (index / Math.max(1, data.length - 1)) * (width - pad.left - pad.right);
  const accountPoints = data.map((item, index) => ({ x: x(index), y: scale(item.accountCumReturn * 100, minValue, maxValue, pad.top, height - pad.bottom) }));
  const marketPoints = data.map((item, index) => ({ x: x(index), y: scale(item.indexCumReturn * 100, minValue, maxValue, pad.top, height - pad.bottom) }));
  svg.innerHTML = `
    <line class="axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" />
    <line class="axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" />
    <line class="grid" x1="${pad.left}" y1="${pad.top}" x2="${width - pad.right}" y2="${pad.top}" />
    <line class="grid" x1="${pad.left}" y1="${(pad.top + height - pad.bottom) / 2}" x2="${width - pad.right}" y2="${(pad.top + height - pad.bottom) / 2}" />
    <path class="equity-line" d="${pathFor(accountPoints)}" />
    <path class="market-line" d="${pathFor(marketPoints)}" />
    ${data.map((item, index) => {
      const startX = index === 0 ? pad.left : (x(index - 1) + x(index)) / 2;
      const endX = index === data.length - 1 ? width - pad.right : (x(index) + x(index + 1)) / 2;
      return `
      <rect class="hit overview-hit" data-index="${index}" x="${startX}" y="${pad.top}" width="${endX - startX}" height="${height - pad.top - pad.bottom}" />
      <line class="hover-line" data-hover-line="${index}" x1="${accountPoints[index].x}" y1="${pad.top}" x2="${accountPoints[index].x}" y2="${height - pad.bottom}" />
      ${index % Math.max(1, Math.floor(data.length / 10)) === 0 || index === data.length - 1 ? `<text class="label" x="${accountPoints[index].x}" y="${height - 22}" text-anchor="middle">${item.label.slice(5) || item.label}</text>` : ""}
    `}).join("")}
    <circle id="accountFocusDot" class="focus-dot" cx="0" cy="0" r="4" stroke="#38bdf8" />
    <circle id="marketFocusDot" class="focus-dot" cx="0" cy="0" r="4" stroke="#22c55e" />
    <text class="legend" x="${pad.left}" y="24">账户累计收益 ${account.at(-1).toFixed(2)}%</text>
    <text class="legend" x="${pad.left + 180}" y="24">${indexName}累计收益 ${market.at(-1).toFixed(2)}%</text>
  `;
  svg.querySelectorAll("[data-index]").forEach((node) => {
    node.addEventListener("mousemove", (event) => {
      const item = data[Number(node.dataset.index)];
      const index = Number(node.dataset.index);
      const accountDot = svg.querySelector("#accountFocusDot");
      const marketDot = svg.querySelector("#marketFocusDot");
      accountDot.setAttribute("cx", accountPoints[index].x);
      accountDot.setAttribute("cy", accountPoints[index].y);
      marketDot.setAttribute("cx", marketPoints[index].x);
      marketDot.setAttribute("cy", marketPoints[index].y);
      accountDot.classList.add("visible");
      marketDot.classList.add("visible");
      svg.querySelectorAll("[data-hover-line]").forEach((line) => line.classList.toggle("visible", line.dataset.hoverLine === node.dataset.index));
      tooltip("overviewTooltip", "overviewWrap", event, `
        <strong>${item.label}</strong>
        <span>${item.startDate}${item.startDate !== item.endDate ? ` 至 ${item.endDate}` : ""}</span>
        <span>总资产：${money(item.equityEnd)}</span>
        <span>账户累计收益：${pct(item.accountCumReturn)}</span>
        <span>${indexName}累计收益：${pct(item.indexCumReturn)}</span>
        <span>${indexName}区间涨跌：${pct(item.indexPeriodReturn)}</span>
        <span>指数收盘：${price(item.indexEnd)}</span>
      `);
    });
    node.addEventListener("mouseleave", () => {
      svg.querySelectorAll("[data-hover-line]").forEach((line) => line.classList.remove("visible"));
      svg.querySelectorAll(".focus-dot").forEach((dot) => dot.classList.remove("visible"));
      hideTooltip("overviewTooltip");
    });
  });
}

function renderBreadthChart() {
  const svg = document.getElementById("breadthChart");
  const data = reports.map((item) => item.review || {});
  const width = 520;
  const height = 260;
  const pad = { left: 42, right: 20, top: 24, bottom: 42 };
  const barWidth = Math.max(16, (width - pad.left - pad.right) / Math.max(1, data.length) - 8);
  svg.innerHTML = `
    <line class="axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" />
    ${data.map((review, index) => {
      const breadth = review.breadth || review.market || {};
      const total = Math.max(1, Number(breadth.sample_count || 0));
      const x = pad.left + index * ((width - pad.left - pad.right) / Math.max(1, data.length));
      const upH = (breadth.advance_count || 0) / total * (height - pad.top - pad.bottom);
      const downH = (breadth.decline_count || 0) / total * (height - pad.top - pad.bottom);
      const flatH = Math.max(0, height - pad.top - pad.bottom - upH - downH);
      const base = height - pad.bottom;
      return `
        <rect class="bar-up" x="${x}" y="${base - upH}" width="${barWidth}" height="${upH}" />
        <rect class="bar-flat" x="${x}" y="${base - upH - flatH}" width="${barWidth}" height="${flatH}" />
        <rect class="bar-down" x="${x}" y="${base - upH - flatH - downH}" width="${barWidth}" height="${downH}" />
        <text class="label" x="${x + barWidth / 2}" y="${height - 16}" text-anchor="middle">${review.trade_date?.slice(5) || ""}</text>
      `;
    }).join("")}
    <text class="legend" x="${pad.left}" y="18">本地股票池宽度</text>
  `;
}

async function loadStock(symbol) {
  const response = await fetch(`${symbolBaseUrl}/${symbol}.csv?t=${Date.now()}`);
  if (!response.ok) throw new Error(`无法读取 ${symbol}`);
  return parseCsv(await response.text());
}

function renderStockChart(symbol, rows) {
  const svg = document.getElementById("stockChart");
  const data = rows.slice(-240).map((row) => ({ date: row.date, close: Number(row.close), volume: Number(row.volume || 0) }));
  const width = 520;
  const height = 260;
  const pad = { left: 48, right: 18, top: 24, bottom: 42 };
  const closes = data.map((item) => item.close);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const x = (index) => pad.left + (index / Math.max(1, data.length - 1)) * (width - pad.left - pad.right);
  const points = data.map((item, index) => ({ x: x(index), y: scale(item.close, minClose, maxClose, pad.top, height - pad.bottom) }));
  svg.innerHTML = `
    <line class="axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" />
    <line class="axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" />
    <path class="stock-line" d="${pathFor(points)}" />
    ${data.map((item, index) => index % Math.max(1, Math.floor(data.length / 8)) === 0 ? `<text class="label" x="${x(index)}" y="${height - 16}" text-anchor="middle">${item.date.slice(5)}</text>` : "").join("")}
    ${points.map((point, index) => `<circle class="hit" data-stock-index="${index}" cx="${point.x}" cy="${point.y}" r="10" />`).join("")}
    <text class="legend" x="${pad.left}" y="18">${symbol} 收盘价趋势</text>
  `;
  svg.querySelectorAll("[data-stock-index]").forEach((node) => {
    node.addEventListener("mousemove", (event) => {
      const item = data[Number(node.dataset.stockIndex)];
      tooltip("stockTooltip", "stockWrap", event, `
        <strong>${symbol}</strong>
        <span>日期：${item.date}</span>
        <span>收盘价：${price(item.close)}</span>
        <span>成交量：${money(item.volume)}</span>
      `);
    });
    node.addEventListener("mouseleave", () => hideTooltip("stockTooltip"));
  });
}

async function renderSelectedStock() {
  const symbol = document.getElementById("symbolSelect").value;
  if (!symbol) return;
  const rows = await loadStock(symbol);
  renderStockChart(symbol, rows);
}

function renderSymbolSelect() {
  const select = document.getElementById("symbolSelect");
  const preferred = ["600519.SH", "000001.SZ", "600396.SH", "603629.SH", "300209.SZ"];
  const existing = new Set(symbols.map((item) => item.symbol));
  const ordered = [
    ...preferred.filter((symbol) => existing.has(symbol)).map((symbol) => symbols.find((item) => item.symbol === symbol)),
    ...symbols.filter((item) => !preferred.includes(item.symbol)).slice(0, 300),
  ].filter(Boolean);
  select.innerHTML = ordered.map((item) => `<option value="${item.symbol}">${item.symbol} (${item.rows})</option>`).join("");
}

function renderIndexSelect() {
  const select = document.getElementById("indexSelect");
  const options = [...new Map(indexRows.map((row) => [row.symbol, row])).values()];
  select.innerHTML = options.map((item) => `<option value="${item.symbol}">${item.name} ${item.symbol}</option>`).join("");
  select.value = selectedIndex;
}

function renderStatus(status) {
  document.getElementById("dataSource").textContent = `数据源：${status.source || "--"} + akshare_free_index_daily`;
  document.getElementById("statusRows").textContent = `股票行情行数：${money(status.merged_rows || status.rows)}`;
  document.getElementById("statusSymbols").textContent = `可选股票：${symbols.length}`;
  document.getElementById("statusDateRange").textContent = `日期范围：${status.start_date || "--"} 至 ${status.end_date || "--"}`;
  document.getElementById("statusNote").textContent = `指数行数：${indexRows.length}，当前大盘：${selectedIndexName()}`;
}

async function loadAll() {
  const [reportResponse, statusResponse, manifestResponse, indexResponse] = await Promise.all([
    fetch(`${reportsUrl}?t=${Date.now()}`),
    fetch(`${statusUrl}?t=${Date.now()}`),
    fetch(`${manifestUrl}?t=${Date.now()}`),
    fetch(`${indicesUrl}?t=${Date.now()}`),
  ]);
  const reportPayload = await reportResponse.json();
  reports = Array.isArray(reportPayload) ? reportPayload : reportPayload.reports || [];
  const status = await statusResponse.json();
  symbols = (await manifestResponse.json()).symbols || [];
  indexRows = parseCsv(await indexResponse.text());
  renderIndexSelect();
  renderKpis(status);
  renderOverviewChart();
  renderBreadthChart();
  renderSymbolSelect();
  renderStatus(status);
  await renderSelectedStock();
}

document.getElementById("refreshButton").addEventListener("click", loadAll);
document.getElementById("symbolSelect").addEventListener("change", renderSelectedStock);
document.getElementById("indexSelect").addEventListener("change", (event) => {
  selectedIndex = event.target.value;
  renderKpis({ start_date: indexRows[0]?.date, end_date: indexRows.at(-1)?.date });
  renderOverviewChart();
  renderStatus({ source: "eastmoney_free_api", start_date: indexRows[0]?.date, end_date: indexRows.at(-1)?.date });
});
document.querySelectorAll("[data-chart-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    chartMode = button.dataset.chartMode;
    document.querySelectorAll("[data-chart-mode]").forEach((item) => item.classList.toggle("active", item === button));
    renderOverviewChart();
  });
});

loadAll().catch((error) => {
  document.body.insertAdjacentHTML("beforeend", `<div class="panel">看板加载失败：${error.message}</div>`);
});

