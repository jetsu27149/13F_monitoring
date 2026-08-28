const state = {
  baseData: null,
  data: null,
  view: "overview",
  search: "",
  investors: ["all"],
  reportDate: "latest",
  quarterCache: {},
  changeIndex: null,
  status: "all",
  rowLimit: "24",
  holdingCategory: "equity",
  earningsCache: {},
  sort: {
    holdings: { key: "weight", direction: "desc" },
    changes: { key: "active_weight", direction: "desc" },
  },
};

const TICKER_ALIAS_BY_CUSIP = {
  "00724F101": ["ADBE"],
  "007903107": ["AMD"],
  "009066101": ["ABNB"],
  "009158106": ["APD"],
  "00187Y100": ["APG"],
  "00827B106": ["AFRM"],
  "013872106": ["AA"],
  "01609W102": ["BABA"],
  "02005N100": ["ALLY"],
  "02079K107": ["GOOG"],
  "02079K305": ["GOOGL"],
  "023135106": ["AMZN"],
  "025816109": ["AXP"],
  "036752103": ["ELV"],
  "037833100": ["AAPL"],
  "03769M106": ["APO"],
  "03831W108": ["APP"],
  "038169207": ["APLD"],
  "038222105": ["AMAT"],
  "040413205": ["ANET"],
  "044186104": ["ASH"],
  "060505104": ["BAC"],
  "09173B107": ["BITF"],
  "093712107": ["BE"],
  "09857L108": ["BKNG"],
  "101137107": ["BSX"],
  "110122108": ["BMY"],
  "11135F101": ["AVGO"],
  "11271J107": ["BN"],
  "125523100": ["CI"],
  "12662P108": ["CVI"],
  "13646K108": ["CP"],
  "136375102": ["CNI"],
  "14040H105": ["COF"],
  "144285103": ["CRS"],
  "146869102": ["CVNA"],
  "15135B101": ["CNC"],
  "166764100": ["CVX"],
  "184496107": ["CLH"],
  "18452B209": ["CLSK"],
  "191216100": ["KO"],
  "199908104": ["FIX"],
  "21037T109": ["CEG"],
  "21873S108": ["CRWV"],
  "21874A106": ["CORZ"],
  "219350105": ["GLW"],
  "22160K105": ["COST"],
  "22266T109": ["CPNG"],
  "23918K108": ["DVA"],
  "247361702": ["DAL"],
  "254687106": ["DIS"],
  "25809K105": ["DASH"],
  "26969P108": ["EXP"],
  "281020107": ["EIX"],
  "29273V100": ["ET"],
  "29444U700": ["EQIX"],
  "29362U104": ["ENTG"],
  "30303M102": ["META"],
  "31488V107": ["FERG"],
  "31428X106": ["FDX"],
  "36828A101": ["GEV"],
  "369604301": ["GE"],
  "37045V100": ["GM"],
  "372460105": ["GPC"],
  "437076102": ["HD"],
  "44267T102": ["HHH"],
  "451100101": ["IEP"],
  "457669307": ["INSM"],
  "458140100": ["INTC"],
  "46625H100": ["JPM"],
  "46090E103": ["QQQ"],
  "464287200": ["IVV"],
  "464287234": ["IEMG"],
  "46137V357": ["RSP"],
  "464286400": ["EWZ"],
  "464286772": ["EWY"],
  "464287655": ["IWM"],
  "501044101": ["KR"],
  "48242W106": ["KBR"],
  "500754106": ["KHC"],
  "50212V100": ["LPLA"],
  "512807306": ["LRCX"],
  "530909308": ["LLYVK", "LLYVA"],
  "536797103": ["LAD"],
  "55024U109": ["LITE"],
  "553368101": ["MP"],
  "580135101": ["MCD"],
  "58933Y105": ["MRK"],
  "576323109": ["MTZ"],
  "58155Q103": ["MCK"],
  "58733R102": ["MELI"],
  "594918104": ["MSFT"],
  "595112103": ["MU"],
  "60471A101": ["MIR"],
  "615369105": ["MCO"],
  "629377508": ["NRG"],
  "632307104": ["NTRA"],
  "650111107": ["NYT"],
  "655844108": ["NSC"],
  "67066G104": ["NVDA"],
  "674599105": ["OXY"],
  "68268W103": ["OMF"],
  "68389X105": ["ORCL"],
  "69331C108": ["PCG"],
  "69608A108": ["PLTR"],
  "71377A103": ["PFGC"],
  "718546104": ["PSX"],
  "74276R102": ["PRVA"],
  "75524B104": ["RBC"],
  "75886F107": ["REGN"],
  "76131D103": ["QSR"],
  "767292105": ["RIOT"],
  "77311W101": ["RKT"],
  "78462F103": ["SPY"],
  "78467X109": ["DIA"],
  "78409V104": ["SPGI"],
  "80004C200": ["SNDK"],
  "81141R100": ["SE"],
  "808513105": ["SCHW"],
  "82452J109": ["FOUR"],
  "824348106": ["SHW"],
  "829933100": ["SIRI"],
  "844741108": ["LUV"],
  "861012102": ["STM"],
  "867224107": ["SU"],
  "86765K109": ["SUN"],
  "874039100": ["TSM"],
  "87422Q109": ["TLN"],
  "872540109": ["TJX"],
  "87612E106": ["TGT"],
  "879369106": ["TFX"],
  "88033G407": ["THC"],
  "880770102": ["TER"],
  "88160R101": ["TSLA"],
  "90353T100": ["UBER"],
  "903731107": ["ULS"],
  "907818108": ["UNP"],
  "912008109": ["USFD"],
  "91307C102": ["UTHR"],
  "918284100": ["VSEC"],
  "92189F676": ["SMH"],
  "92343E102": ["VRSN"],
  "92537N108": ["VRT"],
  "92826C839": ["V"],
  "92840M102": ["VST"],
  "931142103": ["WMT"],
  "934423104": ["WBD"],
  "95082P105": ["WCC"],
  "958102AT2": ["WDC"],
  "983793100": ["XPO"],
  "984245100": ["YPF"],
  "G0403H108": ["AON"],
  "G0896C103": ["TBBB"],
  "G11448100": ["BTDR"],
  "G1467J104": ["CB"],
  "H1467J104": ["CB"],
  "G25457105": ["CRDO"],
  "G25508105": ["CRH"],
  "G29183103": ["ETN"],
  "G3398L118": ["FIHL"],
  "G4412G101": ["HLF"],
  "G61188127": ["LBTYK", "LBTYA"],
  "G66721104": ["NCLH"],
  "G87110105": ["FTI"],
  "G6683N103": ["NU"],
  "G96629103": ["WTW"],
  "L8681T102": ["SPOT"],
  "N07059210": ["ASML"],
  "N3168P101": ["FER"],
  "N62509109": ["NAMS"],
  "Q4982L109": ["IREN"],
};

const TICKER_ALIAS_BY_ISSUER = [
  [/ALPHABET INC/i, ["GOOG", "GOOGL"]],
  [/ISHARES.*RUSSELL 2000/i, ["IWM"]],
  [/INVESCO QQQ/i, ["QQQ"]],
  [/ISHARES.*BRAZIL/i, ["EWZ"]],
  [/ISHARES.*KOR/i, ["EWY"]],
  [/SPDR S&P 500|STATE STREET SPDR S&P 500/i, ["SPY"]],
  [/SPDR GOLD/i, ["GLD"]],
];

const KNOWN_TICKER_ALIASES = new Set(
  [
    ...Object.values(TICKER_ALIAS_BY_CUSIP).flat(),
    ...TICKER_ALIAS_BY_ISSUER.flatMap(([, tickers]) => tickers),
  ].map((ticker) => normalizeTickerQuery(ticker)),
);

const els = {
  dataStatus: document.querySelector("#dataStatus"),
  searchInput: document.querySelector("#searchInput"),
  investorFilter: document.querySelector("#investorFilter"),
  investorFilterButton: document.querySelector("#investorFilterButton"),
  investorFilterPanel: document.querySelector("#investorFilterPanel"),
  reportDateFilter: document.querySelector("#reportDateFilter"),
  statusFilter: document.querySelector("#statusFilter"),
  rowLimitFilter: document.querySelector("#rowLimitFilter"),
  categoryButtons: document.querySelectorAll(".category-button"),
  checkFilingsButton: document.querySelector("#checkFilingsButton"),
  filingCheckStatus: document.querySelector("#filingCheckStatus"),
  tabs: document.querySelectorAll(".tab"),
  views: {
    overview: document.querySelector("#overviewView"),
    investors: document.querySelector("#investorsView"),
    changes: document.querySelector("#changesView"),
    watchlist: document.querySelector("#watchlistView"),
    research: document.querySelector("#researchView"),
    readme: document.querySelector("#readmeView"),
  },
};

