/* ── Wealth Manager AI Agent — Frontend ─────────────────────── */
'use strict';

// ── State ────────────────────────────────────────────────────
let portfolioData = null;
let sectorChart = null;

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setupNav();
  loadPortfolio();
  setupSearch();
});

// ── Navigation ───────────────────────────────────────────────
function setupNav() {
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const section = link.dataset.section;
      showSection(section);
      document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
      link.classList.add('active');
    });
  });
}

function showSection(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
  // Redraw chart if switching to sectors
  if (id === 'sectors' && portfolioData && sectorChart) sectorChart.update();
}

// ── Portfolio Load ────────────────────────────────────────────
async function loadPortfolio() {
  try {
    const res = await fetch('/api/portfolio');
    if (!res.ok) throw new Error(await res.text());
    const raw = await res.json();
    // Normalize: support both old (holdings/symbol) and new (positions/ticker) schema
    if (raw.positions && !raw.holdings) {
      raw.holdings = raw.positions.map(p => ({
        ...p,
        symbol: p.ticker,
        current_price: p.price,
        market_value: p.market_value,
        unrealized_gain: p.unrealized_gain,
        gain_pct: p.gain_pct,
        is_long_term: p.lt_shares > 0 && p.st_shares === 0,
        holding_type: p.lt_shares === p.shares ? 'Long-Term' : (p.st_shares === p.shares ? 'Short-Term' : 'Mixed'),
        analyst_consensus: p.recommendation,
        analyst_target: null,
        num_lots: p.num_lots,
      }));
    }
    if (!raw.total_market_value) raw.total_market_value = raw.total_portfolio_value;
    if (!raw.num_positions) raw.num_positions = (raw.holdings || []).length;
    portfolioData = raw;
    renderDashboard(portfolioData);
    renderSectors(portfolioData);
    renderHoldings(portfolioData);
  } catch (err) {
    console.error('Portfolio load failed:', err);
    setText('totalValue', 'Error loading data');
  }
}

// ── Dashboard ─────────────────────────────────────────────────
function renderDashboard(p) {
  setText('accountName', p.account_name || 'Portfolio');
  setText('asOfDate', `As of ${p.as_of_date}`);
  setText('totalValue', fmt$(p.total_market_value));
  setText('totalPositions', `${p.num_positions} positions`);

  const gain = p.total_unrealized_gain;
  const gainEl = document.getElementById('totalGain');
  gainEl.textContent = fmtGain(gain);
  gainEl.className = 'metric-value ' + (gain >= 0 ? 'gain' : 'neg');

  setText('totalRetPct', `${gain >= 0 ? '+' : ''}${p.total_return_pct.toFixed(1)}% total return`);

  const ltCount = p.holdings.filter(h => h.is_long_term).length;
  setText('ltCount', `${ltCount} / ${p.num_positions}`);

  const drifting = Object.values(p.sector_drift).filter(d => d.status !== 'ON TARGET').length;
  const rebalEl = document.getElementById('rebalCount');
  rebalEl.textContent = drifting;
  rebalEl.className = 'metric-value ' + (drifting > 2 ? 'warn' : 'gain');

  // Top 5 holdings
  const top5 = [...p.holdings].sort((a, b) => b.market_value - a.market_value).slice(0, 5);
  const tbody = document.getElementById('topHoldingsBody');
  tbody.innerHTML = top5.map(h => `
    <tr>
      <td><strong>${h.symbol}</strong></td>
      <td>${fmt$(h.market_value, 0)}</td>
      <td class="${h.unrealized_gain >= 0 ? 'pos' : 'neg'}">
        ${fmtGain(h.unrealized_gain)}<br>
        <small>${fmtPct(h.gain_pct)}</small>
      </td>
      <td>${consBadge(h.analyst_consensus)}</td>
    </tr>`).join('');

  // Sector drift summary
  const driftList = document.getElementById('driftSummaryList');
  const sorted = Object.entries(p.sector_drift)
    .filter(([, d]) => d.target > 0 || d.actual > 0)
    .sort((a, b) => Math.abs(b[1].drift) - Math.abs(a[1].drift));

  driftList.innerHTML = sorted.map(([sector, d]) => {
    const pct = Math.min(Math.abs(d.drift) / 10 * 100, 100);
    const color = d.status === 'OVERWEIGHT' ? '#dc2626' :
                  d.status === 'UNDERWEIGHT' ? '#ea580c' : '#16a34a';
    return `
      <div class="drift-item">
        <span class="drift-name">${sector}</span>
        <div class="drift-bar-wrap">
          <div class="drift-bar" style="width:${pct}%;background:${color}"></div>
        </div>
        <span class="drift-pct" style="color:${color}">
          ${d.drift >= 0 ? '+' : ''}${d.drift.toFixed(1)}%
        </span>
        <span>${statusBadge(d.status)}</span>
      </div>`;
  }).join('');
}

