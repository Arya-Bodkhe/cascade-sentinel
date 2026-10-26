import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const NAV = [
  ['overview', 'Overview'], ['map', 'Grid map'], ['evidence', 'Evidence'],
  ['policy', 'Decision & policy'], ['ledger', 'Why-ledger'],
  ['replay', 'Replay lab'], ['method', 'Method'],
];
const DEFAULT_THRESHOLDS = {
  p_prepare: 0.25, p_alert: 0.50, p_escalate: 0.70,
  rain_3d_prepare: 80, rain_3d_alert: 150, rain_3d_escalate: 220,
  rain24_alert: 80, rain24_escalate: 120, trigger_3d: 150, trigger_24h: 80,
  hysteresis: true, k_down: 2,
};
const ACTION_STYLE = {
  WATCH: 'green', PREPARE: 'yellow', ALERT: 'orange', ESCALATE: 'red',
};
const shortCell = (cell) => (cell || '').replace(/^CELL_/, '').replace('_', '° / ');
const n = (value, digits = 1) => value == null || value === '' || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits);
const pct = (value) => value == null || value === '' || !Number.isFinite(Number(value)) ? '—' : `${(Number(value) * 100).toFixed(0)}%`;

function App() {
  const [tab, setTab] = useState('overview');
  const [mode, setMode] = useState('historical');
  const [eventKey, setEventKey] = useState('2024_sinhagad');
  const [date, setDate] = useState('');
  const [cellId, setCellId] = useState('CELL_18.50_73.75');
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [operatorName, setOperatorName] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState('');
  const [sensitivity, setSensitivity] = useState(null);
  const [sensitivityError, setSensitivityError] = useState('');

  const query = useMemo(() => {
    const p = new URLSearchParams({ mode, event_key: eventKey, cell_id: cellId });
    if (mode === 'historical' && date) p.set('date', date);
    for (const [key, value] of Object.entries(thresholds)) p.set(key, String(value));
    return p.toString();
  }, [mode, eventKey, date, cellId, thresholds]);

  const loadDashboard = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/dashboard?${query}`, { signal, headers: { Accept: 'application/json' } });
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        const text = await response.text();
        throw new Error(`Dashboard API returned HTTP ${response.status}: ${text.slice(0, 240) || 'non-JSON response'}`);
      }
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
      setData(body);
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message || 'Unable to load dashboard data.');
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [query, mode, date]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => loadDashboard(controller.signal), 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [loadDashboard, refresh]);

  useEffect(() => {
    if (tab !== 'replay' || sensitivity) return;
    const controller = new AbortController();
    fetch('/api/sensitivity', { signal: controller.signal })
      .then(async (r) => { const b = await r.json(); if (!r.ok) throw new Error(b.detail || 'Sensitivity data unavailable'); return b; })
      .then(setSensitivity)
      .catch((e) => { if (e.name !== 'AbortError') setSensitivityError(e.message); });
    return () => controller.abort();
  }, [tab, sensitivity]);

  const updateThreshold = (key, value) => {
    if (key === 'hysteresis') {
      setThresholds((prev) => ({ ...prev, hysteresis: Boolean(value) }));
      return;
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    setThresholds((prev) => {
      const next = { ...prev, [key]: numeric };
      if (key === 'p_prepare') next.p_prepare = Math.min(numeric, next.p_alert);
      if (key === 'p_alert') {
        next.p_alert = Math.max(next.p_prepare, numeric);
        next.p_escalate = Math.max(next.p_escalate, next.p_alert);
      }
      if (key === 'p_escalate') next.p_escalate = Math.max(next.p_alert, numeric);
      if (key === 'rain_3d_prepare') next.rain_3d_prepare = Math.min(numeric, next.rain_3d_alert);
      if (key === 'rain_3d_alert') {
        next.rain_3d_alert = Math.max(next.rain_3d_prepare, numeric);
        next.rain_3d_escalate = Math.max(next.rain_3d_escalate, next.rain_3d_alert);
      }
      if (key === 'rain_3d_escalate') next.rain_3d_escalate = Math.max(next.rain_3d_alert, numeric);
      if (key === 'rain24_alert') next.rain24_escalate = Math.max(next.rain24_escalate, numeric);
      if (key === 'rain24_escalate') next.rain24_escalate = Math.max(next.rain24_alert, numeric);
      return next;
    });
  };

  const selectedAction = data?.decision?.action_name || 'WATCH';
  const actionColor = ACTION_STYLE[selectedAction] || 'green';
  const isConfirmed = (data?.ledger?.entries || []).some((entry) =>
    entry.action_to === 'CONFIRMED_ESCALATE' && entry.t === data?.selected_date &&
    entry.input_hash === `${eventKey}:${data?.selected_date}`
  );

  async function confirmRecommendation() {
    if (!data || selectedAction !== 'ESCALATE' || !operatorName.trim()) return;
    setConfirming(true);
    setConfirmMessage('');
    try {
      const body = {
        event_key: eventKey, date: data.selected_date, operator_name: operatorName.trim(),
        thresholds: {
          p_prepare: thresholds.p_prepare, p_alert: thresholds.p_alert, p_escalate: thresholds.p_escalate,
          rain_3d_prepare_mm: thresholds.rain_3d_prepare, rain_3d_alert_mm: thresholds.rain_3d_alert,
          rain_3d_escalate_mm: thresholds.rain_3d_escalate, rain_24h_alert_mm: thresholds.rain24_alert,
          rain_24h_escalate_mm: thresholds.rain24_escalate,
        },
        trigger_3d: thresholds.trigger_3d, trigger_24h: thresholds.trigger_24h,
        hysteresis: thresholds.hysteresis, k_down: thresholds.k_down,
      };
      const response = await fetch('/api/ledger/confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Acknowledgment was not recorded');
      setData((prev) => ({ ...prev, ledger: { entries: result.entries, verified: result.verified, count: result.count } }));
      setConfirmMessage('Acknowledgment appended to the verified hash chain. No dispatch or public notification was sent.');
    } catch (e) {
      setConfirmMessage(e.message || 'Unable to record acknowledgment.');
    } finally {
      setConfirming(false);
    }
  }

  function changeEvent(key) {
    setEventKey(key);
    setDate('');
    setSensitivity(null);
    setSensitivityError('');
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview" onClick={() => setTab('overview')} aria-label="Cascade Sentinel overview">
          <span className="brand-mark">CS</span>
          <span><strong>CASCADE</strong><small>SENTINEL · PUNE</small></span>
        </a>
        <div className="side-label">COMMAND CENTER</div>
        <nav className="nav-list" aria-label="Dashboard sections">
          {NAV.map(([key, label], i) => (
            <button key={key} className={`nav-item ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>
              <span className="nav-num">{String(i + 1).padStart(2, '0')}</span>{label}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="side-foot"><span className="pulse-dot" /> LOCAL API <span className="foot-version">v1.0</span></div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">PUNE DISTRICT <span>/</span> {NAV.find(([key]) => key === tab)?.[1].toUpperCase()}</div>
          <div className="top-controls">
            <label className="mode-control">MODE
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="historical">Historical replay</option>
                <option value="live">Live cell advisory</option>
              </select>
            </label>
            <button className="refresh-button" onClick={() => setRefresh((x) => x + 1)} disabled={loading} title="Refresh evidence">↻ <span>Refresh</span></button>
          </div>
        </header>

        {data && <StatusBar data={data} loading={loading} />}
        {mode === 'live' && data && (
          <div className={`notice ${String(data.status).startsWith('OFFLINE-DEMO') ? 'notice-danger' : 'notice-warning'}`}>
            <strong>{String(data.status).startsWith('OFFLINE-DEMO') ? 'DEMO DATA — NOT FOR OPERATIONAL USE' : 'LIVE SCOPE LIMITATION'}</strong>
            <span>{data.scope_note} {data.status_detail}</span>
          </div>
        )}
        {error && <div className="error-box" role="alert"><strong>Dashboard data unavailable</strong><span>{error}</span><button onClick={() => setRefresh((x) => x + 1)}>Retry</button></div>}
        {loading && !data && !error && <div className="loading-screen"><div className="spinner" /><span>Loading Pune rainfall evidence and replay…</span></div>}

        {data && !error && (
          <div className="page-content" aria-busy={loading}>
            {tab === 'overview' && <Overview data={data} mode={mode} eventKey={eventKey} date={date} onEvent={changeEvent} onDate={setDate} thresholds={thresholds} onCell={setCellId} onTab={setTab} actionColor={actionColor} isConfirmed={isConfirmed} operatorName={operatorName} onOperator={setOperatorName} onConfirm={confirmRecommendation} confirming={confirming} confirmMessage={confirmMessage} />}
            {tab === 'map' && <MapPage data={data} selectedCell={cellId} onCell={setCellId} mode={mode} />}
            {tab === 'evidence' && <EvidencePage data={data} mode={mode} />}
            {tab === 'policy' && <PolicyPage data={data} thresholds={thresholds} onThreshold={updateThreshold} />}
            {tab === 'ledger' && <LedgerPage data={data} />}
            {tab === 'replay' && <ReplayPage data={data} eventKey={eventKey} onEvent={changeEvent} sensitivity={sensitivity} sensitivityError={sensitivityError} onReloadSensitivity={() => { setSensitivity(null); setSensitivityError(''); }} />}
            {tab === 'method' && <MethodPage data={data} />}
          </div>
        )}
        <footer className="footer-disclaimer">DECISION SUPPORT ONLY · ESCALATE IS A RECOMMENDATION · AUTHORIZED HUMAN REVIEW REQUIRED · NO AUTOMATED DISPATCH</footer>
      </main>
    </div>
  );
}