async function init() {
  bindEvents();
  try {
    const response = await fetch("../data/processed/dashboard.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.baseData = await response.json();
    state.data = state.baseData;
    populateInvestorFilter();
    populateReportDateFilter();
    render();
  } catch (error) {
    renderLoadError(error);
  }
}

function bindEvents() {
  els.searchInput.addEventListener("input", (event) => {
    state.search = normalizeTickerQuery(event.target.value);
    render();
  });
  els.investorFilterButton.addEventListener("click", (event) => {
    event.stopPropagation();
    els.investorFilterPanel.hidden = !els.investorFilterPanel.hidden;
  });
  els.investorFilterPanel.addEventListener("change", (event) => {
    if (!event.target.matches("input[type='checkbox']")) return;
    const checked = [...els.investorFilterPanel.querySelectorAll("input[type='checkbox']:checked")].map((input) => input.value);
    const nextSelection =
      event.target.value === "all" && event.target.checked
        ? ["all"]
        : checked.filter((value) => value !== "all");
    state.investors = normalizeInvestorSelection(nextSelection);
    syncInvestorFilterSelection();
    resetFilingCheckStatus();
    render();
  });
  els.statusFilter.addEventListener("change", (event) => {
    state.status = event.target.value;
    render();
  });
  els.reportDateFilter.addEventListener("change", async (event) => {
    await loadReportDate(event.target.value);
  });
  els.rowLimitFilter.addEventListener("change", (event) => {
    state.rowLimit = event.target.value;
    render();
  });
  els.categoryButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.holdingCategory = button.dataset.category;
      els.categoryButtons.forEach((item) => item.classList.toggle("active", item === button));
      render();
    });
  });
  els.checkFilingsButton?.addEventListener("click", checkLatestFilings);
  els.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      state.view = tab.dataset.view;
      els.tabs.forEach((item) => item.classList.toggle("active", item === tab));
      Object.entries(els.views).forEach(([name, view]) => view.classList.toggle("active", name === state.view));
      render();
    });
  });
  document.addEventListener("click", (event) => {
    if (!els.investorFilter.contains(event.target)) {
      els.investorFilterPanel.hidden = true;
    }
    const earningsButton = event.target.closest("[data-earnings-symbol]");
    if (earningsButton) {
      handleEarningsLookup(earningsButton);
      return;
    }
    const earningsBatchButton = event.target.closest("[data-earnings-load-all]");
    if (earningsBatchButton) {
      handleVisibleEarningsLookups(earningsBatchButton);
      return;
    }
    const button = event.target.closest("[data-sort-table]");
    if (!button) return;
    const table = button.dataset.sortTable;
    const key = button.dataset.sortKey;
    toggleSort(table, key);
    render();
  });
}

function populateInvestorFilter() {
  const options = [
    `<label class="multi-select-option"><input type="checkbox" value="all" /> <span>All investors</span></label>`,
  ]
    .concat(
      state.data.investors.map(
        (investor) => `
          <label class="multi-select-option">
            <input type="checkbox" value="${escapeAttribute(investor.slug)}" />
            <span>${escapeHtml(investor.investor)}</span>
          </label>
        `,
      ),
    )
    .join("");
  els.investorFilterPanel.innerHTML = options;
  syncInvestorFilterSelection();
}

function populateReportDateFilter() {
  const dates = [...new Set((state.baseData?.reports || []).map((report) => report.report_date).filter(Boolean))].sort().reverse();
  const options = [
    `<option value="latest">Latest available</option>`,
    ...dates.map((date) => `<option value="${escapeAttribute(date)}">${escapeHtml(reportQuarterLabel(date))}</option>`),
  ];
  els.reportDateFilter.innerHTML = options.join("");
  els.reportDateFilter.value = state.reportDate;
}

async function loadReportDate(reportDate) {
  state.reportDate = reportDate || "latest";
  els.reportDateFilter.value = state.reportDate;
  if (state.reportDate === "latest") {
    state.data = state.baseData;
    state.changeIndex = null;
    render();
    return;
  }

  if (state.quarterCache[state.reportDate]) {
    state.data = mergeQuarterData(state.quarterCache[state.reportDate]);
    state.changeIndex = null;
    render();
    return;
  }

  const previousStatus = els.dataStatus.innerHTML;
  els.dataStatus.textContent = `Loading ${reportQuarterLabel(state.reportDate)}...`;
  els.reportDateFilter.disabled = true;
  try {
    const response = await fetch("/api/quarter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_date: state.reportDate }),
    });
    const payload = await response.json();
    if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
    state.quarterCache[state.reportDate] = payload;
    state.data = mergeQuarterData(payload);
    state.changeIndex = null;
    render();
  } catch (error) {
    els.dataStatus.innerHTML = previousStatus;
    alert(`Could not load ${reportQuarterLabel(state.reportDate)}. Start/restart the dashboard server with scripts/dashboard_server.py --port 8013.\n\n${error.message}`);
    state.reportDate = "latest";
    els.reportDateFilter.value = "latest";
    state.data = state.baseData;
    state.changeIndex = null;
    render();
  } finally {
    els.reportDateFilter.disabled = false;
  }
}

function mergeQuarterData(payload) {
  return {
    ...state.baseData,
    metadata: {
      ...(state.baseData?.metadata || {}),
      ...(payload.metadata || {}),
    },
    investors: payload.investors || [],
    holdings: payload.holdings || [],
    changes: payload.changes || [],
    watchlist: payload.watchlist || [],
    reports: state.baseData?.reports || [],
  };
}

function resetFilingCheckStatus() {
  if (!els.filingCheckStatus) return;
  els.filingCheckStatus.textContent = "Check SEC and download new filings";
  els.filingCheckStatus.title = "";
}

function normalizeInvestorSelection(values) {
  const selected = values.filter(Boolean);
  if (!selected.length || selected.includes("all")) return ["all"];
  return [...new Set(selected)];
}

function syncInvestorFilterSelection() {
  const selected = new Set(state.investors);
  [...els.investorFilterPanel.querySelectorAll("input[type='checkbox']")].forEach((input) => {
    input.checked = selected.has(input.value);
  });
  els.investorFilterButton.textContent = investorSelectionLabel();
  els.investorFilterButton.title = selectedInvestors().map((investor) => investor.investor).join(", ");
}

function render() {
  const data = state.data;
  if (!data) return;

  const mode = data.metadata.mode === "sample" ? `<span class="mode-pill">Sample data</span>` : "";
  const reportContext =
    state.reportDate === "latest"
      ? "Latest available reports"
      : `Report quarter ${escapeHtml(reportQuarterLabel(state.reportDate))}`;
  els.dataStatus.innerHTML = `${formatDateTime(data.metadata.generated_at)} · ${reportContext} ${mode}`;

  if (state.view === "overview") renderOverview();
  if (state.view === "investors") renderInvestors();
  if (state.view === "changes") renderChanges();
  if (state.view === "watchlist") renderWatchlist();
  if (state.view === "research") renderResearch();
  if (state.view === "readme") renderReadme();
}

function renderOverview() {
  const investors = filteredInvestors();
  const holdings = filteredHoldings();
  const changes = filteredChanges();
  const displayedHoldings = limitRows(holdings);
  const totalValue = overviewMetricValue(holdings, changes);
  const latestReports = new Set(investors.map((item) => item.latest_report_date).filter(Boolean));
  const watchCount = filteredWatchlist().length;
  const warnings = state.data.metadata.errors || [];

  els.views.overview.innerHTML = `
    ${warnings.length ? `<div class="warning">${warningSummary(warnings)}</div>` : ""}
    <div class="metric-grid">
      ${metricCard(valueMetricLabel(), formatMoney(totalValue), valueMetricNote())}
      ${metricCard("Investors", formatNumber(investors.length), reportMetricNote(latestReports))}
      ${metricCard("Visible rows", formatNumber(displayedHoldings.length), `${formatNumber(holdings.length)} ${holdingMatchLabel()} matched`)}
      ${metricCard("Research candidates", formatNumber(watchCount), researchCandidateNote())}
    </div>
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>${escapeHtml(categoryTitle())} Holdings</h2>
          <p>Showing top ${formatNumber(displayedHoldings.length)} of ${formatNumber(holdings.length)} ${escapeHtml(holdingMatchLabel())}, ranked by ${escapeHtml(categoryWeightLabel().toLowerCase())}</p>
        </div>
      </div>
      ${holdingsTable(displayedHoldings)}
    </section>
  `;
}

function renderInvestors() {
  const investors = filteredInvestors();
  if (!investors.length) {
    els.views.investors.innerHTML = emptyState();
    return;
  }

  els.views.investors.innerHTML = `
    <div class="investor-grid">
      ${investors.map(investorCard).join("")}
    </div>
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Investor Detail</h2>
          <p>Latest report patterns and quarter-over-quarter activity</p>
        </div>
      </div>
      ${investorDetail(investors[0])}
    </section>
  `;
}

function renderChanges() {
  const changes = filteredChanges();
  const displayedChanges = limitRows(changes);
  els.views.changes.innerHTML = `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Quarter-over-Quarter Changes</h2>
          <p>Showing top ${formatNumber(displayedChanges.length)} of ${formatNumber(changes.length)} rows after filters</p>
        </div>
      </div>
      ${displayedChanges.length ? changesTable(displayedChanges) : emptyState()}
    </section>
  `;
}