// ── Sector Analysis ───────────────────────────────────────────
function renderSectors(p) {
  const drift = p.sector_drift;
  const entries = Object.entries(drift)
    .filter(([, d]) => d.target > 0 || d.actual > 0)
    .sort((a, b) => b[1].target - a[1].target);

  const labels  = entries.map(([s]) => s);
  const actuals = entries.map(([, d]) => d.actual);
  const targets = entries.map(([, d]) => d.target);

  if (sectorChart) sectorChart.destroy();
  const ctx = document.getElementById('sectorChart').getContext('2d');
  sectorChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Actual %', data: actuals, backgroundColor: '#2563eb', borderRadius: 4 },
        { label: 'Target %', data: targets, backgroundColor: '#e5e7eb', borderRadius: 4 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'top' } },
      scales: {
        y: { beginAtZero: true, ticks: { callback: v => v + '%' } },
        x: { ticks: { maxRotation: 35 } }
      }
    }
  });

  // Table
  const tbody = document.getElementById('sectorTableBody');
  tbody.innerHTML = entries.map(([sector, d]) => {
    const value = p.holdings
      .filter(h => h.sector === sector)
      .reduce((s, h) => s + h.market_value, 0);
    return `
      <tr>
        <td><strong>${sector}</strong></td>
        <td>${d.actual.toFixed(1)}%</td>
        <td>${d.target.toFixed(1)}%</td>
        <td class="${d.drift >= 0 ? 'pos' : 'neg'}">${d.drift >= 0 ? '+' : ''}${d.drift.toFixed(1)}%</td>
        <td>${fmt$(value, 0)}</td>
        <td>${statusBadge(d.status)}</td>
      </tr>`;
  }).join('');
}

// ── Holdings Table ────────────────────────────────────────────
function renderHoldings(p) {
  renderHoldingsTable(p.holdings);

  // Tax harvesting opportunities
  const losses = p.holdings.filter(h => h.unrealized_gain < 0);
  const listEl = document.getElementById('harvestingList');
  if (losses.length === 0) {
    listEl.innerHTML = '<p class="harvest-empty">No positions with unrealized losses currently.</p>';
  } else {
    listEl.innerHTML = losses.sort((a, b) => a.unrealized_gain - b.unrealized_gain).map(h => {
      const rate = h.is_long_term ? 0.293 : 0.463;
      const benefit = Math.abs(h.unrealized_gain) * rate;
      return `
        <div class="harvest-item">
          <div class="harvest-info">
            <span class="harvest-symbol">${h.symbol} — ${h.name}</span>
            <span class="harvest-detail">
              ${h.shares} shares · ${h.holding_type} ·
              Loss: <span class="neg">${fmtGain(h.unrealized_gain)}</span> (${fmtPct(h.gain_pct)})
            </span>
          </div>
          <div class="harvest-benefit">~${fmt$(benefit, 0)} tax benefit</div>
        </div>`;
    }).join('');
  }
}

function renderHoldingsTable(holdings) {
  const tbody = document.getElementById('holdingsTableBody');
  tbody.innerHTML = holdings.map(h => {
    const upside = h.analyst_target
      ? ((h.analyst_target - h.current_price) / h.current_price * 100).toFixed(1)
      : null;
    return `
      <tr>
        <td><strong>${h.symbol}</strong></td>
        <td style="font-size:11.5px;color:#6b7280">${h.name}</td>
        <td><span class="badge badge-blue" style="font-size:10px">${h.sector}</span></td>
        <td>${h.shares.toLocaleString()}</td>
        <td>${fmt$(h.current_price, 2)}</td>
        <td>${fmt$(h.market_value, 0)}</td>
        <td>${fmt$(h.cost_basis_total, 0)}</td>
        <td class="${h.unrealized_gain >= 0 ? 'pos' : 'neg'}">
          ${fmtGain(h.unrealized_gain)}<br>
          <small>${fmtPct(h.gain_pct)}</small>
        </td>
        <td>
          <span class="badge ${h.is_long_term ? 'badge-green' : 'badge-orange'}">
            ${h.is_long_term ? 'LT' : 'ST'}
          </span>
        </td>
        <td>${consBadge(h.analyst_consensus)}</td>
        <td style="font-size:11.5px;color:#6b7280">
          ${h.analyst_target ? fmt$(h.analyst_target, 0) : '—'}
          ${upside ? `<br><small class="${upside >= 0 ? 'pos' : 'neg'}">${upside >= 0 ? '+' : ''}${upside}%</small>` : ''}
        </td>
      </tr>`;
  }).join('');
}