function StatusBar({ data, loading }) {
  const statusClass = String(data.status).startsWith('LIVE') ? 'live' : String(data.status).startsWith('CACHED') ? 'cached' : String(data.status).startsWith('OFFLINE-DEMO') ? 'danger' : 'provided';
  return <div className="status-strip">
    <span className={`status-pill ${statusClass}`}><i />{data.status}</span>
    <span className="status-scope">{data.mode === 'live' ? shortCell(data.selected_cell) : `${data.event?.hazard_type || 'Historical evidence'} · ${data.selected_date}`}</span>
    {loading && <span className="small-loading">Updating…</span>}
    <span className="ist-clock">IST · {new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date())}</span>
  </div>;
}

function PageTitle({ eyebrow, title, description, right }) {
  return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{right}</div>;
}

function EventControl({ data, eventKey, date, onEvent, onDate }) {
  const events = data.events || [];
  return <div className="event-controls">
    <label>HISTORICAL EVENT<select value={eventKey} onChange={(e) => onEvent(e.target.value)}>{events.map((e) => <option key={e.key} value={e.key}>{e.title}</option>)}</select></label>
    <label>REPLAY DATE<select value={date || data.selected_date} onChange={(e) => onDate(e.target.value)}>{(data.event_dates || []).map((d) => <option key={d} value={d}>{d}{d === data.event?.peak_date ? ' · peak' : ''}</option>)}</select></label>
  </div>;
}

