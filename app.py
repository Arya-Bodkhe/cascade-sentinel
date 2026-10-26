"""CASCADE SENTINEL: Pune District Real-Data Decision-Support Dashboard
Operational Decision-Support System for Flood / Urban Waterlogging & Rainfall-Triggered Landslides.
"""
import os
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data.loader_imd import IMDLoader
from src.data.loader_openmeteo import OpenMeteoLoader
from src.data.loader_glc import GLCLoader
from src.data.live_adapter import LiveAdapter
from src.data.evidence_builder import EvidenceBuilder
from src.policy.policy import (
    Policy, ACTIONS, ACTION_COLORS, ActionThresholds, CostModel,
    run_scripted_scenarios
)
from src.ledger.ledger import Ledger
from src.replay_engine import ReplayEngine, HISTORICAL_EVENTS
from src.ui.components import (
    create_rainfall_timeline_figure,
    create_grid_map_figure,
    create_source_agreement_figure
)

# Legacy imports for Synthetic Lab mode
from src.common.model import HYPS, KINDS, H_CAS
from src.belief.engine import Engine
from src.sim.world import generate_episode, generate_twin, STRESSORS
from src.runtime import run_episode

# Backwards compatibility endpoints for synthetic simulation tests
PRESETS = {
    "Custom / Manual": {"seed": 41, "fam": "A", "truth": "CASCADE", "stress": [], "t_now": 9},
    "Scenario 1: Flash Flood": {"seed": 41, "fam": "A", "truth": "CASCADE", "stress": [], "t_now": 9},
    "Scenario 2: Rumor Wave": {"seed": 7, "fam": "A", "truth": "NOISE", "stress": ["rumor"], "t_now": 9},
    "Scenario 3: Gateway Outage": {"seed": 6, "fam": "A", "truth": "SENSOR_FAIL", "stress": ["outage"], "t_now": 9},
    "Scenario 4: Fake Hospital Lie": {"seed": 88, "fam": "A", "truth": "NOISE", "stress": ["lie"], "t_now": 8},
    "Scenario 5: Camera Cutout": {"seed": 104, "fam": "A", "truth": "CASCADE", "stress": ["cutout"], "t_now": 9}
}

def replay_cached(seed, fam, truth, stress, which=0, twin=False, pair=("NOISE", "CASCADE"), cost_params=None):
    rng = np.random.default_rng(seed)
    if twin:
        ep = generate_twin(rng, fam=fam, pair=pair, stress=tuple(stress), split=7.0, T=16)[which]
    else:
        ep = generate_episode(rng, fam=fam, hyp=None if truth == "random" else truth,
                              stress=tuple(stress), T=16)
    
    if cost_params:
        cm = CostModel(D=cost_params[0], gamma=cost_params[1], switch=cost_params[2])
        pol = Policy(cost=cm, hysteresis=cost_params[3], fatigue=cost_params[4], lookahead=cost_params[5])
    else:
        pol = Policy()

    led = Ledger(seed)
    recs = run_episode(ep, Engine(), {"SENTINEL": pol}, T_run=14, seed=seed, ledger=led)
    return ep, recs, led.entries, led.to_json(), led.to_csv(), led.verify()