function renderWatchlist() {
  const watchlist = filteredWatchlist();
  els.views.watchlist.innerHTML = watchlist.length
    ? `
      <div class="warning">Research priority is not a rating: new buys, adds, shared ownership, meaningful portfolio weight, large disclosed value, and major changes in large core holdings increase the score.</div>
      <div class="watch-grid">${watchlist.map(watchCard).join("")}</div>
    `
    : emptyState();
}

function renderResearch() {
  const investor = selectedInvestor() || state.data.investors[0];
  const investorLabel = investorSelectionLabel();
  els.views.research.innerHTML = `
    <div class="research-grid">
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Trading Style</h2>
            <p>${escapeHtml(investorLabel)} based on loaded 13F filings</p>
          </div>
        </div>
        <div class="panel-body">
          ${styleSummary(investor)}
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Ticker Snapshot</h2>
            <p>Analyst rating and target-price summary</p>
          </div>
        </div>
        <div class="panel-body">
          <form class="ticker-form" id="tickerForm">
            <div class="inline-form">
              <label>
                Ticker
                <input id="tickerInput" type="text" placeholder="AAPL" autocomplete="off" />
              </label>
              <button type="submit">Check</button>
            </div>
            <div id="tickerResult" class="ticker-result">Set FMP_API_KEY or FINNHUB_API_KEY on the local server for live analyst ratings and price targets.</div>
            <p class="data-source-note">Analyst targets are not recommendations. They are external consensus estimates and may be delayed, stale, or incomplete depending on the data provider.</p>
          </form>
        </div>
      </section>
    </div>
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Filing Q&A</h2>
          <p>Ask about current or prior 13F filings saved locally</p>
        </div>
      </div>
      <div class="panel-body">
        <form class="qa-form" id="qaForm">
          <div class="inline-form">
            <label>
              Quarters
              <select id="qaQuarters">
                <option value="4">Last 4 quarters</option>
                <option value="8">Last 8 quarters</option>
                <option value="12">Last 12 quarters</option>
                <option value="20" selected>Last 20 quarters</option>
              </select>
            </label>
            <button type="submit">Prepare Context</button>
          </div>
          <label>
            Question
            <textarea id="qaQuestion" placeholder="Example: How has Tudor changed its semiconductor exposure over the last 5 years?"></textarea>
          </label>
          <div class="qa-actions">
            <a class="source-link" href="https://chatgpt.com/" target="_blank" rel="noreferrer">Open ChatGPT</a>
            <button type="button" id="copyContextButton">Copy Context</button>
          </div>
          <div id="qaAnswer" class="answer-box">Prepare context, copy it, then open ChatGPT and paste it there with your question.</div>
          <p class="data-source-note">The context is built from local SEC filing data. ChatGPT Plus works well here because you can paste the generated context directly into a new chat.</p>
        </form>
      </div>
    </section>
  `;
  bindResearchForms();
}

function renderReadme() {
  els.views.readme.innerHTML = `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Dashboard Definitions</h2>
          <p>What the local 13F dashboard means by value, status, priority, and lifecycle</p>
        </div>
      </div>
      <div class="panel-body readme-body">
        <div class="definition-grid">
          ${definitionCard(
            "Data source",
            "SEC Form 13F filings downloaded from EDGAR and saved locally. Dataroma is a comparison/source-discovery reference, but the dashboard calculations come from the local SEC filing data.",
          )}
          ${definitionCard(
            "Portfolio name",
            "The filing manager or fund name behind the investor label, such as Pershing Square Capital Management for Bill Ackman. Watchlist owner rows show both the investor name and the portfolio manager name when available.",
          )}
          ${definitionCard(
            "Reporting quarter",
            "Latest available uses each investor's most recent local filing, even when filing dates differ. Choosing a specific quarter rebuilds holdings, changes, and watchlist from the raw filings saved locally for that report date.",
          )}
          ${definitionCard(
            "Holding side",
            "The dashboard downloads every 13F row, then defaults to the Equity tab so common-stock and non-option positions are not mixed with puts/calls. The Options tab keeps option rows separate, and All 13F is available for audit-style totals.",
          )}
          ${definitionCard(
            "Value",
            "Reported 13F market value converted to dollars. It is not a full net exposure because 13F filings exclude shorts, cash, many international securities, private holdings, and most derivatives.",
          )}
          ${definitionCard(
            "Total weight",
            "The position value divided by that investor's total disclosed 13F value for the quarter.",
          )}
          ${definitionCard(
            "Equity / option weight",
            "The position value divided by the investor's disclosed value on the selected side only. This keeps option-heavy books from distorting equity comparisons.",
          )}
          ${definitionCard(
            "Status",
            "Status compares the selected report quarter against that investor's prior adjacent local quarter. New means the position was absent before. Added and reduced mean share count changed by at least 2%. Held means the change was smaller. Exited appears in Changes because there is no current holding row to show.",
          )}
          ${definitionCard(
            "Research priority",
            "A stock/position-specific watchlist score, not an investor rating or buy recommendation. It rises for new buys, additions, shared ownership, large portfolio weights, large dollar positions, and meaningful reductions in large core holdings.",
          )}
          ${definitionCard(
            "Watchlist grouping",
            "Watchlist securities are grouped by CUSIP, holding side, and option put/call flag. This combines equivalent equity rows even when filings use slightly different class labels.",
          )}
          ${definitionCard(
            "Ticker / issuer search",
            "The main search box accepts ticker symbols, ticker prefixes, and issuer-name text. One-letter tickers stay exact, so V still means Visa, while longer prefixes such as AMZ, NVD, or TSL can match AMZN, NVDA, or TSLA. Issuer searches such as apple, western digital, or jpmorgan match the SEC issuer name even when the dashboard has no ticker alias.",
          )}
          ${definitionCard(
            "Lifecycle chart",
            "The Watchlist mini-chart shows the position's weight through the loaded 13F history for each current owner. Zero means the stock was not present in that portfolio for that report date.",
          )}
          ${definitionCard(
            "Context notes",
            "Investor-list comments are generated from the current filters, latest 13F exposure, concentration, book mix, and quarter-over-quarter status counts. They are meant to point you toward what to inspect first, not to score the investor.",
          )}
          ${definitionCard(
            "Past ER watch",
            "Past ER means recent company earnings reports for top visible equity holdings. When FMP_API_KEY is set on the local server, the dashboard can pull FMP earnings rows for known ticker aliases; otherwise the Search link opens a browser search for that issuer's earnings materials.",
          )}
        </div>
        <div class="readme-note">
          <strong>Important limitation</strong>
          <p>13F reports are delayed, usually up to 45 days after quarter-end. The dashboard is designed to surface research leads and investor behavior patterns, not to provide financial advice.</p>
        </div>
      </div>
    </section>
  `;
}

function definitionCard(title, body) {
  return `
    <article class="definition-card">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(body)}</p>
    </article>
  `;
}

function investorCard(investor) {
  const counts = investor.latest_change_counts || {};
  const report = investor.latest_report_date || "No filing";
  return `
    <article class="investor-card">
      <div>
        <h3>${escapeHtml(investor.investor)}</h3>
        <p class="manager">${escapeHtml(investor.manager)}</p>
      </div>
      <div class="stats-row">
        ${stat("Value", formatMoney(investor.total_value_usd))}
        ${stat("13F lines", formatNumber(investor.holding_count))}
        ${stat("Top 10", formatPercent(investor.top_10_concentration))}
      </div>
      <div class="bar" aria-label="Top ten concentration"><span style="width: ${clamp(investor.top_10_concentration * 100, 0, 100)}%"></span></div>
      <div class="tag-row">
        <span class="tag">${escapeHtml(report)}</span>
        <span class="tag">${formatNumber(investor.non_option_count || 0)} non-option</span>
        <span class="tag">${formatNumber(investor.option_count || 0)} options</span>
        <span class="tag">${formatNumber(counts.new || 0)} new</span>
        <span class="tag">${formatNumber(counts.added || 0)} added</span>
        <span class="tag">${formatNumber(counts.exited || 0)} exits</span>
      </div>
      <div class="awareness-label">Context notes</div>
      <ul class="pattern-list">
        ${investorAwarenessList(investor).slice(0, 2).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </article>
  `;
}