function Metric({ label, value, unit, hint, tone }) {
  return <article className="metric-card"><div className="metric-label">{label}</div><div className={`metric-value ${tone || ''}`}>{value}<small>{unit}</small></div>{hint && <div className="metric-hint">{hint}</div>}</article>;
}

function Overview({ data, mode, eventKey, date, onEvent, onDate, thresholds, onCell, onTab, actionColor, isConfirmed, operatorName, onOperator, onConfirm, confirming, confirmMessage }) {
  const s = data.summary; const d = data.decision; const c = data.cell_evidence;
  const rank = [...(s.cells || [])].sort((a, b) => (b.rain_3d_mm || 0) - (a.rain_3d_mm || 0)).slice(0, 7);
  return <>
    <PageTitle eyebrow="OPERATIONAL PICTURE" title="District overview" description="Rainfall evidence, model recommendation, and historical context — joined from the same decision API." right={mode === 'historical' ? <EventControl data={data} eventKey={eventKey} date={date} onEvent={onEvent} onDate={onDate} /> : null} />
    <div className="metric-grid">
      <Metric label="Recommended action" value={d.action_name} hint={d.requires_human_confirm ? 'Human review required' : 'Advisory only'} tone={`tone-${actionColor}`} />
      <Metric label="P(CASCADE) · heuristic" value={pct(data.risk.p_cascade)} hint="Not a calibrated forecast" />
      <Metric label={mode === 'live' ? 'Selected cell · 24h rain' : 'District max · 3-day rain'} value={n(mode === 'live' ? s.district_max_1d_mm : s.district_max_3d_mm)} unit="mm" hint={mode === 'live' ? 'Trailing 24 valid hours' : `Peak cell ${shortCell(s.district_max_cell)}`} />
      <Metric label="Landslide trigger index" value={n(s.max_landslide_trigger_index, 2)} hint={`${s.max_landslide_risk_cell ? shortCell(s.max_landslide_risk_cell) : 'Selected cell'} · assumption-based`} />
      <Metric label="District grid coverage" value="24 / 24" unit="cells" hint="16 excluded border cells shown separately" />
    </div>

    <div className="decision-banner">
      <div className={`decision-symbol ${actionColor}`}>{d.action_level}</div>
      <div className="decision-copy"><div className="eyebrow">OPERATIONAL RATIONALE · {d.rule_fired}</div><p>{d.plain_reason}</p><small>Reverses / advances if: {d.reverses_if}</small></div>
      {d.requires_human_confirm && <span className={`confirm-state ${isConfirmed ? 'confirmed' : ''}`}>{isConfirmed ? 'ACKNOWLEDGED' : 'HUMAN REVIEW REQUIRED'}</span>}
    </div>

    {d.requires_human_confirm && <div className="human-review">
      <div><strong>ESCALATE recommendation — no dispatch is performed here.</strong><p>Logging below records an operator acknowledgment only. The app does not authenticate identity or send sirens, alerts, or evacuation notices.</p></div>
      {!isConfirmed && <div className="ack-form"><input aria-label="Operator name" value={operatorName} maxLength={120} minLength={2} onChange={(e) => onOperator(e.target.value)} placeholder="Operator name" /><button className="button-danger" onClick={onConfirm} disabled={confirming || operatorName.trim().length < 2}>{confirming ? 'Recording…' : 'Acknowledge & log'}</button></div>}
      {isConfirmed && <span className="verified-inline">Hash chain verified · acknowledgment recorded</span>}
      {confirmMessage && <div className="inline-message" role="status">{confirmMessage}</div>}
    </div>}

    <div className="content-grid two-one">
      <section className="panel"><PanelHead title={mode === 'live' ? 'Recent selected-cell telemetry' : 'Rainfall & risk replay'} meta={mode === 'live' ? 'Open-Meteo hourly · selected cell' : `${data.event?.start_date} — ${data.event?.end_date}`} />
        {mode === 'live' ? <HourlyChart rows={data.hourly || []} /> : <RainChart rows={data.timeline || []} activeDate={data.selected_date} onPick={onDate} />}
        <div className="chart-legend"><span><i className="legend-bar" />24h maximum</span>{mode !== 'live' && <><span><i className="legend-line indigo" />3-day total</span><span><i className="legend-line red" />P(CASCADE)</span></>}</div>
      </section>
      <section className="panel"><PanelHead title="Highest 3-day rainfall" meta="In-district cells only" />
        <div className="rank-list">{rank.map((row, i) => <button key={row.cell_id} className={`rank-row ${row.cell_id === c.cell_id ? 'selected' : ''}`} onClick={() => { onCell(row.cell_id); onTab('map'); }}><span className="rank-num">{String(i + 1).padStart(2, '0')}</span><span className="rank-cell">{shortCell(row.cell_id)}<small>{row.taluka_label}</small></span><span className="rank-bar-wrap"><i style={{ width: `${Math.max(2, Math.min(100, (row.rain_3d_mm / Math.max(s.district_max_3d_mm, 1)) * 100))}%` }} /></span><strong>{n(row.rain_3d_mm)} <small>mm</small></strong></button>)}</div>
        <button className="text-button" onClick={() => onTab('map')}>Open full grid map →</button>
      </section>
    </div>
    <div className="scope-note"><b>Scope & provenance</b><span>{data.scope_note} {data.risk.classification}. Historical data carries PROVIDED-DATA provenance; assumptions are identified in Method.</span></div>
  </>;
}