// ── Search ────────────────────────────────────────────────────
function setupSearch() {
  document.getElementById('holdingsSearch').addEventListener('input', e => {
    const q = e.target.value.toLowerCase();
    if (!portfolioData) return;
    const filtered = portfolioData.holdings.filter(h =>
      h.symbol.toLowerCase().includes(q) ||
      h.sector.toLowerCase().includes(q) ||
      h.name.toLowerCase().includes(q)
    );
    renderHoldingsTable(filtered);
  });
}

// ── AI Analysis ───────────────────────────────────────────────
document.getElementById('runAnalysisBtn').addEventListener('click', runAnalysis);

async function runAnalysis() {
  // Switch to analysis section
  showSection('analysis');
  document.querySelectorAll('.nav-link').forEach(l => {
    l.classList.toggle('active', l.dataset.section === 'analysis');
  });

  setVisible('analysisPlaceholder', false);
  setVisible('analysisContent', false);
  setVisible('analysisError', false);
  setVisible('analysisLoading', true);

  // Animate loading steps
  const steps = [
    'Fetching live portfolio data and prices…',
    'Checking analyst ratings for all holdings…',
    'Calculating tax impact for potential trades…',
    'Screening replacement stocks by sector…',
    'Identifying tax-loss harvesting opportunities…',
    'Synthesizing findings into trading plan…'
  ];
  let stepIdx = 0;
  const stepEl = document.getElementById('loadingStep');
  const stepTimer = setInterval(() => {
    stepEl.textContent = steps[Math.min(++stepIdx, steps.length - 1)];
  }, 8000);

  // Spinner in button
  setVisible('analysisSpinner', true);
  setVisible('analysisBtnText', false);
  document.getElementById('runAnalysisBtn').disabled = true;

  try {
    const res = await fetch('/api/analysis');
    clearInterval(stepTimer);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Analysis failed');
    }
    const plan = await res.json();
    renderAnalysis(plan);
    setVisible('analysisLoading', false);
    setVisible('analysisContent', true);

    // Update health score ring
    if (plan.portfolio_health_score) updateHealthRing(plan.portfolio_health_score);

  } catch (err) {
    clearInterval(stepTimer);
    setVisible('analysisLoading', false);
    const errEl = document.getElementById('analysisError');
    errEl.textContent = `Error: ${err.message}`;
    setVisible('analysisError', true);
    setVisible('analysisPlaceholder', true);
  } finally {
    setVisible('analysisSpinner', false);
    setVisible('analysisBtnText', true);
    document.getElementById('runAnalysisBtn').disabled = false;
  }
}