function investorDetail(investor) {
  const investorHoldings = filteredHoldings()
    .filter((item) => item.investor_slug === investor.slug);
  const investorChanges = filteredChanges()
    .filter((item) => item.investor_slug === investor.slug);
  const displayedInvestorHoldings = limitRows(investorHoldings);
  const displayedInvestorChanges = limitRows(investorChanges);
  const awareness = investorAwarenessList(investor, investorHoldings, investorChanges);
  const earningsCandidates = earningsCandidatesFor(investorHoldings);
  const links = [
    investor.latest_sec_url ? `<a class="source-link" href="${escapeAttribute(investor.latest_sec_url)}" target="_blank" rel="noreferrer">Latest filing</a>` : "",
    investor.sec_company_url ? `<a class="source-link" href="${escapeAttribute(investor.sec_company_url)}" target="_blank" rel="noreferrer">SEC profile</a>` : "",
    investor.dataroma_url ? `<a class="source-link" href="${escapeAttribute(investor.dataroma_url)}" target="_blank" rel="noreferrer">Dataroma</a>` : "",
  ].join("");

  return `
    <div class="panel-header">
      <div>
        <h2>${escapeHtml(investor.investor)}</h2>
        <p>${escapeHtml(investor.style || "")}</p>
      </div>
      <div class="topbar-actions">${links}</div>
    </div>
    <div class="metric-grid" style="padding: 16px;">
      ${metricCard("Portfolio value", formatMoney(investor.total_value_usd), investor.latest_report_date || "")}
      ${metricCard("Non-option rows", formatNumber(investor.non_option_count), `${formatNumber(investor.unique_non_option_issuer_count)} unique issuers`)}
      ${metricCard("Turnover proxy", formatPercent(investor.turnover_proxy), "Value-based estimate")}
      ${metricCard("Avg new positions", formatNumber(investor.average_new_positions, 1), "Loaded history")}
    </div>
    <div class="situational-grid" style="padding: 0 16px 16px;">
      <section class="awareness-block">
        <div class="section-heading">
          <h3>Context Notes</h3>
          <p>What deserves attention before reading the table</p>
        </div>
        <ul class="pattern-list">
          ${awareness.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      </section>
      <section class="earnings-watch">
        <div class="section-heading">
          <h3>Past ER Watch</h3>
          <p>Recent earnings reports for top equity holdings with ticker aliases</p>
        </div>
        ${pastEarningsWatch(earningsCandidates)}
      </section>
    </div>
    <div class="grid-2" style="padding: 0 16px 16px;">
      <div>
        <h2 class="subhead">Top ${escapeHtml(categoryTitle())} Holdings</h2>
        <p class="subtle-note">Showing ${formatNumber(displayedInvestorHoldings.length)} of ${formatNumber(investorHoldings.length)}</p>
        ${holdingsTable(displayedInvestorHoldings)}
      </div>
      <div>
        <h2 class="subhead">Largest Changes</h2>
        <p class="subtle-note">Showing ${formatNumber(displayedInvestorChanges.length)} of ${formatNumber(investorChanges.length)}</p>
        ${changesTable(displayedInvestorChanges)}
      </div>
    </div>
  `;
}

function investorAwarenessList(investor, holdings = null, changes = null) {
  const investorHoldings =
    holdings ||
    state.data.holdings
      .filter((item) => item.investor_slug === investor.slug && matchesSearch(item) && matchesCategory(item))
      .map((item) => (state.status === "all" ? item : enrichHoldingStatus(item)))
      .filter(matchesStatus);
  const investorChanges =
    changes ||
    state.data.changes.filter(
      (item) =>
        item.investor_slug === investor.slug &&
        matchesSearch(item) &&
        matchesCategory(item) &&
        (state.status === "all" || item.status === state.status),
    );
  const topHolding = [...investorHoldings].sort((a, b) => activeWeight(b) - activeWeight(a))[0];
  const counts = countBy(investorChanges, "status");
  const optionMix = ratio(investor.option_value_usd, investor.total_value_usd);
  const equityMix = ratio(investor.equity_value_usd, investor.total_value_usd);
  const earningsNames = earningsCandidatesFor(investorHoldings);
  const notes = [];

  if (topHolding) {
    notes.push(
      `Largest visible ${categoryTitle().toLowerCase()} exposure is ${issuerLabel(topHolding)} at ${formatPercent(activeWeight(topHolding))} of the selected side (${formatMoney(topHolding.value_usd)}).`,
    );
  } else {
    notes.push(`No ${categoryTitle().toLowerCase()} holdings match the current filters.`);
  }

  notes.push(
    `Latest change tape shows ${formatNumber(counts.new || 0)} new, ${formatNumber(counts.added || 0)} added, ${formatNumber(counts.reduced || 0)} reduced, and ${formatNumber(counts.exited || 0)} exited rows in the current filter context.`,
  );

  if (optionMix >= 0.2) {
    notes.push(`Options are ${formatPercent(optionMix)} of disclosed 13F value, so separate the Options tab before reading this as pure equity conviction.`);
  } else {
    notes.push(`Equity/non-option rows are ${formatPercent(equityMix)} of disclosed 13F value; the current view is mostly cash-equity style 13F exposure.`);
  }

  if (investor.top_10_concentration >= 0.65) {
    notes.push(`Top 10 concentration is high at ${formatPercent(investor.top_10_concentration)}, so individual position changes can matter more than row count.`);
  } else if (investor.holding_count >= 500) {
    notes.push(`This is a broad book with ${formatNumber(investor.holding_count)} reported rows; look for repeated adds/reductions rather than one-off small weights.`);
  }

  if (earningsNames.length) {
    notes.push(`Past ER lookup is ready for ${formatNumber(earningsNames.length)} top equity name${earningsNames.length === 1 ? "" : "s"} with known ticker aliases.`);
  }

  return notes;
}