function PanelHead({ title, meta, action }) { return <div className="panel-head"><div><h2>{title}</h2>{meta && <span>{meta}</span>}</div>{action}</div>; }

function RainChart({ rows, activeDate, onPick }) {
  if (!rows.length) return <div className="empty-chart">No replay points are available for this event.</div>;
  const W = 760, H = 270, left = 45, right = 46, top = 20, bottom = 40;
  const plotW = W - left - right, plotH = H - top - bottom;
  const maxRain = Math.max(100, ...rows.map((r) => Number(r.district_max_1d_mm) || 0), ...rows.map((r) => Number(r.district_max_3d_mm) || 0));
  const x = (i) => left + (rows.length === 1 ? plotW / 2 : (i * plotW) / (rows.length - 1));
  const yRain = (v) => top + plotH - ((Number(v) || 0) / maxRain) * plotH;
  const yRisk = (v) => top + plotH - (Number(v) || 0) * plotH;
  const line3d = rows.map((r, i) => `${x(i)},${yRain(r.district_max_3d_mm)}`).join(' ');
  const lineP = rows.map((r, i) => `${x(i)},${yRisk(r.p_cascade)}`).join(' ');
  const grid = [0, 0.5, 1].map((f) => top + plotH * f);
  return <div className="chart-wrap"><svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Rainfall and cascade risk timeline">
    {grid.map((gy, i) => <g key={i}><line x1={left} x2={W - right} y1={gy} y2={gy} className="chart-grid" /><text x={left - 8} y={gy + 4} textAnchor="end" className="chart-axis">{Math.round(maxRain * (1 - i * 0.5))}</text><text x={W - right + 8} y={gy + 4} className="chart-axis">{100 - i * 50}%</text></g>)}
    {rows.map((r, i) => { const bw = Math.max(5, plotW / rows.length * 0.42); return <g key={r.date} className="chart-point" onClick={() => onPick?.(r.date)} role="button" tabIndex="0" onKeyDown={(e) => e.key === 'Enter' && onPick?.(r.date)}><title>{`${r.date}: 24h ${n(r.district_max_1d_mm)} mm · 3d ${n(r.district_max_3d_mm)} mm · risk ${pct(r.p_cascade)} · ${r.action_name}`}</title><rect x={x(i) - bw / 2} y={yRain(r.district_max_1d_mm)} width={bw} height={Math.max(1, top + plotH - yRain(r.district_max_1d_mm))} rx="2" className={r.date === activeDate ? 'bar-active' : 'bar-rain'} /><line x1={x(i)} x2={x(i)} y1={top} y2={top + plotH} className={r.date === activeDate ? 'selected-rule' : 'point-rule'} /><circle cx={x(i)} cy={yRisk(r.p_cascade)} r={r.date === activeDate ? 5 : 3} className="risk-dot" /></g>; })}
    <polyline points={line3d} className="rain-line" fill="none" /><polyline points={lineP} className="risk-line" fill="none" />
    {rows.map((r, i) => <text key={`d${r.date}`} x={x(i)} y={H - 13} textAnchor="middle" className="chart-axis">{r.date.slice(5)}</text>)}
  </svg></div>;
}

function HourlyChart({ rows }) {
  if (!rows.length) return <div className="empty-chart">No hourly rows available.</div>;
  const W = 760, H = 245, left = 36, right = 16, top = 18, bottom = 36, plotW = W - left - right, plotH = H - top - bottom;
  const max = Math.max(1, ...rows.map((x) => Number(x.rain_mm_h) || 0));
  const step = plotW / rows.length;
  return <div className="chart-wrap"><svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Hourly rain telemetry"><line x1={left} x2={W - right} y1={top + plotH} y2={top + plotH} className="chart-grid" />{rows.map((row, i) => { const val = Number(row.rain_mm_h) || 0; const h = val / max * plotH; return <g key={row.time}><title>{row.time}: {n(val, 2)} mm · {row.provenance}</title><rect x={left + i * step + 0.5} y={top + plotH - h} width={Math.max(1, step - 1)} height={Math.max(1, h)} className={row.provenance === 'FORECAST' ? 'bar-forecast' : 'bar-rain'} /></g>; })}<text x={left} y={H - 12} className="chart-axis">96 recent valid hours</text><text x={W - right} y={H - 12} textAnchor="end" className="chart-axis">Forecast rows retain FORECAST provenance</text></svg></div>;
}