function renderAnalysis(plan) {
  // Executive summary
  setText('execSummary', plan.executive_summary || '');

  // Key findings
  const findingsEl = document.getElementById('keyFindings');
  findingsEl.innerHTML = (plan.key_findings || []).map((f, i) => `
    <div class="finding-item">
      <span class="finding-num">${i + 1}</span>
      <span>${f}</span>
    </div>`).join('');

  // Sells
  const sellBody = document.getElementById('sellsTableBody');
  const sells = plan.recommended_sells || [];
  sellBody.innerHTML = sells.length ? sells.map(s => `
    <tr>
      <td><strong>${s.symbol}</strong></td>
      <td>${(s.shares || 0).toLocaleString()}</td>
      <td>${fmt$(s.estimated_proceeds || 0, 0)}</td>
      <td>${consBadge(s.analyst_rating || 'Hold')}</td>
      <td style="font-size:11px;color:#6b7280">${s.tax_recommendation || s.tax_impact || '—'}</td>
      <td style="font-size:11.5px">${s.rationale || '—'}</td>
      <td>${priorityBadge(s.priority)}</td>
    </tr>`).join('')
  : '<tr><td colspan="7" style="color:#6b7280;padding:14px">No sell recommendations at this time.</td></tr>';

  // Buys
  const buyBody = document.getElementById('buysTableBody');
  const buys = plan.recommended_buys || [];
  buyBody.innerHTML = buys.length ? buys.map(b => `
    <tr>
      <td><strong>${b.symbol}</strong></td>
      <td>${(b.shares || 0).toLocaleString()}</td>
      <td>${fmt$(b.estimated_cost || 0, 0)}</td>
      <td><span class="badge badge-blue" style="font-size:10px">${b.sector || '—'}</span></td>
      <td>${consBadge(b.analyst_rating || 'Buy')}</td>
      <td style="font-size:11.5px">${b.rationale || '—'}</td>
      <td>${priorityBadge(b.priority, true)}</td>
    </tr>`).join('')
  : '<tr><td colspan="7" style="color:#6b7280;padding:14px">No buy recommendations at this time.</td></tr>';

  // Tax harvesting
  const tlhBody = document.getElementById('harvestTableBody');
  const tlh = plan.tax_loss_harvesting || [];
  tlhBody.innerHTML = tlh.length ? tlh.map(t => `
    <tr>
      <td><strong>${t.symbol}</strong></td>
      <td>${t.action || '—'}</td>
      <td class="pos">${fmt$(t.tax_benefit || 0, 0)}</td>
      <td style="font-size:11.5px">${t.notes || '—'}</td>
    </tr>`).join('')
  : '<tr><td colspan="4" style="color:#6b7280;padding:14px">No harvesting opportunities identified.</td></tr>';

  // Narrative
  const narrative = document.getElementById('narrativeText');
  narrative.textContent = plan.trading_plan_narrative || 'See table above for trading recommendations.';

  // Risks
  const risksList = document.getElementById('risksList');
  risksList.innerHTML = (plan.risk_considerations || []).map(r => `<li>${r}</li>`).join('');

  // Summary row
  const summaryRow = document.getElementById('summaryRow');
  summaryRow.innerHTML = `
    <div class="summary-box">
      <div class="s-label">Total Recommended Trades</div>
      <div class="s-value">${plan.total_estimated_trades ?? (sells.length + buys.length)}</div>
    </div>
    <div class="summary-box">
      <div class="s-label">Net Tax Impact</div>
      <div class="s-value" style="font-size:14px">${plan.net_tax_impact || '—'}</div>
    </div>
    <div class="summary-box">
      <div class="s-label">Expected Improvement</div>
      <div class="s-value" style="font-size:13px">${plan.expected_portfolio_improvement || '—'}</div>
    </div>`;
}

// ── Health Ring ───────────────────────────────────────────────
function updateHealthRing(score) {
  document.getElementById('healthScore').textContent = score;
  const fill = document.getElementById('ringFill');
  fill.setAttribute('stroke-dasharray', `${score}, 100`);
  fill.style.stroke = score >= 75 ? '#16a34a' : score >= 50 ? '#ea580c' : '#dc2626';
}

// ── Helpers ───────────────────────────────────────────────────
function fmt$(n, dec = 0) {
  if (n == null) return '—';
  const abs = Math.abs(n);
  const s = abs.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
  return n < 0 ? `($${s})` : `$${s}`;
}
function fmtGain(n) {
  return (n >= 0 ? '+' : '') + fmt$(n, 0);
}
function fmtPct(n) {
  return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function setVisible(id, visible) {
  const el = document.getElementById(id);
  if (!el) return;
  if (visible) el.classList.remove('hidden');
  else el.classList.add('hidden');
}

function consBadge(c) {
  const map = {
    'Strong Buy': 'badge-green',
    'Buy':        'badge-blue',
    'Hold':       'badge-orange',
    'Sell':       'badge-red',
    'Strong Sell':'badge-red'
  };
  return `<span class="badge ${map[c] || 'badge-gray'}">${c || '—'}</span>`;
}

function statusBadge(s) {
  const map = {
    'OVERWEIGHT': 'badge-red',
    'UNDERWEIGHT': 'badge-orange',
    'ON TARGET': 'badge-green'
  };
  return `<span class="badge ${map[s] || 'badge-gray'}">${s}</span>`;
}

function priorityBadge(p, isBuy = false) {
  if (p === 'HIGH') return `<span class="badge ${isBuy ? 'badge-green' : 'badge-red'}">HIGH</span>`;
  if (p === 'LOW')  return `<span class="badge badge-gray">LOW</span>`;
  return `<span class="badge badge-orange">MED</span>`;
}