function countBy(rows, key) {
  return rows.reduce((counts, row) => {
    const value = row[key] || "unknown";
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

function earningsCandidatesFor(holdings) {
  const byTicker = new Map();
  for (const row of holdings) {
    if (row.category === "option") continue;
    const symbol = primaryTickerFor(row);
    if (!symbol) continue;
    const current = byTicker.get(symbol);
    if (!current || activeWeight(row) > activeWeight(current)) {
      byTicker.set(symbol, row);
    }
  }
  return [...byTicker.values()].sort((a, b) => activeWeight(b) - activeWeight(a)).slice(0, 6);
}

function pastEarningsWatch(rows) {
  if (!rows.length) {
    return `<p class="empty-inline">No top equity holdings in the current filter have a ticker alias yet.</p>`;
  }
  return `
    <div class="earnings-actions">
      <button type="button" data-earnings-load-all>Load visible ER</button>
      <span>Uses FMP_API_KEY on the local server.</span>
    </div>
    <div class="earnings-list">
      ${rows.map(pastEarningsRow).join("")}
    </div>
  `;
}

function pastEarningsRow(row) {
  const symbol = primaryTickerFor(row);
  const label = issuerLabel(row);
  const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(`${symbol} ${row.issuer || ""} earnings results investor relations`)}`;
  return `
    <div class="earnings-row">
      <div>
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(symbol)} · ${formatPercent(activeWeight(row))} · ${formatMoney(row.value_usd)}</span>
      </div>
      <div class="earnings-row-actions">
        <button type="button" data-earnings-symbol="${escapeAttribute(symbol)}">Past ER</button>
        <a class="source-link compact-link" href="${escapeAttribute(searchUrl)}" target="_blank" rel="noreferrer">Search</a>
      </div>
      <div class="earnings-result" data-earnings-result="${escapeAttribute(symbol)}">Not loaded</div>
    </div>
  `;
}

function holdingsTable(rows) {
  if (!rows.length) return emptyState();
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            ${sortHeader("holdings", "investor", "Investor")}
            ${sortHeader("holdings", "issuer", "Issuer")}
            ${sortHeader("holdings", "status", "Status")}
            ${sortHeader("holdings", "cusip", "CUSIP")}
            ${sortHeader("holdings", "value_usd", "Value", true)}
            ${sortHeader("holdings", "weight", categoryWeightLabel(), true)}
            ${sortHeader("holdings", "category", "Side")}
            ${sortHeader("holdings", "shares", "Shares", true)}
            ${sortHeader("holdings", "class", "Class")}
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <td>${escapeHtml(row.investor)}</td>
                  <td>${escapeHtml(issuerLabel(row))}</td>
                  <td>${statusPill(row.status || "held")}</td>
                  <td>${escapeHtml(row.cusip || "")}</td>
                  <td class="num">${formatMoney(row.value_usd)}</td>
                  <td class="num">${formatPercent(activeWeight(row))}</td>
                  <td>${sidePill(row.category)}</td>
                  <td class="num">${formatNumber(row.shares)}</td>
                  <td>${escapeHtml(row.title_of_class || "")}${row.put_call ? ` ${escapeHtml(row.put_call)}` : ""}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function changesTable(rows) {
  if (!rows.length) return emptyState();
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            ${sortHeader("changes", "investor", "Investor")}
            ${sortHeader("changes", "issuer", "Issuer")}
            ${sortHeader("changes", "status", "Status")}
            ${sortHeader("changes", "current_value_usd", "Current Value", true)}
            ${sortHeader("changes", "value_delta_usd", "Delta", true)}
            ${sortHeader("changes", "share_delta_pct", "Share Change", true)}
            ${sortHeader("changes", "active_weight", categoryWeightLabel(), true)}
            ${sortHeader("changes", "category", "Side")}
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <td>${escapeHtml(row.investor)}</td>
                  <td>${escapeHtml(issuerLabel(row))}</td>
                  <td>${statusPill(row.status)}</td>
                  <td class="num">${formatMoney(row.current_value_usd)}</td>
                  <td class="num">${formatMoney(row.value_delta_usd)}</td>
                  <td class="num">${formatPercent(row.share_delta_pct)}</td>
                  <td class="num">${formatPercent(activeChangeWeight(row))}</td>
                  <td>${sidePill(row.category)}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function watchCard(item) {
  const owners = ownerDetails(item);
  const commentary = item.portfolio_commentary || item.research_prompt || "";
  return `
    <article class="watch-card">
      <div class="watch-head">
        <div>
          <h3>${escapeHtml(issuerLabel(item))}</h3>
          <p>${escapeHtml(item.cusip || "")} ${escapeHtml(item.title_of_class || "")}</p>
        </div>
        <div class="watch-score" title="Research priority score: new buys, adds, shared ownership, meaningful portfolio weight, and large disclosed value increase this number.">
          <strong>${formatNumber(item.score, 1)}</strong>
          <span>Priority</span>
        </div>
      </div>
      <div class="stats-row">
        ${stat("Value", formatMoney(item.largest_current_value_usd))}
        ${stat(categoryWeightLabel(), formatPercent(activeWatchWeight(item)))}
        ${stat("Owners", formatNumber(owners.length))}
      </div>
      <div class="tag-row">
        ${sidePill(item.category)}
      </div>
      <div class="watch-section">
        <h4>Score drivers</h4>
        <ul class="pattern-list">
          ${(item.reasons || []).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
        </ul>
      </div>
      <div class="watch-section">
        <h4>Owners and changes</h4>
        <div class="owner-change-list">${owners.map(watchOwnerChangeRow).join("")}</div>
      </div>
      ${watchLifecycleChart(item)}
      <div class="watch-commentary">
        <strong>Portfolio read</strong>
        <p>${escapeHtml(commentary)}</p>
      </div>
    </article>
  `;
}

function ownerDetails(item) {
  if (Array.isArray(item.owner_details) && item.owner_details.length) return item.owner_details;
  const buyers = new Set(item.buyers || []);
  return (item.owners || []).map((owner) => ({
    investor: owner,
    portfolio_name: owner,
    status: buyers.has(owner) ? "added" : "held",
    current_value_usd: 0,
    current_weight: 0,
    current_category_weight: 0,
    value_delta_usd: 0,
    share_delta_pct: 0,
  }));
}

function latestWatchChanges(item) {
  const active = ownerDetails(item).filter((owner) => owner.status && owner.status !== "held");
  if (active.length) {
    return active.sort((a, b) => Math.abs(Number(b.value_delta_usd || 0)) - Math.abs(Number(a.value_delta_usd || 0)));
  }
  return ownerDetails(item).slice(0, 3);
}

function watchOwnerChangeRow(owner) {
  const status = owner.status || "held";
  return `
    <div class="owner-change-row owner-change-${escapeAttribute(status)}">
      ${statusPill(status)}
      <div>
        <strong>${escapeHtml(owner.investor)}</strong>
        <small>${escapeHtml(owner.portfolio_name || owner.manager || owner.investor)}</small>
        <span>${formatMoney(owner.current_value_usd)} / ${formatPercent(activeOwnerWeight(owner))}</span>
        <em>${escapeHtml(watchChangeText(owner))}</em>
      </div>
    </div>
  `;
}

function watchLifecycleChart(item) {
  const lifecycle = Array.isArray(item.lifecycle) ? item.lifecycle : [];
  const visibleLifecycle = lifecycle.filter((series) => ownerDetails(item).some((owner) => owner.investor === series.investor));
  if (!visibleLifecycle.length) return "";

  const dates = [...new Set(visibleLifecycle.flatMap((series) => (series.points || []).map((point) => point.report_date)))].sort();
  if (!dates.length) return "";

  const values = visibleLifecycle.flatMap((series) => (series.points || []).map((point) => lifecyclePointWeight(point)));
  const maxValue = Math.max(...values, 0);
  if (maxValue <= 0) return "";

  const width = 360;
  const height = 118;
  const padX = 14;
  const padTop = 12;
  const padBottom = 24;
  const plotHeight = height - padTop - padBottom;
  const colors = ["#226c73", "#2f7d52", "#b06b24", "#2f5f9f", "#b84a3a", "#6f5aa8", "#7c6a36", "#3f7f91", "#8f4f63", "#4f795f"];
  const xForDate = (date) => {
    const index = dates.indexOf(date);
    if (dates.length === 1) return width / 2;
    return padX + (index / (dates.length - 1)) * (width - padX * 2);
  };
  const yForValue = (value) => padTop + plotHeight - (Number(value || 0) / maxValue) * plotHeight;
  const dateLabel = dates.length > 1 ? `${shortDate(dates[0])} to ${shortDate(dates[dates.length - 1])}` : shortDate(dates[0]);

  const lines = visibleLifecycle
    .map((series, index) => {
      const color = colors[index % colors.length];
      const pointMap = new Map((series.points || []).map((point) => [point.report_date, point]));
      const coordinates = dates
        .map((date) => `${xForDate(date).toFixed(1)},${yForValue(lifecyclePointWeight(pointMap.get(date))).toFixed(1)}`)
        .join(" ");
      const latestPoint = pointMap.get(dates[dates.length - 1]) || {};
      return `
        <polyline points="${coordinates}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></polyline>
        <circle cx="${xForDate(dates[dates.length - 1]).toFixed(1)}" cy="${yForValue(lifecyclePointWeight(latestPoint)).toFixed(1)}" r="3" fill="${color}"></circle>
      `;
    })
    .join("");

  const legend = visibleLifecycle
    .map((series, index) => {
      const latest = (series.points || [])[series.points.length - 1] || {};
      const color = colors[index % colors.length];
      return `
        <div class="lifecycle-legend-item">
          <span style="background:${color}"></span>
          <strong>${escapeHtml(series.investor)}</strong>
          <em>${escapeHtml(series.portfolio_name || "")}</em>
          <small>${formatPercent(lifecyclePointWeight(latest))} current / ${formatPercent(series.peak_weight || 0)} peak</small>
        </div>
      `;
    })
    .join("");

  return `
    <div class="watch-section lifecycle-section">
      <h4>Portfolio lifecycle</h4>
      <div class="lifecycle-chart" aria-label="Position weight over loaded 13F history">
        <svg viewBox="0 0 ${width} ${height}" role="img">
          <line x1="${padX}" y1="${height - padBottom}" x2="${width - padX}" y2="${height - padBottom}" class="axis-line"></line>
          <text x="${padX}" y="${height - 6}">${escapeHtml(shortDate(dates[0]))}</text>
          <text x="${width - padX}" y="${height - 6}" text-anchor="end">${escapeHtml(shortDate(dates[dates.length - 1]))}</text>
          <text x="${padX}" y="10">${escapeHtml(formatPercent(maxValue))}</text>
          ${lines}
        </svg>
        <div class="lifecycle-range">${escapeHtml(dateLabel)} · ${escapeHtml(categoryWeightLabel())}</div>
      </div>
      <div class="lifecycle-legend">${legend}</div>
    </div>
  `;
}

function lifecyclePointWeight(point) {
  if (!point) return 0;
  return state.holdingCategory === "all" ? Number(point.weight || 0) : Number(point.category_weight || 0);
}

function watchChangeText(owner) {
  const status = owner.status || "held";
  if (status === "new") return `Opened a new position; current value ${formatMoney(owner.current_value_usd)}`;
  if (status === "added") return `Added ${formatPercent(Math.abs(Number(owner.share_delta_pct || 0)))} shares; value change ${formatMoney(owner.value_delta_usd)}`;
  if (status === "reduced") return `Reduced ${formatPercent(Math.abs(Number(owner.share_delta_pct || 0)))} shares; value change ${formatMoney(owner.value_delta_usd)}`;
  if (status === "exited") return `Exited; value change ${formatMoney(owner.value_delta_usd)}`;
  return `Held; current value ${formatMoney(owner.current_value_usd)}`;
}

function styleSummary(investor) {
  const investors = selectedInvestors();
  if (!hasInvestorFilter() || investors.length !== 1) {
    return `
      <div class="style-summary">
        <h3>${escapeHtml(investorSelectionLabel())}</h3>
        <p>Select exactly one investor in the top filter to see a more specific trading-style readout.</p>
        <div class="stats-row">
          ${stat("Tracked value", formatMoney(sum(investors.map((item) => item.total_value_usd))))}
          ${stat("Investors", formatNumber(investors.length))}
          ${stat("Watchlist", formatNumber(filteredWatchlist().length))}
        </div>
        <ul class="pattern-list">
          <li>Use the Watchlist tab for cross-investor consensus buying and additions.</li>
          <li>Use the Equity and Options book tabs before interpreting macro-oriented or platform managers such as Tudor, Duquesne, Citadel, Millennium, or Balyasny.</li>
        </ul>
      </div>
    `;
  }

  const counts = investor.latest_change_counts || {};
  const optionMix = ratio(investor.option_value_usd, investor.total_value_usd);
  const equityMix = ratio(investor.equity_value_usd, investor.total_value_usd);
  return `
    <div class="style-summary">
      <h3>${escapeHtml(investor.investor)}</h3>
      <p>${escapeHtml(investor.style || "")}</p>
      <div class="metric-grid">
        ${metricCard("Total 13F value", formatMoney(investor.total_value_usd), investor.latest_report_date || "")}
        ${metricCard("Equity side", formatMoney(investor.equity_value_usd), formatPercent(equityMix))}
        ${metricCard("Options side", formatMoney(investor.option_value_usd), formatPercent(optionMix))}
        ${metricCard("Turnover proxy", formatPercent(investor.turnover_proxy), "Latest loaded quarter")}
      </div>
      <div class="stats-row">
        ${stat("New", formatNumber(counts.new || 0))}
        ${stat("Added", formatNumber(counts.added || 0))}
        ${stat("Exited", formatNumber(counts.exited || 0))}
      </div>
      <ul class="pattern-list">
        ${(investor.pattern_summary || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        <li>${escapeHtml(investor.notes || "")}</li>
      </ul>
    </div>
  `;
}

function bindResearchForms() {
  const qaForm = document.querySelector("#qaForm");
  const tickerForm = document.querySelector("#tickerForm");
  if (qaForm) {
    qaForm.addEventListener("submit", handleAskQuestion);
  }
  const copyButton = document.querySelector("#copyContextButton");
  if (copyButton) {
    copyButton.addEventListener("click", copyQaContext);
  }
  if (tickerForm) {
    tickerForm.addEventListener("submit", handleTickerLookup);
  }
}

async function handleAskQuestion(event) {
  event.preventDefault();
  const answer = document.querySelector("#qaAnswer");
  const question = document.querySelector("#qaQuestion").value.trim();
  const quarters = Number(document.querySelector("#qaQuarters").value || 20);
  if (!question) {
    answer.textContent = "Ask a filing question first.";
    return;
  }
  answer.classList.add("loading");
  answer.textContent = "Preparing local filing context...";
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        investor_slug: investorSelectionPayload().length === 1 ? investorSelectionPayload()[0] : "all",
        investor_slugs: investorSelectionPayload(),
        question,
        quarters,
        category: state.holdingCategory,
      }),
    });
    const payload = await response.json();
    const text = payload.answer || payload.error || "No context returned.";
    answer.textContent = text.replace("OPENAI_API_KEY is not set on the local server, so I cannot call an LLM yet.\n\nHere is the filing context that would be sent to the model:\n\n", "");
  } catch (error) {
    answer.textContent = `Q&A server is not running. Start it with: python3 scripts/dashboard_server.py --port 8013\n\n${error.message}`;
  } finally {
    answer.classList.remove("loading");
  }
}

async function copyQaContext() {
  const answer = document.querySelector("#qaAnswer");
  const question = document.querySelector("#qaQuestion").value.trim();
  const context = answer.textContent.trim();
  if (!context || context.startsWith("Prepare context")) {
    answer.textContent = "Prepare context first, then copy it for ChatGPT.";
    return;
  }
  const prompt = [
    question ? `My question: ${question}` : "My question: Please analyze this 13F filing context.",
    "",
    "Use the SEC 13F context below. Separate equity/non-option holdings from options, cite report dates, and explain limitations.",
    "",
    context,
  ].join("\n");
  try {
    await navigator.clipboard.writeText(prompt);
    answer.textContent = `${context}\n\nCopied for ChatGPT. Open ChatGPT and paste.`;
  } catch (error) {
    answer.textContent = `${context}\n\nClipboard copy failed. Select this context manually and paste it into ChatGPT.`;
  }
}

async function handleTickerLookup(event) {
  event.preventDefault();
  const result = document.querySelector("#tickerResult");
  const symbol = document.querySelector("#tickerInput").value.trim().toUpperCase();
  if (!symbol) {
    result.textContent = "Enter a ticker first.";
    return;
  }
  result.classList.add("loading");
  result.textContent = `Looking up ${symbol}...`;
  try {
    const response = await fetch("/api/ticker", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    const payload = await response.json();
    result.textContent = payload.summary || payload.error || "No ticker data returned.";
  } catch (error) {
    result.textContent = `Ticker server is not running. Start it with: python3 scripts/dashboard_server.py --port 8013\n\n${error.message}`;
  } finally {
    result.classList.remove("loading");
  }
}

async function handleVisibleEarningsLookups(button) {
  const panel = button.closest(".earnings-watch");
  if (!panel) return;
  const buttons = [...panel.querySelectorAll("[data-earnings-symbol]")];
  button.disabled = true;
  button.textContent = "Loading ER...";
  try {
    for (const item of buttons) {
      await handleEarningsLookup(item);
    }
  } finally {
    button.disabled = false;
    button.textContent = "Load visible ER";
  }
}

async function handleEarningsLookup(button) {
  const symbol = normalizeTickerQuery(button.dataset.earningsSymbol || "");
  const row = button.closest(".earnings-row");
  const result = row?.querySelector(".earnings-result");
  if (!symbol || !result) return;

  if (state.earningsCache[symbol]) {
    result.textContent = state.earningsCache[symbol];
    return;
  }

  button.disabled = true;
  result.classList.add("loading");
  result.textContent = `Looking up ${symbol} past ER...`;
  try {
    const response = await fetch("/api/earnings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    const payload = await response.json();
    const text = payload.summary || payload.error || "No earnings data returned.";
    state.earningsCache[symbol] = text;
    result.textContent = text;
  } catch (error) {
    result.textContent = `Earnings lookup failed. Start the local server with FMP_API_KEY set, then try again.\n\n${error.message}`;
  } finally {
    result.classList.remove("loading");
    button.disabled = false;
  }
}

// Every local API call goes through here. A bare response.json() on an HTML
// error page throws an engine-specific parse error ("The string did not match
// the expected pattern." in Safari), which tells the user nothing about the
// actual problem -- usually a stale server process or one that was never
// started. Read the body as text first and report what really came back.
async function postJson(url, body) {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  } catch (error) {
    throw new Error(
      `cannot reach the local server. Start it with "python3 scripts/dashboard_server.py" and open the dashboard through it, not as a file:// page.`,
    );
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      payload = null;
    }
  }

  if (payload === null) {
    if (response.status === 404) {
      throw new Error(
        `${url} returned 404. The running server predates this endpoint — restart scripts/dashboard_server.py to pick up the current code.`,
      );
    }
    const snippet = text.slice(0, 120).replace(/\s+/g, " ").trim();
    throw new Error(`${url} returned HTTP ${response.status} and a non-JSON body: ${snippet || "(empty)"}`);
  }

  if (!response.ok || payload.error) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function checkLatestFilings() {
  if (!state.data) return;
  const button = els.checkFilingsButton;
  const status = els.filingCheckStatus;
  const label = investorSelectionLabel().toLowerCase();
  button.disabled = true;
  status.textContent = `Checking SEC for ${label}...`;
  status.title = "";

  try {
    const payload = await postJson("/api/check-filings", {
      investor_slug: investorSelectionPayload().length === 1 ? investorSelectionPayload()[0] : "all",
      investor_slugs: investorSelectionPayload(),
    });

    const results = payload.results || [];
    const newFilings = results.filter((item) => item.new_available);
    const errors = results.filter((item) => item.error);
    const checkedLabel = payload.checked_at ? `Checked ${formatDateTime(payload.checked_at).replace("Updated ", "")}` : "Checked SEC";
    status.title = results.map(filingCheckLine).join("\n");

    if (newFilings.length) {
      // Something new exists upstream, so download it rather than just reporting it.
      await downloadNewFilings(newFilings, status);
      return;
    }

    if (errors.length) {
      status.textContent = payload.user_agent_unset
        ? `SEC rejected ${errors.length} request${errors.length === 1 ? "" : "s"}. Set SEC_USER_AGENT in .env and restart the server.`
        : `No new filings found; ${errors.length} SEC check error${errors.length === 1 ? "" : "s"}. Hover for detail.`;
      return;
    }

    status.textContent = `No new filings. ${checkedLabel}`;
  } catch (error) {
    status.textContent = `Filing check failed: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

async function downloadNewFilings(newFilings, status) {
  const checkDetail = status.title;
  const names = newFilings
    .slice(0, 2)
    .map((item) => `${item.investor} ${item.sec_report_date}`)
    .join(", ");
  const extra = newFilings.length > 2 ? ` +${newFilings.length - 2} more` : "";
  status.textContent = `${newFilings.length} new filing${newFilings.length === 1 ? "" : "s"} (${names}${extra}). Downloading...`;

  const slugs = newFilings.map((item) => item.investor_slug).filter(Boolean);
  await postJson("/api/refresh-filings", {
    investor_slugs: slugs,
    investor_slug: slugs.length === 1 ? slugs[0] : "all",
  });

  const summary = await pollRefresh(status);
  if (!summary) return;

  if (summary.rebuilt) {
    status.textContent = "Download complete. Reloading dashboard...";
    await reloadDashboardData();
    const added = summary.filings_added || 0;
    status.textContent = `Downloaded ${added} filing${added === 1 ? "" : "s"} and refreshed the dashboard.`;
  } else {
    status.textContent = "SEC reported new filings but none could be downloaded. Hover for detail.";
  }

  const problems = summary.errors || [];
  status.title = problems.length ? `${checkDetail}\n\nDownload issues:\n${problems.join("\n")}` : checkDetail;
}

async function pollRefresh(status) {
  // Rebuilding reads every cached filing, so this can run for minutes. Poll for
  // progress instead of holding one request open and risking a browser timeout.
  const deadline = Date.now() + 30 * 60 * 1000;
  let consecutiveFailures = 0;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    let job;
    try {
      job = await postJson("/api/refresh-status", {});
      consecutiveFailures = 0;
    } catch (error) {
      // A single dropped poll is not fatal, but a persistent one means the
      // server is gone or too old to know this endpoint. Say so rather than
      // spinning silently until the deadline.
      consecutiveFailures += 1;
      if (consecutiveFailures >= 5) {
        status.textContent = `Lost contact with the server while downloading: ${error.message}`;
        return null;
      }
      continue;
    }
    if (job.state === "running") {
      const percent = Math.round((job.progress || 0) * 100);
      status.textContent = `${job.message || "Working"} (${percent}%)`;
      continue;
    }
    if (job.state === "error") {
      status.textContent = `Download failed: ${job.error || "unknown error"}`;
      return null;
    }
    if (job.state === "done") return job.summary || {};
  }
  status.textContent = "Download is still running. Check the server console.";
  return null;
}

async function reloadDashboardData() {
  const response = await fetch("../data/processed/dashboard.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  state.baseData = await response.json();
  state.quarterCache = {};
  state.changeIndex = null;
  state.reportDate = "latest";
  state.data = state.baseData;
  populateInvestorFilter();
  populateReportDateFilter();
  render();
}

function filingCheckLine(item) {
  if (item.error) return `${item.investor}: ${item.error}`;
  const marker = item.new_available ? "NEW" : "current";
  return `${item.investor}: ${marker} | SEC ${item.sec_report_date || "n/a"} filed ${item.sec_filing_date || "n/a"} | local ${item.local_report_date || "n/a"} filed ${item.local_filing_date || "n/a"}`;
}

function filteredInvestors() {
  return state.data.investors.filter((item) => matchesInvestor(item) && matchesInvestorTickerSearch(item));
}

function filteredHoldings() {
  return state.data.holdings
    .map(enrichHoldingStatus)
    .filter((item) => matchesInvestor(item) && matchesSearch(item) && matchesCategory(item) && matchesStatus(item))
    .sort((a, b) => compareRows(a, b, state.sort.holdings, "holdings"));
}

function filteredChanges() {
  return state.data.changes
    .filter(
      (item) =>
        matchesInvestor(item) &&
        matchesSearch(item) &&
        matchesCategory(item) &&
        (state.status === "all" || item.status === state.status),
    )
    .sort((a, b) => compareRows(a, b, state.sort.changes, "changes"));
}

function filteredWatchlist() {
  return state.data.watchlist
    .filter((item) => {
      const owners = ownerDetails(item);
      const selectedSlugs = selectedInvestorSlugSet();
      const selectedNames = new Set(selectedInvestors().map((investor) => investor.investor));
      const investorMatch =
        !hasInvestorFilter() ||
        (item.buyers || []).some((buyer) => selectedNames.has(buyer)) ||
        owners.some((owner) => selectedSlugs.has(owner.investor_slug) || selectedNames.has(owner.investor));
      return investorMatch && matchesCategory(item) && matchesSearch(item) && matchesWatchlistStatus(item);
    })
    .sort((a, b) => activeWatchWeight(b) - activeWatchWeight(a) || Number(b.score || 0) - Number(a.score || 0));
}

function enrichHoldingStatus(row) {
  const change = changeForHolding(row);
  if (!change) return { ...row, status: "held" };
  return {
    ...row,
    status: change.status || "held",
    value_delta_usd: change.value_delta_usd,
    share_delta_pct: change.share_delta_pct,
    previous_report_date: change.previous_report_date,
  };
}

function changeForHolding(row) {
  return changeIndex().get(changeIndexKey(row));
}

function changeIndex() {
  if (state.changeIndex?.data === state.data) return state.changeIndex.map;
  const map = new Map();
  for (const change of state.data?.changes || []) {
    map.set(changeIndexKey(change), change);
  }
  state.changeIndex = { data: state.data, map };
  return map;
}

function changeIndexKey(row) {
  return `${row.investor_slug || ""}|${row.position_key || ""}`;
}

function matchesStatus(item) {
  return state.status === "all" || item.status === state.status;
}

function matchesWatchlistStatus(item) {
  if (state.status === "all") return true;
  return dominantWatchlistStatus(item) === state.status;
}

function dominantWatchlistStatus(item) {
  const owners = ownerDetails(item);
  if (!owners.length) return "held";
  const activeOwners = owners.filter((owner) => ["new", "added", "reduced", "exited"].includes(owner.status));
  if (activeOwners.length) {
    const largestAction = activeOwners.reduce((leader, owner) => {
      const leaderValue = Math.abs(Number(leader.value_delta_usd || leader.current_value_usd || 0));
      const ownerValue = Math.abs(Number(owner.value_delta_usd || owner.current_value_usd || 0));
      return ownerValue > leaderValue ? owner : leader;
    }, activeOwners[0]);
    return largestAction.status || "held";
  }
  const largestOwner = owners.reduce((leader, owner) => {
    const leaderValue = Number(leader.current_value_usd || 0);
    const ownerValue = Number(owner.current_value_usd || 0);
    return ownerValue > leaderValue ? owner : leader;
  }, owners[0]);
  return largestOwner.status || "held";
}

function limitRows(rows) {
  if (state.rowLimit === "all") return rows;
  const limit = Number(state.rowLimit || 24);
  return rows.slice(0, Number.isFinite(limit) ? limit : 24);
}

function hasInvestorFilter() {
  return !state.investors.includes("all");
}

function selectedInvestorSlugs() {
  return hasInvestorFilter() ? state.investors : [];
}

function selectedInvestorSlugSet() {
  return new Set(selectedInvestorSlugs());
}

function investorSelectionPayload() {
  return selectedInvestorSlugs();
}

function selectedInvestors() {
  if (!state.data) return [];
  if (!hasInvestorFilter()) return state.data.investors;
  const selected = selectedInvestorSlugSet();
  return state.data.investors.filter((item) => selected.has(item.slug));
}

function investorSelectionLabel() {
  const investors = selectedInvestors();
  if (!hasInvestorFilter()) return "All tracked investors";
  if (investors.length === 1) return investors[0].investor;
  return `${formatNumber(investors.length)} selected investors`;
}

function selectedInvestor() {
  return selectedInvestors()[0];
}

function warningSummary(warnings) {
  const visible = warnings.slice(0, 4).map(escapeHtml).join("<br>");
  const remainder = warnings.length > 4 ? `<br>${formatNumber(warnings.length - 4)} more refresh warnings. See terminal output or rerun with SEC access.` : "";
  return `${visible}${remainder}`;
}

function toggleSort(table, key) {
  const current = state.sort[table];
  const nextDirection = current.key === key && current.direction === "asc" ? "desc" : "asc";
  state.sort[table] = { key, direction: nextDirection };
}

function sortHeader(table, key, label, numeric = false) {
  const active = state.sort[table]?.key === key;
  const direction = active ? state.sort[table].direction : "";
  const arrow = active ? (direction === "asc" ? "^" : "v") : "<>";
  return `
    <th class="${numeric ? "num" : ""}">
      <button
        type="button"
        class="sort-button ${active ? "active" : ""}"
        data-sort-table="${escapeAttribute(table)}"
        data-sort-key="${escapeAttribute(key)}"
        aria-label="Sort ${escapeAttribute(label)} ${direction === "asc" ? "descending" : "ascending"}"
      >
        <span>${escapeHtml(label)}</span>
        <span class="sort-arrow">${arrow}</span>
      </button>
    </th>
  `;
}

function compareRows(a, b, sort, table) {
  const direction = sort.direction === "asc" ? 1 : -1;
  const left = sortValue(a, sort.key, table);
  const right = sortValue(b, sort.key, table);
  const compared = compareValues(left, right);
  if (compared !== 0) return compared * direction;
  return compareValues(String(a.issuer || ""), String(b.issuer || ""));
}

function sortValue(row, key, table) {
  if (key === "weight") return activeWeight(row);
  if (key === "active_weight") return activeChangeWeight(row);
  if (key === "class") return `${row.title_of_class || ""} ${row.put_call || ""}`.trim();
  if (key === "category") return row.category === "option" ? "Options" : "Equity";
  if (table === "changes" && key === "value_delta_usd") return Number(row.value_delta_usd || 0);
  return row[key];
}

function compareValues(left, right) {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  const bothNumeric = Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && left !== "" && right !== "";
  if (bothNumeric) return leftNumber - rightNumber;
  return String(left ?? "").localeCompare(String(right ?? ""), undefined, { numeric: true, sensitivity: "base" });
}

function matchesInvestor(item) {
  if (!hasInvestorFilter()) return true;
  const slug = item.investor_slug || item.slug;
  return selectedInvestorSlugSet().has(slug);
}

function matchesInvestorTickerSearch(investor) {
  if (!state.search) return true;
  const slug = investor.slug || investor.investor_slug;
  return state.data.holdings.some((item) => item.investor_slug === slug && matchesSearch(item));
}

function matchesSearch(item) {
  return matchesTickerSearch(item) || matchesIssuerSearch(item);
}

function matchesTickerSearch(item) {
  const tokens = tickerSearchTokens();
  if (!tokens.length) return true;
  const aliases = tickerAliasesFor(item);
  if (!aliases.length) return false;
  return tokens.some((token) => aliases.some((alias) => tickerTokenMatches(token, alias)));
}

function tickerSearchTokens() {
  return normalizeTickerQuery(state.search).split(/[,\s]+/).filter(Boolean);
}

function matchesIssuerSearch(item) {
  const queries = issuerSearchQueries();
  if (!queries.length) return false;
  const haystack = normalizeIssuerSearch(`${item.issuer || ""} ${item.title_of_class || ""}`);
  if (!haystack) return false;
  return queries.some((query) => issuerQueryMatches(query, haystack));
}

function issuerSearchQueries() {
  return String(state.search || "")
    .split(",")
    .map(normalizeIssuerSearch)
    .filter((query) => query.replace(/\s+/g, "").length >= 3)
    .filter(Boolean);
}

function issuerQueryMatches(query, haystack) {
  if (haystack.includes(query)) return true;
  const tokens = query.split(" ").filter(Boolean);
  return tokens.length > 1 && tokens.every((token) => haystack.includes(token));
}

function tickerTokenMatches(token, alias) {
  if (!token || !alias) return false;
  if (alias === token) return true;
  if (token.length === 1) return false;
  if (token.length === 2 && KNOWN_TICKER_ALIASES.has(token)) return false;
  return alias.startsWith(token);
}

function tickerAliasesFor(item) {
  const aliases = new Set();
  const explicitTicker = normalizeTickerQuery(item.ticker || item.symbol || "");
  if (explicitTicker) aliases.add(explicitTicker);

  const cusip = String(item.cusip || "").trim().toUpperCase();
  (TICKER_ALIAS_BY_CUSIP[cusip] || []).forEach((ticker) => aliases.add(ticker));

  const issuer = String(item.issuer || "");
  TICKER_ALIAS_BY_ISSUER.forEach(([pattern, tickers]) => {
    if (pattern.test(issuer)) tickers.forEach((ticker) => aliases.add(ticker));
  });

  return [...aliases];
}

function primaryTickerFor(item) {
  return tickerAliasesFor(item)[0] || "";
}

function issuerLabel(item) {
  const issuer = String(item.issuer || "");
  const ticker = primaryTickerFor(item);
  return ticker ? `${issuer} (${ticker})` : issuer;
}

function normalizeTickerQuery(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/[^A-Z0-9.,\-\s]/g, "")
    .trim();
}

function normalizeIssuerSearch(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function matchesCategory(item) {
  return state.holdingCategory === "all" || item.category === state.holdingCategory;
}

function activeWeight(row) {
  return state.holdingCategory === "all" ? Number(row.weight || 0) : Number(row.category_weight || 0);
}

function activeChangeWeight(row) {
  return state.holdingCategory === "all" ? Number(row.current_weight || 0) : Number(row.current_category_weight || 0);
}

function activeWatchWeight(row) {
  return state.holdingCategory === "all" ? Number(row.largest_current_weight || 0) : Number(row.largest_current_category_weight || 0);
}

function activeOwnerWeight(owner) {
  return state.holdingCategory === "all" ? Number(owner.current_weight || 0) : Number(owner.current_category_weight || 0);
}

function categoryTitle() {
  if (state.holdingCategory === "option") return "Options";
  if (state.holdingCategory === "equity") return "Equity / Non-option";
  return "All";
}

function categoryWeightLabel() {
  if (state.holdingCategory === "option") return "Option Weight";
  if (state.holdingCategory === "equity") return "Equity Weight";
  return "Total Weight";
}

function holdingMatchLabel() {
  const category = `${categoryTitle().toLowerCase()} rows`;
  if (state.status === "all") return category;
  return `${statusLabel(state.status)} ${category}`;
}

function statusLabel(status) {
  const labels = {
    new: "new",
    added: "added",
    reduced: "reduced",
    exited: "exited",
    held: "held",
  };
  return labels[status] || String(status || "all");
}

function reportMetricNote(latestReports) {
  if (state.reportDate !== "latest") return `${reportQuarterLabel(state.reportDate)} reports loaded`;
  return `${latestReports.size} report dates loaded`;
}

function investorValueForActiveSide(investor) {
  if (state.holdingCategory === "option") return Number(investor.option_value_usd || 0);
  if (state.holdingCategory === "equity") return Number(investor.equity_value_usd || 0);
  return Number(investor.total_value_usd || 0);
}

function overviewMetricValue(holdings, changes) {
  if (state.status === "new") {
    return sum(changes.map((item) => item.current_value_usd));
  }
  if (state.status === "added") {
    return sum(changes.map((item) => Math.max(Number(item.value_delta_usd || 0), 0)));
  }
  if (state.status === "reduced") {
    return sum(changes.map((item) => Math.abs(Math.min(Number(item.value_delta_usd || 0), 0))));
  }
  if (state.status === "exited") {
    return sum(changes.map((item) => item.previous_value_usd));
  }
  return sum(holdings.map((item) => item.value_usd));
}

function valueMetricLabel() {
  if (state.status === "exited") return "Exited prior value";
  if (state.status !== "all") return `${titleCaseStatus(state.status)} value`;
  return hasInvestorFilter() ? "Selected value" : "Tracked value";
}

function valueMetricNote() {
  if (state.status === "new") return `Current value of newly opened ${categoryTitle().toLowerCase()} rows`;
  if (state.status === "added") return `Positive disclosed value change for added ${categoryTitle().toLowerCase()} rows`;
  if (state.status === "reduced") return `Disclosed value decrease for reduced ${categoryTitle().toLowerCase()} rows`;
  if (state.status === "exited") return `Prior value of exited ${categoryTitle().toLowerCase()} rows`;
  if (state.status !== "all") return `Current value of ${holdingMatchLabel()}`;
  return `${categoryTitle()} value after all current filters`;
}

function researchCandidateNote() {
  if (state.status === "all") return "Watchlist names after current filters";
  return `Dominant ${statusLabel(state.status)} action watchlist names`;
}

function titleCaseStatus(status) {
  const label = statusLabel(status);
  return label ? label.charAt(0).toUpperCase() + label.slice(1) : "Filtered";
}

function metricCard(label, value, note) {
  return `
    <div class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(note || "")}</small>
    </div>
  `;
}

function stat(label, value) {
  return `
    <div class="stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function statusPill(status) {
  return `<span class="status-pill status-${escapeAttribute(status)}">${escapeHtml(status)}</span>`;
}

function sidePill(category) {
  const label = category === "option" ? "Options" : "Equity";
  return `<span class="side-pill side-${escapeAttribute(category || "equity")}">${escapeHtml(label)}</span>`;
}

function emptyState() {
  return document.querySelector("#emptyStateTemplate").innerHTML;
}

function renderLoadError(error) {
  els.dataStatus.textContent = "Data file not found";
  Object.values(els.views).forEach((view) => {
    view.innerHTML = `
      <div class="empty-state">
        <h2>Run the data refresh</h2>
        <p>Expected data/processed/dashboard.json. Error: ${escapeHtml(error.message)}</p>
      </div>
    `;
  });
}

function formatMoney(value) {
  const number = Number(value || 0);
  const abs = Math.abs(number);
  const sign = number < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function formatPercent(value) {
  if (!Number.isFinite(Number(value))) return "0%";
  return `${(Number(value) * 100).toFixed(Math.abs(value) < 0.1 ? 1 : 0)}%`;
}

function formatNumber(value, digits = 0) {
  const number = Number(value || 0);
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(number);
}

function formatDateTime(value) {
  if (!value) return "No data timestamp";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `Updated ${date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`;
}

function reportQuarterLabel(value) {
  const text = String(value || "");
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return text || "Latest available";
  const year = match[1];
  const month = Number(match[2]);
  const quarter = Math.max(1, Math.min(4, Math.ceil(month / 3)));
  return `${year} Q${quarter} (${text})`;
}

function shortDate(value) {
  if (!value) return "";
  const [year, month] = String(value).split("-");
  if (!year || !month) return String(value);
  return `${year.slice(2)}Q${Math.ceil(Number(month) / 3)}`;
}

function sum(values) {
  return values.reduce((total, value) => total + Number(value || 0), 0);
}

function ratio(numerator, denominator) {
  return denominator ? Number(numerator || 0) / Number(denominator) : 0;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

init();