function MapPage({ data, selectedCell, onCell, mode }) {
  const cells = data.cells || [];
  const W = 860, H = 470, left = 66, right = 42, top = 35, bottom = 54;
  const x = (lon) => left + ((Number(lon) - 72.85) / (74.9 - 72.85)) * (W - left - right);
  const y = (lat) => top + ((19.15 - Number(lat)) / (19.15 - 17.85)) * (H - top - bottom);
  const inDistrict = cells.filter((c) => c.in_district);
  const excluded = cells.filter((c) => !c.in_district);
  const color = (c) => {
    const rain = Number(c.rain_1d_mm) || 0; const index = Number(c.landslide_trigger_index) || 0;
    if (index >= 0.7 || rain >= 100) return '#F16E65';
    if (index >= 0.45 || rain >= 60) return '#f2a15d';
    if (index >= 0.25 || rain >= 30) return '#f0d16a';
    return '#47c69a';
  };
  return <>
    <PageTitle eyebrow="SPATIAL EVIDENCE" title="40-cell rainfall grid" description="Click an in-district square to inspect local rainfall, susceptibility proxy, and evidence. Excluded cells are shown but never enter district aggregates." />
    {mode === 'live' && <div className="notice notice-warning"><strong>Historical reference map</strong><span>Only the selected cell is queried live. These 40 plotted values remain from the last historical IMD date.</span></div>}
    <section className="panel map-panel"><PanelHead title="IMD 0.25° grid" meta={`24 in district · ${excluded.length} excluded`} />
      <div className="map-scroll"><svg className="grid-map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Interactive Pune 40 cell map">
        {[73, 73.25, 73.5, 73.75, 74, 74.25, 74.5, 74.75].map((lon) => <g key={lon}><line x1={x(lon)} x2={x(lon)} y1={top} y2={H - bottom} className="map-gridline"/><text x={x(lon)} y={H - 25} textAnchor="middle" className="map-axis">{lon.toFixed(2)}°E</text></g>)}
        {[18, 18.25, 18.5, 18.75, 19].map((lat) => <g key={lat}><line x1={left} x2={W - right} y1={y(lat)} y2={y(lat)} className="map-gridline"/><text x={left - 12} y={y(lat) + 4} textAnchor="end" className="map-axis">{lat.toFixed(2)}°N</text></g>)}
        <line x1={x(73.4)} x2={x(73.4)} y1={top} y2={H - bottom} className="crest-line"/><text x={x(73.4) + 7} y={top + 12} className="crest-label">WESTERN GHATS DIVIDE</text>
        {excluded.map((c) => <g key={c.cell_id} className="map-cell excluded"><title>{`${c.cell_id} · excluded · ${c.exclusion_reason || 'outside boundary'} · ${n(c.rain_1d_mm)} mm/day`}</title><rect x={x(c.lon) - 15} y={y(c.lat) - 15} width="30" height="30" rx="5"/><text x={x(c.lon)} y={y(c.lat) + 3} textAnchor="middle">×</text></g>)}
        {inDistrict.map((c) => <g key={c.cell_id} className={`map-cell ${selectedCell === c.cell_id ? 'map-selected' : ''}`} tabIndex="0" role="button" onClick={() => onCell(c.cell_id)} onKeyDown={(e) => e.key === 'Enter' && onCell(c.cell_id)}><title>{`${c.cell_id} · ${c.taluka_label} · 24h ${n(c.rain_1d_mm)} mm · 3d ${n(c.rain_3d_mm)} mm · landslide index ${n(c.landslide_trigger_index, 2)}`}</title><rect x={x(c.lon) - 18} y={y(c.lat) - 18} width="36" height="36" rx="6" fill={color(c)}/><text x={x(c.lon)} y={y(c.lat) + 3} textAnchor="middle">{gridKey(c)}</text></g>)}
      </svg></div>
      <div className="map-legend"><span><i className="swatch green" />Lower trigger index</span><span><i className="swatch yellow" />Elevated rainfall</span><span><i className="swatch orange" />High rainfall</span><span><i className="swatch red" />High trigger index</span><span><i className="swatch excluded" />Excluded / border</span><span>Grid key: row A–E (south→north), column 1–8; hover for full cell ID.</span></div>
    </section>
    <section className="panel selected-cell-panel"><PanelHead title={`Selected: ${shortCell(selectedCell)}`} meta={data.cell_evidence?.taluka_label || 'Nearest taluka proxy'} />
      <div className="detail-grid"><Detail label="1-day rainfall" value={`${n(data.cell_evidence?.rain_1d_mm)} mm`} /><Detail label="3-day accumulation" value={`${n(data.cell_evidence?.rain_3d_mm)} mm`} /><Detail label="Susceptibility prior" value={n(data.cell_evidence?.susceptibility_prior, 2)} /><Detail label="GLC proximity" value={Number.isFinite(Number(data.cell_evidence?.glc_dist_km)) ? `${n(data.cell_evidence.glc_dist_km)} km` : '—'} /><Detail label="Landslide trigger index" value={n(data.cell_evidence?.landslide_trigger_index, 2)} /><Detail label="Quality flag" value={data.cell_evidence?.quality_flag || '—'} /></div>
    </section>
  </>;
}

function Detail({ label, value }) { return <div className="detail-item"><span>{label}</span><strong>{value}</strong></div>; }
function gridKey(cell) { return `${String.fromCharCode(65 + Math.round((Number(cell.lat) - 18) / 0.25))}${Math.round((Number(cell.lon) - 73) / 0.25) + 1}`; }

