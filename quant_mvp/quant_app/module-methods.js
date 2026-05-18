const methodLibrary = {
  selection: [
    {
      name: "多因子动量评分（当前使用）",
      summary: "把 A 股股票池先做可交易过滤，再用动量、趋势、流动性和波动率合成一个综合分数，取排名靠前的股票进入候选池。",
      principle: [
        "动量假设：过去一段时间持续上涨且成交活跃的股票，短期更可能延续强势。",
        "趋势确认：20 日均线相对 60 日均线越强，说明价格结构越偏向上行。",
        "风险约束：波动率过高会扣分，避免只追极端波动的票。",
      ],
      inputOutput: [
        "输入：SQLite 中每只股票截至复盘日的日线行情。",
        "输出：Top N 候选股票、目标仓位、因子指标和入选原因。",
      ],
      prosCons: [
        "优点：逻辑透明，日报里能解释每只股票为什么入选。",
        "限制：偏趋势跟随，震荡市可能频繁换股。",
      ],
      code: "quant_core/strategy/stock_selector.py",
    },
    {
      name: "均线突破过滤",
      summary: "先要求价格站上关键均线，再按突破强度排序，适合想减少弱势票进入候选池的情况。",
      principle: [
        "价格高于 20 日和 60 日均线时，认为中短期趋势较健康。",
        "突破幅度越大，说明当前价格相对历史成本越强。",
        "成交额过滤用于避免流动性太弱的假突破。",
      ],
      inputOutput: [
        "输入：收盘价、20 日均线、60 日均线、成交额。",
        "输出：突破候选池和突破强度排名。",
      ],
      prosCons: [
        "优点：更容易避开长期下跌中的反弹票。",
        "限制：启动早期可能还没完全站上均线，会错过一部分初段行情。",
      ],
      code: "可作为 stock_selector.py 的 alternate selector 扩展",
    },
    {
      name: "低波动稳健池",
      summary: "把低波动和稳定上涨放在更高权重，适合希望回撤更平滑的模拟组合。",
      principle: [
        "波动率越低，组合净值曲线通常越平滑。",
        "仍保留动量指标，避免选到只是横盘不动的股票。",
        "通过行业或个股数量限制减少集中暴露。",
      ],
      inputOutput: [
        "输入：收益率序列、波动率、成交额、趋势指标。",
        "输出：低波动候选股和较保守的目标仓位。",
      ],
      prosCons: [
        "优点：更适合长期模拟观察和风险控制。",
        "限制：强趋势行情里收益可能不如动量模型激进。",
      ],
      code: "可作为 risk-aware selector 扩展",
    },
  ],
  evaluation: [
    {
      name: "因子贡献拆解（当前使用）",
      summary: "把入选股票的每个因子单独列出来，解释分数来自哪里，而不是只显示 rank 或 technical_score。",
      principle: [
        "分数由 20 日动量、60 日动量、均线趋势、成交额流动性、低波动等指标共同组成。",
        "每个指标保留原始数值，日报和功能页都能回看具体原因。",
        "未入选股票也记录过滤原因，例如历史不足、流动性不足、停牌或 ST。",
      ],
      inputOutput: [
        "输入：选股模块输出的 stock_pool 和 rejected_symbols。",
        "输出：单股解释、Top 5 因子对比、过滤统计。",
      ],
      prosCons: [
        "优点：最适合学习系统逻辑，能直接看懂每只股票的入选理由。",
        "限制：解释依赖规则因子，暂时不是自然语言大模型自动推理。",
      ],
      code: "quant_core/agent/daily_runner.py + stock_selector.py",
    },
    {
      name: "横截面排名解释",
      summary: "把一只股票放到当天所有可交易股票里比较，看它每个因子处于市场什么位置。",
      principle: [
        "同一天比较所有股票，比单看绝对收益率更能体现相对强弱。",
        "排名越靠前，说明该因子在市场中越突出。",
        "适合解释为什么某只票能进 Top N，另一只票不能进。",
      ],
      inputOutput: [
        "输入：当天全市场因子矩阵。",
        "输出：每个因子的市场分位数和排名。",
      ],
      prosCons: [
        "优点：解释更直观，能看到相对市场的位置。",
        "限制：需要保存更多中间因子数据。",
      ],
      code: "可扩展为 factor_explainer.py",
    },
    {
      name: "风险过滤解释",
      summary: "专门解释股票为什么被排除，包括停牌、ST、成交额不足、历史长度不足、波动异常等。",
      principle: [
        "先判断股票是否有资格进入评分池，再做打分。",
        "过滤原因要比综合分数更早出现，因为不可交易股票不能进入策略。",
        "把过滤统计聚合后，可以判断数据质量和市场可交易性。",
      ],
      inputOutput: [
        "输入：股票元数据、行情完整度、成交额和状态标记。",
        "输出：过滤原因字典和原因计数。",
      ],
      prosCons: [
        "优点：排查数据和策略边界很方便。",
        "限制：不会对已过滤股票继续做收益预测。",
      ],
      code: "stock_selector.py 的过滤阶段",
    },
  ],
  strategy: [
    {
      name: "等权目标仓位（当前使用）",
      summary: "从候选池选 Top N，给每只股票接近相同的目标仓位，并保留现金缓冲。",
      principle: [
        "不预测哪只股票一定最好，先用等权降低单票判断错误的影响。",
        "组合总股票仓位默认不超过 95%，保留现金用于手续费和调仓缓冲。",
        "不在新候选池里的旧持仓会生成卖出计划。",
      ],
      inputOutput: [
        "输入：今日收盘后生成的候选池、当前持仓和现金。",
        "输出：明日开盘执行的买入、卖出、目标仓位订单。",
      ],
      prosCons: [
        "优点：简单稳定，适合 MVP 阶段验证完整流程。",
        "限制：没有把分数高低转成更细的仓位差异。",
      ],
      code: "quant_core/strategy/portfolio_planner.py",
    },
    {
      name: "分数加权仓位",
      summary: "股票分数越高，目标仓位越高，但仍受单票上限和总仓位上限约束。",
      principle: [
        "把选股分数转换成仓位权重，让更强信号获得更多资金。",
        "使用单票上限避免组合过度集中在一只股票。",
        "低分但仍入选的股票可以获得较小仓位。",
      ],
      inputOutput: [
        "输入：候选股票分数、风险上限、账户资产。",
        "输出：按分数分配的目标仓位。",
      ],
      prosCons: [
        "优点：能表达信号强弱差异。",
        "限制：分数本身如果不稳定，仓位也会更敏感。",
      ],
      code: "可扩展 portfolio_planner.py 的 weighting 模式",
    },
    {
      name: "风控优先再平衡",
      summary: "先检查回撤、波动率和现金比例，满足风控后才允许新增买入。",
      principle: [
        "当组合回撤过大时，降低目标股票仓位。",
        "当波动率升高时，减少单票上限或提高现金比例。",
        "卖出释放现金优先于新增买入。",
      ],
      inputOutput: [
        "输入：净值曲线、当前仓位、候选池、风险阈值。",
        "输出：更保守的调仓计划或暂停买入计划。",
      ],
      prosCons: [
        "优点：更贴近真实资金管理。",
        "限制：需要更完善的风险参数和长期验证。",
      ],
      code: "可扩展 risk_manager.py",
    },
  ],
  data: [
    {
      name: "CSV + SQLite 增量缓存（当前使用）",
      summary: "免费接口下载来的股票日线先落 CSV，再导入 SQLite，前端和回测统一读取本地数据。",
      principle: [
        "CSV 适合断点续传和人工检查，SQLite 适合快速查询和去重。",
        "SQLite 使用 symbol + date 作为唯一键，重复导入会更新而不是重复插入。",
        "本地缓存减少免费接口请求压力，也避免每次回测都重新下载。",
      ],
      inputOutput: [
        "输入：免费行情接口返回的 A 股日线和指数日线。",
        "输出：market_data.sqlite、symbols CSV、下载状态 JSON。",
      ],
      prosCons: [
        "优点：免费、可恢复、查询比扫全量 CSV 更快。",
        "限制：首次下载全市场三年数据会比较久。",
      ],
      code: "quant_core/data/sqlite_store.py + scripts/download_*.py",
    },
    {
      name: "纯 CSV 文件缓存",
      summary: "每只股票一个 CSV 文件，不使用数据库，适合最简单的数据检查和迁移。",
      principle: [
        "文件结构直观，任何表格工具都能打开。",
        "按股票分文件，单只股票更新失败不会影响其他股票。",
        "回测时需要合并或批量读取多个文件。",
      ],
      inputOutput: [
        "输入：股票代码列表和免费接口数据。",
        "输出：symbols/<symbol>.csv 文件集合。",
      ],
      prosCons: [
        "优点：最容易理解和人工排错。",
        "限制：大规模按日期查询会慢，重复扫描文件成本高。",
      ],
      code: "quant_workspace/data/symbols/*.csv",
    },
    {
      name: "即时接口读取",
      summary: "运行策略时直接调用免费接口，不提前落库。",
      principle: [
        "每次运行都请求最新数据，减少本地存储管理。",
        "适合少量股票或临时验证。",
        "全市场回测会受接口速度、失败率和限频影响。",
      ],
      inputOutput: [
        "输入：当前运行需要的股票代码和日期范围。",
        "输出：内存中的行情 DataFrame 或列表。",
      ],
      prosCons: [
        "优点：实现简单，数据较新。",
        "限制：不适合稳定批量回测，也不利于复现历史结果。",
      ],
      code: "可作为 data_provider 的实时模式",
    },
  ],
  execution: [
    {
      name: "次日开盘价成交（当前使用）",
      summary: "昨天收盘后生成计划，今天收盘后按今天开盘价回放执行，符合你设定的按天模拟交易流程。",
      principle: [
        "策略只能使用昨天及之前的数据做计划，避免未来函数。",
        "执行价格固定为今天开盘价，不使用盘中价格。",
        "先卖出再买入，释放现金后再计算可买数量。",
      ],
      inputOutput: [
        "输入：昨日计划、今日开盘价、当前账户现金和持仓。",
        "输出：今日交易记录、跳过订单、更新后的账户状态。",
      ],
      prosCons: [
        "优点：时间顺序清楚，适合日频模拟交易。",
        "限制：无法模拟盘中触发和盘口冲击。",
      ],
      code: "quant_core/trading/simulator.py",
    },
    {
      name: "含滑点和手续费模拟",
      summary: "在开盘价基础上加入滑点、佣金、印花税等交易成本，更接近真实交易。",
      principle: [
        "买入价可以略高于开盘价，卖出价可以略低于开盘价。",
        "佣金和印花税会降低真实收益。",
        "流动性差的股票可以设置更高滑点。",
      ],
      inputOutput: [
        "输入：订单、开盘价、成交额、滑点参数、费率参数。",
        "输出：扣除成本后的成交金额和账户变化。",
      ],
      prosCons: [
        "优点：回测结果更保守。",
        "限制：滑点参数需要根据真实交易经验校准。",
      ],
      code: "simulator.py 的 cost/slippage 扩展",
    },
    {
      name: "涨跌停约束执行",
      summary: "如果股票涨停则不买入，跌停则不卖出，避免模拟出真实市场无法成交的订单。",
      principle: [
        "A 股存在涨跌停限制，部分订单即使有计划也无法成交。",
        "系统把无法成交的订单记录到 skipped_orders。",
        "跳过原因会进入日报，方便复盘交易计划是否可执行。",
      ],
      inputOutput: [
        "输入：今日开盘价、涨跌停状态、订单方向。",
        "输出：成交订单或跳过原因。",
      ],
      prosCons: [
        "优点：更符合 A 股交易制度。",
        "限制：当前是日线级模拟，不能刻画开盘后是否打开涨跌停。",
      ],
      code: "simulator.py 的 execution guard",
    },
  ],
};

