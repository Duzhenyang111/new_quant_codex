const backtestUrl = "../quant_workspace/backtests/latest_year_backtest.json";
const statusUrl = "../quant_workspace/data/status.json";
const sqliteStatusUrl = "../quant_workspace/data/sqlite_status.json";
const bulkStatusUrl = "../quant_workspace/data/baostock_bulk_status.json";

const fmtMoney = (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
const fmtPct = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;
const fmtPrice = (value) => Number(value || 0).toFixed(2);

async function loadJson(url) {
  const response = await fetch(`${url}?t=${Date.now()}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function latestReport() {
  const payload = await loadJson(backtestUrl);
  return {
    payload,
    latest: payload.reports?.at(-1) || {},
    summary: payload.summary || {},
  };
}

function output(html) {
  document.getElementById("demoOutput").innerHTML = html;
}

function table(headers, rows) {
  return `
    <table>
      <thead><tr>${headers.map((item) => `<th>${item}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${row.map((item) => `<td>${item}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>
  `;
}

function metricsList(metrics = {}) {
  return [
    ["20日动量", fmtPct(metrics.momentum_20)],
    ["60日动量", fmtPct(metrics.momentum_60)],
    ["均线趋势", fmtPct(metrics.trend)],
    ["流动性", Number(metrics.liquidity || 0).toFixed(2)],
    ["波动率约", fmtPct(-Number(metrics.low_volatility || 0))],
  ];
}

async function runDemo(kind) {
  output("正在读取本地回测数据...");
  if (kind.startsWith("data-")) {
    await renderDataDemo(kind);
    return;
  }
  const { payload, latest, summary } = await latestReport();
  const review = latest.review || {};
  const plan = latest.next_plan || {};
  if (kind === "selection-latest") {
    const rows = (review.stock_pool || []).slice(0, 5).map((item, index) => [
      index + 1,
      item.symbol,
      Number(item.score || 0).toFixed(4),
      fmtPct(item.target_weight),
      item.reason || "",
    ]);
    output(`<p class="muted">交易日 ${review.trade_date} 的选股池。</p>${table(["排名", "股票", "分数", "目标仓位", "原因"], rows)}`);
  }
  if (kind === "selection-rejected") {
    const rejected = review.rejected_symbols || {};
    const counts = Object.values(rejected).reduce((acc, reason) => {
      acc[reason] = (acc[reason] || 0) + 1;
      return acc;
    }, {});
    const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([reason, count]) => [reason, count]);
    output(`<p class="muted">过滤原因统计，帮助理解哪些股票没有进入评分池。</p>${table(["过滤原因", "数量"], rows.slice(0, 10))}`);
  }
  if (kind === "evaluation-top") {
    const top = (review.stock_pool || [])[0];
    output(`
      <p><strong>${top.symbol}</strong> 是 ${review.trade_date} 的 Top 1 候选。</p>
      ${table(["指标", "数值"], metricsList(top.metrics))}
      <p class="muted">${top.reason || ""}</p>
    `);
  }
  if (kind === "evaluation-all") {
    const rows = (review.stock_pool || []).slice(0, 5).flatMap((item) =>
      metricsList(item.metrics).map(([name, value]) => [item.symbol, name, value]),
    );
    output(table(["股票", "因子", "数值"], rows));
  }
  if (kind === "strategy-plan") {
    const rows = (plan.orders || []).slice(0, 20).map((item) => [
      item.symbol,
      String(item.action || "").toUpperCase(),
      fmtPct(item.target_weight),
      Number(item.score || 0).toFixed(4),
      item.reason || "",
    ]);
    output(`<p class="muted">只展示前 20 条，完整计划在日报页。</p>${table(["股票", "方向", "目标仓位", "分数", "原因"], rows)}`);
  }
  if (kind === "strategy-risk") {
    const positions = Object.keys(summary.final_positions || {}).length;
    output(table(["项目", "当前值"], [
      ["初始资金", fmtMoney(summary.initial_cash)],
      ["期末资产", fmtMoney(summary.final_assets)],
      ["总收益", fmtPct(summary.total_return)],
      ["最大回撤", fmtPct(summary.max_drawdown)],
      ["最终持仓数量", positions],
    ]));
  }
  if (kind === "execution-trades") {
    const rows = (review.trades || []).map((trade) => [
      trade.symbol,
      String(trade.action || "").toUpperCase(),
      Number(trade.quantity || 0).toLocaleString("zh-CN"),
      fmtPrice(trade.price),
      fmtMoney(trade.amount),
      trade.reason || "",
    ]);
    output(`<p class="muted">交易日 ${review.trade_date}，按当日开盘价执行。</p>${rows.length ? table(["股票", "方向", "数量", "开盘价", "金额", "原因"], rows) : "当日无交易。"}`);
  }
  if (kind === "execution-skipped") {
    const skipped = review.skipped_orders || {};
    const rows = Object.entries(skipped).map(([symbol, reason]) => [symbol, reason]);
    output(rows.length ? table(["股票", "跳过原因"], rows) : "当日没有跳过订单。");
  }
}

async function renderDataDemo(kind) {
  if (kind === "data-status") {
    const [status, sqliteStatus, bulkStatus] = await Promise.allSettled([
      loadJson(statusUrl),
      loadJson(sqliteStatusUrl),
      loadJson(bulkStatusUrl),
    ]);
    const rows = [
      ["股票 CSV 行数", fmtMoney(status.value?.merged_rows || status.value?.rows)],
      ["SQLite 股票行数", fmtMoney(bulkStatus.value?.bars_rows || sqliteStatus.value?.bars_rows)],
      ["指数行数", fmtMoney(sqliteStatus.value?.index_rows || 2175)],
      ["本地股票数量", fmtMoney(bulkStatus.value?.initial_sqlite_symbols || status.value?.ok_symbols?.length)],
      ["最近更新", bulkStatus.value?.updated_at || status.value?.updated_at || "--"],
    ];
    output(table(["数据项", "值"], rows));
  }
  if (kind === "data-sample") {
    output(`
      <pre>quant_workspace/data/market_data.sqlite
├─ bars(symbol, date, open, high, low, close, volume, amount, flags...)
├─ indices(symbol, date, name, open, high, low, close, daily_return)
├─ symbols/&lt;symbol&gt;.csv
└─ backtests/latest_year_backtest.json</pre>
    `);
  }
}

document.querySelectorAll("[data-demo]").forEach((button) => {
  button.addEventListener("click", () => {
    runDemo(button.dataset.demo).catch((error) => output(`示例加载失败：${error.message}`));
  });
});