function EvidencePage({ data, mode }) {
  const a = data.summary.source_agreement || {};
  const c = data.cell_evidence || {};
  return <>
    <PageTitle eyebrow="MULTI-SOURCE EVIDENCE" title="Evidence & provenance" description="Separate observed-derived, model, cached, and assumed evidence; no silent averaging of disagreeing products." />
    <div className="content-grid two-one">
      <section className="panel"><PanelHead title="Source agreement at Pune reference cell" meta={data.selected_date} />
        <div className="agreement-status"><span className={`agreement-dot ${a.status === 'STRONG_AGREEMENT' ? 'ok' : a.status === 'HIGH_CONFLICT' ? 'bad' : 'warn'}`} /><strong>{a.status || 'SINGLE SOURCE'}</strong><span>Confidence penalty: {pct(a.confidence_penalty ?? 0)}</span></div>
        <div className="compare-bars">{[['IMD gridded', a.imd_rain_mm], ['Open-Meteo point', a.om_rain_mm]].map(([label, val]) => <div className="compare-row" key={label}><div><span>{label}</span><strong>{val == null ? 'No data' : `${n(val)} mm`}</strong></div><i><b style={{ width: `${Math.min(100, (Number(val) || 0) / Math.max(1, Number(a.imd_rain_mm) || 0, Number(a.om_rain_mm) || 0) * 100)}%` }} /></i></div>)}</div>
        <p className="fineprint">Δ {a.abs_delta_mm == null ? '—' : `${n(a.abs_delta_mm)} mm`} · {a.note || 'Sources are reported separately.'}</p>
      </section>
      <section className="panel"><PanelHead title="Selected-cell evidence" meta={c.cell_id} />
        <div className="evidence-numbers"><Detail label="1-day" value={`${n(c.rain_1d_mm)} mm`} /><Detail label="2-day" value={`${n(c.rain_2d_mm)} mm`} /><Detail label="3-day" value={`${n(c.rain_3d_mm)} mm`} /><Detail label="7-day" value={`${n(c.rain_7d_mm)} mm`} /><Detail label="Historical percentile" value={c.percentile_rank == null ? '—' : `${n(c.percentile_rank, 0)}th`} /><Detail label="Data quality" value={c.quality_flag || '—'} /></div>
        <div className="tag-row"><span className="source-tag provided">{mode === 'live' ? data.status : 'PROVIDED-DATA'}</span><span className="source-tag assumed">SUSCEPTIBILITY · ASSUMPTION</span></div>
      </section>
    </div>
    <section className="panel provenance-panel"><PanelHead title="Arrival lag & source boundaries" />
      <div className="three-cards"><Detail label="IMD daily gridded" value="T+1 day modeled arrival · assumed" /><Detail label="Open-Meteo reanalysis" value="Pune point, hourly · source estimate" /><Detail label="Live provider" value="7 past days + 72h forecast · selected cell only" /></div>
      <p className="fineprint">Rainfall grid values are IMD gridded estimates, not station observations. Open-Meteo is a separate gridded estimate. Missing data remains missing; no missing rainfall is treated as zero for source comparison.</p>
    </section>
  </>;
}