# -----------------------------------------------------------------------------
# Streamlit Page Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="CASCADE SENTINEL | Pune District",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark theme styling matching emergency crisis operations room
st.markdown("""
<style>
    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    
    .status-bar {
        background: linear-gradient(90deg, #111827 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 10px 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
    }
    
    .badge-tag {
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 4px;
        letter-spacing: 0.05em;
        display: inline-block;
        margin-left: 6px;
    }
    .tag-provided { background: #1e3a8a; color: #93c5fd; border: 1px solid #3b82f6; }
    .tag-live { background: #064e3b; color: #6ee7b7; border: 1px solid #10b981; }
    .tag-cached { background: #78350f; color: #fcd34d; border: 1px solid #f59e0b; }
    .tag-forecast { background: #581c87; color: #d8b4fe; border: 1px solid #a855f7; }
    .tag-assumption { background: #374151; color: #cbd5e1; border: 1px solid #6b7280; }

    .action-chip {
        font-size: 1.05rem;
        font-weight: 800;
        padding: 4px 14px;
        border-radius: 6px;
        letter-spacing: 0.06em;
        display: inline-block;
    }
    .action-watch { background: rgba(16, 185, 129, 0.20); color: #10b981; border: 1px solid #10b981; }
    .action-prepare { background: rgba(250, 204, 21, 0.20); color: #facc15; border: 1px solid #facc15; }
    .action-alert { background: rgba(251, 146, 60, 0.22); color: #fb923c; border: 1px solid #fb923c; }
    .action-escalate { background: rgba(239, 68, 68, 0.28); color: #f87171; border: 1px solid #ef4444; }

    .metric-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }
    .metric-label {
        color: #94a3b8;
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-num {
        font-size: 1.6rem;
        font-weight: 800;
        color: #f8fafc;
        line-height: 1.2;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Global Data Cache Initialization
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_data_system():
    imd = IMDLoader()
    imd.load()
    om = OpenMeteoLoader()
    om.load()
    glc = GLCLoader()
    glc.process_and_export()
    eb = EvidenceBuilder(imd, om, glc)
    eb.build_susceptibility_priors()
    re = ReplayEngine(eb)
    la = LiveAdapter()
    return imd, om, glc, eb, re, la

imd_loader, om_loader, glc_loader, evidence_builder, replay_engine, live_adapter = get_data_system()

# Initialize session state for ledger and human confirmation
if "why_ledger" not in st.session_state:
    st.session_state.why_ledger = Ledger(seed=42)
if "human_confirmations" not in st.session_state:
    st.session_state.human_confirmations = {}
if "demo_step" not in st.session_state:
    st.session_state.demo_step = 0


# -----------------------------------------------------------------------------
# Sidebar Navigation & Operational Controls
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("🛡️ Sentinel Control")
    st.caption("Pune District Decision Support")

    # Mode Selector
    app_mode = st.radio(
        "Operating Mode",
        [
            "Historical Replay (Pune Real Data)",
            "Live Forecast (Open-Meteo)",
            "Synthetic Lab (10-Min Twin Pair)"
        ],
        index=0
    )

    st.markdown("---")

    # Mode-Specific Parameters
    if app_mode == "Historical Replay (Pune Real Data)":
        event_key = st.selectbox(
            "Historical Event",
            list(HISTORICAL_EVENTS.keys()),
            format_func=lambda k: HISTORICAL_EVENTS[k].title,
            index=3  # Default to 2024 Sinhagad Urban Flood
        )
        selected_meta = HISTORICAL_EVENTS[event_key]
        st.info(f"**Hazard:** {selected_meta.hazard_type}\n\n{selected_meta.description}")

        replay_dates = pd.date_range(start=selected_meta.start_date, end=selected_meta.end_date, freq="D").strftime("%Y-%m-%d").tolist()
        peak_idx = replay_dates.index(selected_meta.peak_date) if selected_meta.peak_date in replay_dates else len(replay_dates) // 2

        active_date = st.select_slider(
            "Replay Date (IST)",
            options=replay_dates,
            value=selected_meta.peak_date,
            help="Scrub through the replay window (7 days before peak to 3 days after)."
        )

        in_district_cells = imd_loader.in_district_cells
        selected_cell = st.selectbox(
            "Target Grid Cell",
            in_district_cells,
            index=in_district_cells.index("CELL_18.50_73.75") if "CELL_18.50_73.75" in in_district_cells else 0,
            help="Select in-district IMD grid cell for localized telemetry."
        )

    elif app_mode == "Live Forecast (Open-Meteo)":
        st.info("Live mode queries Open-Meteo API for past 7 days observed + next 72 hours forecast.")
        in_district_cells = imd_loader.in_district_cells
        selected_cell = st.selectbox("Target Grid Cell", in_district_cells, index=0)
        active_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    else:
        # Legacy Synthetic Twin Lab Mode
        sim_truth = st.selectbox("Hidden Truth", ["random"] + HYPS, index=0)
        sim_seed = st.number_input("Seed", 0, 100_000, 41, step=1)
        sim_stress = st.multiselect("Stressors", STRESSORS, default=[])
        sim_t_now = st.slider("Wall-Clock Minute", 1, 14, 9)

    # Advanced Policy Parameters in Collapsed Expander
    with st.expander("⚙ Decision Policy Parameters (Assumptions)"):
        p_prep_in = st.slider("P(CASCADE) for PREPARE", 0.10, 0.45, 0.25, 0.05)
        p_alert_in = st.slider("P(CASCADE) for ALERT", 0.35, 0.70, 0.50, 0.05)
        p_esc_in = st.slider("P(CASCADE) for ESCALATE", 0.60, 0.90, 0.70, 0.05)
        r3d_thresh = st.slider("3-Day Landslide Saturation (mm)", 80.0, 250.0, 150.0, 10.0)
        r24h_thresh = st.slider("24h Deluge Threshold (mm)", 40.0, 150.0, 80.0, 5.0)
        k_down_in = st.slider("Hysteresis Sustained Drop (k_down steps)", 1, 4, 2)
        use_hyst_in = st.checkbox("Enable Hysteresis", True)
        use_fatigue_in = st.checkbox("Enable Cry-Wolf Anti-Fatigue", True)
        imd_lag_days = st.slider("IMD Reporting Arrival Lag (Days)", 0, 3, 1, help="Modeled reporting lag for IMD gridded arrival. Default T+1 day.")

    # Guided Demo Tour Controller
    st.markdown("---")
    st.subheader("🎓 Guided Demo Tour")
    demo_steps = [
        "1. Executive Overview & Status",
        "2. In-District Map & Cell Partitioning",
        "3. Multi-Timescale Evidence & Source Agreement",
        "4. Bayesian Hypothesis Engine",
        "5. Decision Ladder & Hysteresis",
        "6. Human Confirm for ESCALATE",
        "7. Hash-Chained Why-Ledger Verification",
        "8. Historical Replay: Lavasa 2016 vs Quiet 2023"
    ]
    st.progress((st.session_state.demo_step + 1) / len(demo_steps))
    st.caption(f"Current: **{demo_steps[st.session_state.demo_step]}**")
    col_dprev, col_dnext = st.columns(2)
    if col_dprev.button("◀ Previous", use_container_width=True) and st.session_state.demo_step > 0:
        st.session_state.demo_step -= 1
        st.rerun()
    if col_dnext.button("Next ▶", use_container_width=True) and st.session_state.demo_step < len(demo_steps) - 1:
        st.session_state.demo_step += 1
        st.rerun()

# Instantiate Policy with active configuration
active_thresholds = ActionThresholds(
    p_prepare=p_prep_in,
    p_alert=p_alert_in,
    p_escalate=p_esc_in,
    rain_3d_alert_mm=r3d_thresh,
    rain_24h_alert_mm=r24h_thresh
)
current_policy = Policy(
    thresholds=active_thresholds,
    hysteresis=use_hyst_in,
    fatigue=use_fatigue_in,
    k_down=k_down_in
)


# -----------------------------------------------------------------------------
# Top Status Bar
# -----------------------------------------------------------------------------
if app_mode == "Historical Replay (Pune Real Data)":
    status_badge_text = "PROVIDED-DATA (OFFLINE REPLAY)"
    status_badge_class = "tag-provided"
    current_ist = f"{active_date} 08:30:00 IST"
elif app_mode == "Live Forecast (Open-Meteo)":
    status_badge_text = "LIVE (OPEN-METEO API)"
    status_badge_class = "tag-live"
    current_ist = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%Y-%m-%d %H:%M:%S IST")
else:
    status_badge_text = "SIMULATED LAB"
    status_badge_class = "tag-assumption"
    current_ist = f"Sim T={sim_t_now} min"

# Evaluate active evidence and decision
if app_mode != "Synthetic Lab (10-Min Twin Pair)":
    day_summary = evidence_builder.evaluate_district_summary(active_date)
    cell_evidence = evidence_builder.evaluate_cell_evidence(
        active_date, selected_cell, thresh_3d=r3d_thresh, thresh_24h=r24h_thresh
    )

    # Compute P(CASCADE) from multi-timescale evidence & source agreement
    max_3d = day_summary["district_max_3d_mm"]
    max_1d = day_summary["district_max_1d_mm"]
    ls_idx = day_summary["max_landslide_trigger_index"]
    agr = day_summary["source_agreement"]

    p_cas_raw = 0.05 + 0.45 * (max_3d / 200.0) + 0.35 * (max_1d / 120.0) + 0.15 * ls_idx
    p_cascade = float(np.clip(p_cas_raw * (1.0 - agr.get("confidence_penalty", 0.0)), 0.02, 0.98))

    decision_res = current_policy.step_decision(
        p_cas=p_cascade,
        lead=24.0,
        rain_3d=max_3d,
        rain_24h=max_1d,
        susceptibility=cell_evidence.get("susceptibility_prior", 0.50),
        pct_rank=cell_evidence.get("percentile_rank", 50.0)
    )
    current_action = decision_res["action_name"]
    is_confirmed = st.session_state.human_confirmations.get(active_date, False)
else:
    current_action = "WATCH"
    p_cascade = 0.15
    is_confirmed = False

action_class = f"action-{current_action.lower()}"

st.markdown(f"""
<div class="status-bar">
    <div>
        <span style="font-size:1.15rem; font-weight:800; color:#f8fafc;">📍 Pune District, Maharashtra</span>
        <span class="badge-tag {status_badge_class}">{status_badge_text}</span>
        <span class="badge-tag tag-assumption">IMD Lag: T+{imd_lag_days}d</span>
    </div>
    <div>
        <span style="color:#94a3b8; font-size:0.85rem; margin-right:8px;">RECOMMENDED ACTION:</span>
        <span class="action-chip {action_class}">{current_action}</span>
        {"<span class='badge-tag tag-live'>✔ CONFIRMED BY OPERATOR</span>" if is_confirmed else ""}
    </div>
    <div style="color:#94a3b8; font-size:0.82rem;">
        Clock (IST): <strong style="color:#f8fafc;">{current_ist}</strong>
    </div>
</div>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Main Navigation Tabs (7 Required Real-Data Tabs)
# -----------------------------------------------------------------------------
if app_mode != "Synthetic Lab (10-Min Twin Pair)":
    tab_overview, tab_map, tab_evidence, tab_policy, tab_ledger, tab_replay, tab_about = st.tabs([
        "1. Overview",
        "2. Map",
        "3. Evidence",
        "4. Decision & Policy",
        "5. Why-Ledger",
        "6. Replay Lab",
        "7. About / Method"
    ])

    # =========================================================================
    # TAB 1: OVERVIEW
    # =========================================================================
    with tab_overview:
        # Top KPI Cards
        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Recommended Action <span class="badge-tag tag-assumption">POLICY</span></div>
                <div class="metric-num" style="color:{ACTION_COLORS[current_action]}">{current_action}</div>
                <div style="font-size:0.75rem; color:#94a3b8;">{"Human confirm required" if current_action == "ESCALATE" and not is_confirmed else "Automated advisory"}</div>
            </div>
            """, unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">P(CASCADE) <span class="badge-tag tag-provided">INFERENCE</span></div>
                <div class="metric-num">{p_cascade:.1%}</div>
                <div style="font-size:0.75rem; color:#94a3b8;">Catchment saturation driver</div>
            </div>
            """, unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">District 3-Day Rain <span class="badge-tag tag-provided">IMD</span></div>
                <div class="metric-num">{day_summary['district_max_3d_mm']:.1f} <span style="font-size:1rem;">mm</span></div>
                <div style="font-size:0.75rem; color:#94a3b8;">Max cell: {day_summary['district_max_cell']}</div>
            </div>
            """, unsafe_allow_html=True)
        with k4:
            ls_val = day_summary['max_landslide_trigger_index']
            ls_tag = "CRITICAL" if ls_val >= 0.7 else ("ELEVATED" if ls_val >= 0.45 else "LOW")
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Landslide Risk Level <span class="badge-tag tag-assumption">GSI/CAINE</span></div>
                <div class="metric-num" style="color:{ACTION_COLORS['ESCALATE'] if ls_val>=0.7 else ACTION_COLORS['ALERT']}">{ls_tag} ({ls_val:.2f})</div>
                <div style="font-size:0.75rem; color:#94a3b8;">Western Ghats empirical</div>
            </div>
            """, unsafe_allow_html=True)
        with k5:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">In-District Coverage <span class="badge-tag tag-provided">DATA</span></div>
                <div class="metric-num">24 / 24 <span style="font-size:1rem;">cells</span></div>
                <div style="font-size:0.75rem; color:#94a3b8;">16 border/Konkan excluded</div>
            </div>
            """, unsafe_allow_html=True)

        # Plain Reason Banner
        st.info(f"**Operational Rationale:** {decision_res['plain_reason']}")
        st.caption(f"**What would change this recommendation:** {decision_res['reverses_if']}")

        # ESCALATE Human Confirmation Action Bar
        if current_action == "ESCALATE":
            if not is_confirmed:
                st.warning("⚠️ **CRITICAL ACTION REQUIRED:** The engine recommends **ESCALATE**. In accordance with disaster SOP, public alerting, siren activation, and mass evacuation REQUIRE explicit human officer confirmation.")
                c_conf1, c_conf2 = st.columns([1, 3])
                with c_conf1:
                    if st.button("🚨 CONFIRM ESCALATE & LOG DISPATCH", type="primary", use_container_width=True):
                        st.session_state.human_confirmations[active_date] = True
                        st.session_state.why_ledger.add_human_confirmation(
                            t=active_date,
                            action="ESCALATE",
                            operator_name="District Disaster Management Officer (Pune)",
                            notes="Authorized public alert following field verification of catchment saturation."
                        )
                        st.success("✔ ESCALATE recommendation confirmed and logged to hash chain.")
                        st.rerun()
            else:
                st.success(f"✔ **ESCALATE CONFIRMED BY OPERATOR:** Authorized for {active_date}. Recorded in immutable ledger block.")

        st.markdown("---")

        # Visual Timeline & Cell Ranking
        col_plot, col_rank = st.columns([1.6, 1])

        with col_plot:
            st.subheader("Catchment Deluge & Saturation Timeline")
            # Build time-series data for replay window
            if app_mode == "Historical Replay (Pune Real Data)":
                rep_data = replay_engine.run_replay(event_key)
                dates_ts = rep_data["dates"]
                r1d_ts = [s["district_max_1d_mm"] for s in rep_data["timeline"]]
                r3d_ts = [s["district_max_3d_mm"] for s in rep_data["timeline"]]
                pcas_ts = [s["p_cascade"] for s in rep_data["timeline"]]
            else:
                dates_ts = [active_date]
                r1d_ts = [day_summary["district_max_1d_mm"]]
                r3d_ts = [day_summary["district_max_3d_mm"]]
                pcas_ts = [p_cascade]

            fig_ts = create_rainfall_timeline_figure(
                dates=dates_ts,
                rain_1d=r1d_ts,
                rain_3d=r3d_ts,
                p_cascade=pcas_ts,
                current_date=active_date,
                thresh_3d=r3d_thresh
            )
            st.plotly_chart(fig_ts, use_container_width=True)

        with col_rank:
            st.subheader("In-District Cell Threat Ranking")
            df_cells = pd.DataFrame(day_summary["cells"])
            df_rank = df_cells[[
                "cell_id", "taluka_label", "rain_1d_mm", "rain_3d_mm", "percentile_rank", "landslide_trigger_index"
            ]].copy()
            df_rank.sort_values("rain_3d_mm", ascending=False, inplace=True)
            df_rank.rename(columns={
                "cell_id": "Cell ID",
                "taluka_label": "Taluka Proxy",
                "rain_1d_mm": "24h Rain (mm)",
                "rain_3d_mm": "3-Day Rain (mm)",
                "percentile_rank": "Historical %",
                "landslide_trigger_index": "Landslide Risk"
            }, inplace=True)
            st.dataframe(df_rank, hide_index=True, use_container_width=True, height=330)

    # =========================================================================
    # TAB 2: MAP
    # =========================================================================
    with tab_map:
        st.subheader("Pune District 40-Cell Hydro-Meteorological Grid Map")
        st.caption(
            "Spatial unit is the IMD 0.25° grid cell. "
            "Western cells (lon <= 73.25°) lie in the Konkan lowlands (Raigad/Thane); southern cells (lat = 18.00°) lie in Satara/Solapur. "
            "All 16 excluded cells are shown with hollow squares and explicit physical justification."
        )

        fig_map = create_grid_map_figure(day_summary["cells"], selected_cell_id=selected_cell)
        st.plotly_chart(fig_map, use_container_width=True)

        # Selected Cell Telemetry Drilldown
        c_m1, c_m2, c_m3, c_m4 = st.columns(4)
        c_m1.metric("Selected Cell", cell_evidence.get("cell_id", selected_cell))
        c_m2.metric("Taluka Proxy", cell_evidence.get("taluka_label", "N/A"))
        c_m3.metric("Susceptibility Prior", f"{cell_evidence.get('susceptibility_prior', 0.5):.2f}")
        c_m4.metric("Dist to Confirmed GLC", f"{cell_evidence.get('glc_dist_km', 999.0):.1f} km")

        with st.expander("📋 Review Excluded Cells (Border / Non-District Table)"):
            excluded_cells_list = imd_loader.excluded_cells
            ex_data = []
            for cid in excluded_cells_list:
                m = imd_loader.cell_metadata[cid]
                ex_data.append({
                    "Cell ID": cid,
                    "Latitude": m.lat,
                    "Longitude": m.lon,
                    "Physical Exclusion Reason": m.exclusion_reason
                })
            st.table(pd.DataFrame(ex_data))

    # =========================================================================
    # TAB 3: EVIDENCE
    # =========================================================================
    with tab_evidence:
        st.subheader("Evidence Timeline, Arrival Lag & Source Agreement")

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.markdown("#### Modeled Reporting Arrival Lag")
            st.write(
                f"- **IMD Gridded Data Arrival:** Event date `{active_date}` is typically derived from morning synoptic observations "
                f"and available at **T+{imd_lag_days} day** (default assumption, user-editable in sidebar)."
            )
            st.write(
                "- **Open-Meteo Reanalysis/Forecast Lag:** Hourly reanalysis published with a ~2 hour lag; "
                "live forecast is zero-lag forward looking."
            )
            st.write(
                "- **Lag Handling Policy:** In operational decisions, when IMD observations are not yet received, "
                "the engine falls back to Open-Meteo gridded forecast without halting, applying a confidence discount."
            )

        with col_e2:
            st.markdown("#### Source Agreement at Pune Cell (`CELL_18.50_73.75`)")
            fig_agr = create_source_agreement_figure(agr)
            st.plotly_chart(fig_agr, use_container_width=True)
            st.caption(f"Note: {agr.get('note', '')}")

        # Pune Point Hourly Detail
        st.markdown("---")
        st.subheader("Open-Meteo Pune Point Hourly Evidence (18.52N, 73.87E, 561 m)")
        st.caption("Label: gridded estimate (Open-Meteo). Pune point only. Hourly intensity and soil moisture.")
        
        om_win = om_loader.get_window(active_date, active_date)
        if len(om_win) and om_win["quality_flag"].iloc[0] != "MISSING":
            col_om1, col_om2 = st.columns(2)
            with col_om1:
                fig_hourly_rain = px.line(
                    om_win, x="time_ist", y=["rain_acc_1h", "rain_acc_3h"],
                    title="Hourly Accumulation Rates (mm/h) [PROVIDED-DATA]",
                    labels={"value": "Rain (mm)", "time_ist": "Time IST"}
                )
                fig_hourly_rain.update_layout(template="plotly_dark", height=260)
                st.plotly_chart(fig_hourly_rain, use_container_width=True)
            with col_om2:
                fig_soil = px.line(
                    om_win, x="time_ist", y="soil_moisture_m3m3",
                    title="Topsoil Moisture (0-7cm m³/m³) [PROVIDED-DATA]",
                    labels={"soil_moisture_m3m3": "Soil Moisture", "time_ist": "Time IST"}
                )
                fig_soil.update_layout(template="plotly_dark", height=260)
                st.plotly_chart(fig_soil, use_container_width=True)
        else:
            st.warning("Hourly Open-Meteo data for this date is MISSING (Jan-May 2015). Preserved as NaN, never filled with zero.")

    # =========================================================================
    # TAB 4: DECISION & POLICY
    # =========================================================================
    with tab_policy:
        st.subheader("Cost-Aware Decision Policy & Ladder")

        col_p1, col_p2 = st.columns([1.2, 1])
        with col_p1:
            st.markdown("""
            #### Unified 4-Stage Action Ladder
            1. **WATCH (Green):** Normal catchment baseline. Routine monitoring.
            2. **PREPARE (Yellow):** Elevated catchment soil saturation or high 3-day rainfall. Stage field rescue assets, clear urban stormwater chokepoints.
            3. **ALERT (Orange):** Imminent heavy deluge or landslide threshold exceeded. Activate emergency operations centers, sound dam release warnings.
            4. **ESCALATE (Red):** Catastrophic catchment deluge threatening human lives. Public siren dispatch and evacuation. **RECOMMENDATION ONLY — requires Human Officer confirmation.**
            """)

            st.markdown("#### Numeric Policy Thresholds (Editable)")
            th_df = pd.DataFrame([
                {"Action": "PREPARE", "Min P(CASCADE)": active_thresholds.p_prepare, "3-Day Rain (mm)": active_thresholds.rain_3d_prepare_mm, "Operational Trigger": "Catchment saturation"},
                {"Action": "ALERT", "Min P(CASCADE)": active_thresholds.p_alert, "3-Day Rain (mm)": active_thresholds.rain_3d_alert_mm, "Operational Trigger": "Deluge threshold or high prior"},
                {"Action": "ESCALATE", "Min P(CASCADE)": active_thresholds.p_escalate, "3-Day Rain (mm)": active_thresholds.rain_3d_escalate_mm, "Operational Trigger": "Severe hazard; human confirm required"}
            ])
            st.table(th_df)

        with col_p2:
            st.markdown("#### CostModel Parameters (Unvalidated Assumption)")
            st.markdown(f"""
            - **Damage unmitigated (D):** `{current_policy.cost.D:.1f}`
            - **Damage mitigation (ρ):** `{current_policy.cost.rho}`
            - **False-alarm cost (c_fa):** `{current_policy.cost.c_fa}`
            - **Fatigue multiplier (γ):** `{current_policy.cost.gamma:.1f}`
            - **Lead benefit rate (κ):** `{current_policy.cost.kappa:.2f}`
            - **Switch penalty:** `{current_policy.cost.switch:.1f}`
            """)

            st.markdown("#### Anti-Flapping Hysteresis & Fatigue State")
            st.write(f"- **Hysteresis Enabled:** `{current_policy.hysteresis}` (k_down = `{current_policy.k_down}` steps)")
            st.write(f"- **Cry-Wolf Fatigue Enabled:** `{current_policy.use_fatigue}` (f = `{current_policy.f:.2f}`)")

        st.markdown("---")
        st.subheader("Scripted Scenario Validation Suite")
        st.caption("Verifies expected vs actual policy action across 6 critical operational edge cases.")
        df_scripted = run_scripted_scenarios(current_policy)
        st.dataframe(df_scripted, hide_index=True, use_container_width=True)

    # =========================================================================
    # TAB 5: WHY-LEDGER
    # =========================================================================
    with tab_ledger:
        st.subheader("SHA-256 Hash-Chained Why-Ledger")

        # Verify ledger chain
        chain_ok = st.session_state.why_ledger.verify()
        if chain_ok:
            st.success("✔ **CRYPTOGRAPHIC INTEGRITY VERIFIED:** All SHA-256 hashes chain back to genesis root.")
        else:
            st.error("❌ **LEDGER INTEGRITY COMPROMISED:** Hash mismatch detected in chain!")

        entries = st.session_state.why_ledger.entries

        col_l1, col_l2 = st.columns([2, 1])
        with col_l1:
            st.write(f"Total Audit Entries Logged: **{len(entries)}**")
        with col_l2:
            st.download_button(
                "⬇ Download Ledger (JSON)",
                st.session_state.why_ledger.to_json(),
                "pune_why_ledger.json",
                use_container_width=True
            )

        # Show entries in reverse chronological order
        for e in reversed(entries):
            action_tag = f"{e['action_from']} ➔ {e['action_to']}"
            conf_str = " | 🛡️ CONFIRMED BY OPERATOR" if e.get("confirmed_by_human") else ""
            with st.expander(f"Step {e.get('t', 0)} ({e.get('timestamp_ist', '')}): {action_tag}{conf_str}"):
                c_e1, c_e2 = st.columns(2)
                with c_e1:
                    st.write(f"**Rule Fired:** `{e.get('rule_fired', 'N/A')}`")
                    st.write(f"**P(CASCADE):** {e.get('p_before', [0,0,0,0])[3]:.2f} ➔ {e.get('p_after', [0,0,0,0])[3]:.2f}")
                    st.write("**Triggering Factors:**")
                    for k, v in e.get("because", []):
                        st.write(f"- `{k}`: {v:+.2f}")
                with c_e2:
                    st.write(f"**Reverses If:** {e.get('reverses_if', 'N/A')}")
                    st.write(f"**Notes:** {', '.join(e.get('notes', [])) or 'None'}")
                    st.code(
                        f"Prev Hash: {e.get('prev_hash', '')[:16]}...\n"
                        f"This Hash: {e.get('hash', '')[:16]}...\n"
                        f"Input Hash: {e.get('input_hash', '')}"
                    )

    # =========================================================================
    # TAB 6: REPLAY LAB
    # =========================================================================
    with tab_replay:
        st.subheader("Historical Event Replay & Landslide Threshold Sensitivity")

        col_r1, col_r2 = st.columns([1.5, 1])
        with col_r1:
            st.markdown(f"#### Active Replay Event: **{selected_meta.title}**")
            st.write(f"- **Hazard:** {selected_meta.hazard_type}")
            st.write(f"- **Peak Date:** `{selected_meta.peak_date}`")
            st.write(f"- **Replay Window:** `{selected_meta.start_date}` to `{selected_meta.end_date}`")
            st.write(f"- **Context:** {selected_meta.description}")
            if selected_meta.confirmed_glc_match:
                st.info(f"📍 **Ground Truth Validation:** {selected_meta.confirmed_glc_match}")

        with col_r2:
            st.markdown("#### Landslide Empirical Threshold Sensitivity Check")
            st.caption("Hit vs False Alarm rates across replay events at ±20% threshold levels.")
            df_sens = evidence_builder.calculate_threshold_sensitivity()
            st.dataframe(df_sens, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.subheader("Historical Replay Candidate Registry")
        st.table(pd.DataFrame([
            {"Key": k, "Event": m.title, "Peak Date": m.peak_date, "Hazard": m.hazard_type, "Expected Action": m.expected_peak_action}
            for k, m in HISTORICAL_EVENTS.items()
        ]))

    # =========================================================================
    # TAB 7: ABOUT / METHOD
    # =========================================================================
    with tab_about:
        st.subheader("Data Sources, Quality Audit & Methodological Disclaimers")

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            st.markdown("""
            #### Data Quality & Ingestion Audit
            - **IMD Gridded Daily Rainfall:** 40 grid cells at 0.25° resolution (2015-01-28 to 2025-12-31). 159,640 records, zero missing, zero nulls. 16 extreme values (>300 mm/day) flagged as *"extreme, plausible Western Ghats, verify"*; strictly preserved without deletion or clipping.
            - **Open-Meteo Pune Point:** Hourly reanalysis at (18.523726N, 73.86876E, 561 m ASL). UTC converted to IST (+05:30). Jan-May 2015 is missing and preserved as explicit `NaN`, never zero-filled.
            - **NASA Global Landslide Catalog (GLC):** 31 regional candidates filtered. 3 confirmed in Pune district (Malin 2014, Karla 2015, Lavasa 2016); 9 ambiguous crest border events; 19 non-district events excluded.
            """)

        with col_a2:
            st.markdown("""
            #### Malin Landslide (2014-07-30) Historical Context
            - **Date:** 2014-07-30 09:00 IST
            - **Location:** Malin village, Ambegaon taluka, Pune District (19.1620N, 73.6873E)
            - **Impact:** 151 fatalities, catastrophic slope failure after 108 mm downpour.
            - **Data Handling:** Predates the 2015-2025 rainfall data files. Displayed strictly as historical context and weak spatial prior; never replayed or trained on.
            """)

        st.markdown("---")
        st.markdown("""
        #### Legal & Operational Disclaimers
        > [!IMPORTANT]
        > **Decision Support Only:** This dashboard is an engineering decision-support tool designed for district emergency planners. It does not replace statutory authority. Public emergency alerts (ESCALATE) require explicit human confirmation by authorized disaster management officials.
        
        > [!NOTE]
        > **Susceptibility Prior:** Derived from rank-normalized monsoon climatology and proximity to confirmed GLC points. Labeled *ASSUMPTION: rainfall-climatology proxy, not a geological susceptibility map*.
        """)

# -----------------------------------------------------------------------------
# LEGACY / LAB MODE: 10-Minute Synthetic Twin Pair Simulator
# -----------------------------------------------------------------------------
else:
    st.subheader("Synthetic Crisis Simulator (Lab Mode)")
    st.caption("Twin pair stress testing: identical first 7 minutes, diverging thereafter.")

    rng = np.random.default_rng(sim_seed)
    pair = ("NOISE", "CASCADE" if sim_truth in ("random", "NOISE") else sim_truth)
    twins = generate_twin(rng, fam="A", pair=pair, stress=tuple(sim_stress), split=7.0, T=16)
    
    a_rec = run_episode(twins[0], Engine(), {"SENTINEL": Policy()}, T_run=14, seed=sim_seed)
    b_rec = run_episode(twins[1], Engine(), {"SENTINEL": Policy()}, T_run=14, seed=sim_seed)

    fig_sim = go.Figure()
    fig_sim.add_scatter(x=[r["t"] for r in a_rec], y=[r["p"][H_CAS] for r in a_rec], name="Twin A (NOISE) P(CASCADE)", line=dict(color="#94a3b8", dash="dot"))
    fig_sim.add_scatter(x=[r["t"] for r in b_rec], y=[r["p"][H_CAS] for r in b_rec], name=f"Twin B ({pair[1]}) P(CASCADE)", line=dict(color="#ef4444", width=3))
    fig_sim.add_vline(x=7.0, line_dash="dot", line_color="#f59e0b", annotation_text="split (T=7)")
    fig_sim.add_vline(x=sim_t_now, line_dash="solid", line_color="#38bdf8", annotation_text=f"min {sim_t_now}")
    fig_sim.update_layout(template="plotly_dark", height=320, xaxis=dict(title="Minute (T)"), yaxis=dict(title="P(CASCADE)"))
    st.plotly_chart(fig_sim, use_container_width=True)