function renderMethod(method) {
  return `
    <div class="method-summary">${method.summary}</div>
    <div class="method-grid">
      <div class="method-block">
        <h3>核心原理</h3>
        <ul class="method-list">${method.principle.map((item) => `<li>${item}</li>`).join("")}</ul>
      </div>
      <div class="method-block">
        <h3>输入与输出</h3>
        <ul class="method-list">${method.inputOutput.map((item) => `<li>${item}</li>`).join("")}</ul>
      </div>
      <div class="method-block">
        <h3>优点与限制</h3>
        <ul class="method-list">${method.prosCons.map((item) => `<li>${item}</li>`).join("")}</ul>
      </div>
      <div class="method-block">
        <h3>程序位置</h3>
        <p class="method-code"><code>${method.code}</code></p>
      </div>
    </div>
  `;
}

document.querySelectorAll("[data-method-page]").forEach((panel) => {
  const methods = methodLibrary[panel.dataset.methodPage] || [];
  const select = panel.querySelector(".method-select");
  const content = panel.querySelector(".method-content");
  if (!methods.length || !select || !content) return;

  select.innerHTML = methods.map((method, index) => `<option value="${index}">${method.name}</option>`).join("");
  const update = () => {
    content.innerHTML = renderMethod(methods[Number(select.value) || 0]);
  };
  select.addEventListener("change", update);
  update();
});