function PolicyPage({ data, thresholds, onThreshold }) {
  const scenarios = data.scenarios || [];
  const controls = [
    ['p_prepare', 'P(CASCADE) PREPARE', 0, 1, 0.01, true], ['p_alert', 'P(CASCADE) ALERT', 0, 1, 0.01, true], ['p_escalate', 'P(CASCADE) ESCALATE', 0, 1, 0.01, true],
    ['rain_3d_prepare', '3-day PREPARE (mm)', 0, 500, 5], ['rain_3d_alert', '3-day ALERT (mm)', 0, 500, 5], ['rain_3d_escalate', '3-day ESCALATE (mm)', 0, 500, 5],
    ['rain24_alert', '24-hour ALERT (mm)', 0, 300, 5], ['rain24_escalate', '24-hour ESCALATE (mm)', 0, 300, 5],
    ['trigger_3d', 'Landslide index 3-day reference (mm)', 1, 500, 5], ['trigger_24h', 'Landslide index 24-hour reference (mm)', 1, 300, 5],
  ];
  return <>
    <PageTitle eyebrow="RECOMMENDATION ENGINE" title="Decision & policy" description="Thresholds are validated in order, and the same configured policy drives the recommendation and replay trace." />
    <div className="content-grid two-one">
      <section className="panel"><PanelHead title="Editable action thresholds" meta="ASSUMPTION · tune locally" />
        <div className="threshold-grid">{controls.map(([key, label, min, max, step, isProb]) => <label className="threshold-control" key={key}><span>{label}<b>{isProb ? n(thresholds[key] * 100, 0) + '%' : n(thresholds[key], 0)}</b></span><input type="range" min={min} max={max} step={step} value={thresholds[key]} onChange={(e) => onThreshold(key, e.target.value)} /></label>)}</div>
        <div className="threshold-grid small-thresholds"><label className="threshold-control check-control"><span>Anti-flapping hysteresis<b>{thresholds.hysteresis ? 'Enabled' : 'Disabled'}</b></span><input type="checkbox" checked={thresholds.hysteresis} onChange={(e) => onThreshold('hysteresis', e.target.checked)} /></label><label className="threshold-control"><span>Consecutive lower checks<b>{thresholds.k_down}</b></span><input type="range" min="1" max="4" value={thresholds.k_down} onChange={(e) => onThreshold('k_down', e.target.value)} /></label></div>
        <p className="fineprint">PREPARE ≤ ALERT ≤ ESCALATE is enforced. Rising risk escalates immediately; reductions require the configured number of replay steps. Live mode is a one-cell snapshot and cannot establish a multi-step de-escalation history.</p>
      </section>
      <section className="panel"><PanelHead title="Current recommendation" meta={data.selected_date} />
        <div className={`big-action ${ACTION_STYLE[data.decision.action_name] || 'green'}`}>{data.decision.action_name}</div>
        <p className="policy-reason">{data.decision.plain_reason}</p>
        <div className="policy-facts"><Detail label="Rule fired" value={data.decision.rule_fired} /><Detail label="Probability" value={pct(data.decision.p_cascade)} /><Detail label="Hysteresis" value={thresholds.hysteresis ? `k = ${thresholds.k_down}` : 'Off'} /><Detail label="Outcome feedback" value="Unavailable; fatigue penalty off" /></div>
        {data.decision.requires_human_confirm && <div className="notice notice-danger"><strong>RECOMMENDATION ONLY</strong><span>Requires authorized human review. This software cannot dispatch public sirens.</span></div>}
      </section>
    </div>
    <section className="panel ladder-panel"><PanelHead title="Four-stage action ladder" />
      <div className="ladder-grid">{[['WATCH', 'Routine monitoring', 'Green'], ['PREPARE', 'Stage field and municipal assets', 'Yellow'], ['ALERT', 'Mobilize emergency operations', 'Orange'], ['ESCALATE', 'Public action recommendation · human authority required', 'Red']].map(([name, desc, color]) => <div className={`ladder-step ${data.decision.action_name === name ? 'current' : ''}`} key={name}><span className={`stage-dot ${color.toLowerCase()}`} /><strong>{name}</strong><small>{desc}</small></div>)}</div>
    </section>
    <section className="panel"><PanelHead title="Scripted policy checks" meta="CURRENT CONFIGURATION" /><div className="replay-table-wrap"><table><thead><tr><th>Scenario</th><th>Expected</th><th>Actual</th><th>Result</th><th>Triggered rule</th></tr></thead><tbody>{scenarios.map((row) => <tr key={row.Scenario}><td>{row.Scenario}</td><td>{row['Expected Action']}</td><td>{row['Actual Action']}</td><td><span className={`action-mini ${row.Match === '[PASS]' ? 'green' : 'red'}`}>{row.Match}</span></td><td>{row['Rule Fired']}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><PanelHead title="Operational cost model" meta="UNVALIDATED ASSUMPTIONS" /><div className="three-cards"><Detail label="Unmitigated damage D" value="100 (relative units)" /><Detail label="False-alarm costs" value="0 / 3 / 30 / 62 · assumed" /><Detail label="Damage mitigation ρ" value="0 / .25 / .60 / .85" /></div></section>
  </>;
}

function LedgerPage({ data }) {
  const ledger = data.ledger || { entries: [], verified: true, count: 0 };
  const entries = [...(ledger.entries || [])].reverse();
  const download = () => { const blob = new Blob([JSON.stringify(ledger.entries || [], null, 2)], { type: 'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'cascade-sentinel-why-ledger.json'; link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 0); };
  return <>
    <PageTitle eyebrow="AUDIT TRAIL" title="Hash-chained why-ledger" description="Operator acknowledgments are append-only JSON entries. Verify the SHA-256 chain before relying on this record." right={<button className="button-secondary" onClick={download}>↓ Export JSON</button>} />
    <div className={`integrity-banner ${ledger.verified ? 'integrity-ok' : 'integrity-bad'}`}><span className="integrity-icon">{ledger.verified ? '✓' : '!'}</span><div><strong>{ledger.verified ? 'CHAIN INTEGRITY VERIFIED' : 'INTEGRITY FAILURE'}</strong><small>{ledger.count || 0} entries · SHA-256 linked from genesis · stored locally in project data</small></div></div>
    <section className="panel ledger-panel"><PanelHead title="Audit entries" meta="Newest first" />{!entries.length ? <div className="empty-state"><strong>No operator acknowledgments recorded.</strong><span>Historical recommendations are replayed for analysis; only explicit acknowledgment actions are added to this ledger.</span></div> : <div className="ledger-list">{entries.map((e, i) => <article className="ledger-entry" key={e.hash || i}><div className="ledger-entry-top"><div><span className="ledger-kind">{e.confirmed_by_human ? 'OPERATOR ACKNOWLEDGMENT' : 'DECISION RECORD'}</span><h3>{e.action_from} → {e.action_to}</h3></div><time>{e.timestamp_ist} · {String(e.t)}</time></div><div className="ledger-entry-grid"><Detail label="Rule fired" value={e.rule_fired} /><Detail label="P(CASCADE)" value={pct(e.p_after?.[3])} /><Detail label="Recorded by" value={(e.notes || []).join(' · ') || '—'} /></div><div className="hash-pair"><span>PREV <code>{e.prev_hash}</code></span><span>HASH <code>{e.hash}</code></span></div></article>)}</div>}</section>
    <p className="fineprint">The chain detects edits to stored records but does not provide digital-signature identity, external backup, or tamper-proof hardware storage. Keep backups of <code>data/operations_ledger.json</code>.</p>
  </>;
}

function ReplayPage({ data, eventKey, onEvent, sensitivity, sensitivityError, onReloadSensitivity }) {
  const events = data.events || [];
  return <>
    <PageTitle eyebrow="HISTORICAL VALIDATION" title="Replay laboratory" description="Deterministic, offline event windows with one shared action policy and probability heuristic." right={<label className="replay-picker">EVENT<select value={eventKey} onChange={(e) => onEvent(e.target.value)}>{events.map((e) => <option key={e.key} value={e.key}>{e.title}</option>)}</select></label>} />
    <section className="panel"><PanelHead title={data.event?.title || 'Selected event'} meta={`${data.event?.start_date} → ${data.event?.end_date}`} />
      <div className="event-summary"><Detail label="Hazard type" value={data.event?.hazard_type} /><Detail label="Peak date" value={data.event?.peak_date} /><Detail label="Expected peak action" value={data.event?.expected_peak_action} /><Detail label="GLC match" value={data.event?.confirmed_glc_match || 'None recorded'} /></div>
      <p className="event-description">{data.event?.description}</p>
    </section>
    <section className="panel"><PanelHead title="Replay decision timeline" meta="Select a point by choosing its date in Overview" /><RainChart rows={data.timeline || []} activeDate={data.selected_date} onPick={() => {}} /><div className="replay-table-wrap"><table><thead><tr><th>Date</th><th>24h max</th><th>3-day max</th><th>P(CASCADE)</th><th>Action</th><th>Peak</th></tr></thead><tbody>{(data.timeline || []).map((r) => <tr key={r.date} className={r.is_peak ? 'peak-row' : ''}><td>{r.date}</td><td>{n(r.district_max_1d_mm)} mm</td><td>{n(r.district_max_3d_mm)} mm</td><td>{pct(r.p_cascade)}</td><td><span className={`action-mini ${ACTION_STYLE[r.action_name]}`}>{r.action_name}</span></td><td>{r.is_peak ? 'Peak' : ''}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><PanelHead title="Empirical trigger sensitivity" meta="Historical hits and quiet-day false triggers" action={<button className="text-button" onClick={onReloadSensitivity}>Refresh</button>} />{sensitivityError && <div className="error-box compact"><span>{sensitivityError}</span></div>}{!sensitivity ? <div className="empty-state"><span>Loading sensitivity results…</span></div> : <div className="replay-table-wrap"><table><thead><tr>{Object.keys(sensitivity[0] || {}).map((key) => <th key={key}>{key}</th>)}</tr></thead><tbody>{sensitivity.map((row, i) => <tr key={i}>{Object.values(row).map((value, j) => <td key={j}>{String(value)}</td>)}</tr>)}</tbody></table></div>}</section>
    <section className="panel"><PanelHead title="Historical event registry" /><div className="registry-list">{events.map((e) => <button className={`registry-row ${e.key === eventKey ? 'selected' : ''}`} key={e.key} onClick={() => onEvent(e.key)}><span className="registry-date">{e.peak_date}</span><span><strong>{e.title}</strong><small>{e.hazard_type}</small></span><span className={`action-mini ${ACTION_STYLE[e.expected_peak_action]}`}>{e.expected_peak_action}</span></button>)}</div></section>
  </>;
}

function MethodPage({ data }) {
  return <>
    <PageTitle eyebrow="DATA QUALITY & LIMITATIONS" title="Method & sources" description="Explicit scope, assumptions, provenance, and deployment boundary. This system supports—but never replaces—statutory emergency authority." />
    <div className="content-grid two-one">
      <section className="panel"><PanelHead title="Input data & coverage" /><div className="method-list"><MethodItem name="IMD gridded daily rainfall" tag="PROVIDED-DATA" text="40 grid cells at 0.25° resolution; 24 cells are classified in-district and used for district summaries. Extreme measurements are preserved and flagged for verification." /><MethodItem name="Open-Meteo historical point" tag="PROVIDED-DATA" text="Hourly gridded estimate for the Pune point. Jan–May 2015 is missing and remains NaN rather than being filled with zero." /><MethodItem name="Open-Meteo live endpoint" tag="LIVE / CACHED / DEMO" text="Queries the selected grid point. Cached or offline demo results are distinctly labeled; one point is not district-wide coverage." /><MethodItem name="NASA Global Landslide Catalog" tag="PROVIDED-DATA" text="Sparse event records provide only a weak spatial prior and historical cross-check. They are not used to train a predictive classifier." /></div></section>
      <section className="panel"><PanelHead title="Decision safeguards" /><ul className="method-bullets"><li>Single shared probability formula drives the historical recommendation and replay graph.</li><li>Threshold order is validated by the Python policy model.</li><li>Escalation is a recommendation only; the app cannot dispatch or notify the public.</li><li>Operator acknowledgment is stored in a SHA-256 hash chain, but identity is not authenticated by this app.</li><li>Rainfall susceptibility values are engineering proxies, not a geological susceptibility map.</li><li>Live advisory uses one selected cell and one observation window; no district-wide live service is represented.</li></ul></section>
    </div>
    <section className="panel"><PanelHead title="Probability & operational disclaimer" /><p className="method-copy">{data.risk.formula}</p><p className="method-copy"><strong>Important:</strong> P(CASCADE) is a transparent heuristic, not a statistically calibrated probability. Cost parameters, lag assumptions, susceptibility priors, and trigger thresholds are engineering assumptions. Verify high-risk results independently with field observations and official sources.</p></section>
  </>;
}

function MethodItem({ name, tag, text }) { return <div className="method-item"><div><strong>{name}</strong><span className="source-tag provided">{tag}</span></div><p>{text}</p></div>; }

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
