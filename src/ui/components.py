"""Reusable Plotly visualizations and UI components for Cascade Sentinel."""
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.policy.policy import ACTION_COLORS

# Theme Palette matching Crisis Operations Center
BG_DARK = "#0b0f19"
PANEL_DARK = "#111827"
BORDER_DARK = "#1f2937"
TEXT_MUTED = "#94a3b8"
TEXT_BRIGHT = "#f8fafc"
ACCENT_CYAN = "#38bdf8"


def create_rainfall_timeline_figure(
    dates: List[str],
    rain_1d: List[float],
    rain_3d: List[float],
    p_cascade: List[float],
    current_date: str,
    thresh_3d: float = 150.0,
    forecast_df: Optional[pd.DataFrame] = None
) -> go.Figure:
    """Create interactive dual-axis rainfall and P(CASCADE) time-series."""
    fig = go.Figure()

    # 1-day daily rain bars
    fig.add_trace(go.Bar(
        x=dates,
        y=rain_1d,
        name="24h District Max (mm)",
        marker_color="rgba(56, 189, 248, 0.45)",
        marker_line=dict(color="#38bdf8", width=1.5),
        yaxis="y1"
    ))

    # 3-day accumulation line
    fig.add_trace(go.Scatter(
        x=dates,
        y=rain_3d,
        name="3-Day Accumulation (mm)",
        line=dict(color="#818cf8", width=2.5),
        mode="lines+markers",
        yaxis="y1"
    ))

    # P(CASCADE) posterior on secondary axis
    fig.add_trace(go.Scatter(
        x=dates,
        y=p_cascade,
        name="P(CASCADE) Posterior",
        line=dict(color="#ef4444", width=3, dash="solid"),
        mode="lines+markers",
        yaxis="y2"
    ))

    # Threshold horizontal line
    fig.add_hline(
        y=thresh_3d,
        line_dash="dot",
        line_color="#f59e0b",
        annotation_text=f"Catchment Saturation Threshold ({thresh_3d:.0f} mm)",
        annotation_position="top left",
        yref="y1"
    )

    # Current time step vertical indicator
    if current_date in dates:
        fig.add_vline(
            x=current_date,
            line_dash="solid",
            line_color="#38bdf8",
            line_width=2.5,
            annotation_text=f"Selected: {current_date}",
            annotation_position="bottom right"
        )

    # If forecast data is provided, append forecast envelope
    if forecast_df is not None and len(forecast_df):
        fc_daily = forecast_df.groupby("date_ist")["rain_mm_h"].sum().reset_index()
        fig.add_trace(go.Bar(
            x=fc_daily["date_ist"].tolist(),
            y=fc_daily["rain_mm_h"].tolist(),
            name="Forecast Rain (72h) [FORECAST]",
            marker_color="rgba(245, 158, 11, 0.35)",
            marker_line=dict(color="#f59e0b", width=1.5, dash="dash"),
            yaxis="y1"
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,0.6)",
        height=360,
        margin=dict(l=40, r=40, t=20, b=30),
        xaxis=dict(title="Date (IST)", gridcolor="#1e293b"),
        yaxis=dict(
            title="Rainfall (mm)",
            gridcolor="#1e293b",
            zeroline=False
        ),
        yaxis2=dict(
            title="P(CASCADE)",
            overlaying="y",
            side="right",
            range=[-0.02, 1.05],
            tickformat=".0%",
            showgrid=False
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0.0
        ),
        hovermode="x unified"
    )
    return fig


def create_grid_map_figure(
    cells: List[Dict[str, Any]],
    selected_cell_id: str,
    action_ladder_policy: Any = None
) -> go.Figure:
    """Render 40 IMD grid cells colored by risk (in-district) vs excluded cells."""
    df_cells = pd.DataFrame(cells)

    fig = go.Figure()

    # Split into In-District vs Excluded
    in_dist = df_cells[df_cells["in_district"] == True].copy()
    excluded = df_cells[df_cells["in_district"] == False].copy()

    # 1. Excluded cells (Konkan / Satara)
    if len(excluded):
        fig.add_trace(go.Scatter(
            x=excluded["lon"],
            y=excluded["lat"],
            mode="markers+text",
            name="Excluded Cells (Konkan / Satara)",
            marker=dict(
                size=24,
                symbol="square-open",
                color="#64748b",
                line=dict(color="#475569", width=2)
            ),
            text=excluded["cell_id"].apply(lambda s: s.replace("CELL_", "")),
            textposition="top center",
            textfont=dict(size=9, color="#94a3b8"),
            customdata=excluded[["exclusion_reason", "rain_1d_mm"]],
            hovertemplate=(
                "<b>%{text} (EXCLUDED)</b><br>"
                "Reason: %{customdata[0]}<br>"
                "Rainfall: %{customdata[1]:.1f} mm/day<br>"
                "<extra></extra>"
            )
        ))

    # 2. In-district cells colored by risk
    if len(in_dist):
        # Color mapped by action level or landslide trigger index
        colors = []
        for _, r in in_dist.iterrows():
            ls = r.get("landslide_trigger_index", 0.0)
            r1d = r.get("rain_1d_mm", 0.0)
            if ls >= 0.70 or r1d >= 100.0:
                colors.append(ACTION_COLORS["ESCALATE"])
            elif ls >= 0.45 or r1d >= 60.0:
                colors.append(ACTION_COLORS["ALERT"])
            elif ls >= 0.25 or r1d >= 30.0:
                colors.append(ACTION_COLORS["PREPARE"])
            else:
                colors.append(ACTION_COLORS["WATCH"])

        fig.add_trace(go.Scatter(
            x=in_dist["lon"],
            y=in_dist["lat"],
            mode="markers+text",
            name="In-District Cells (Pune)",
            marker=dict(
                size=32,
                symbol="square",
                color=colors,
                line=dict(color="#f8fafc", width=1.5),
                opacity=0.90
            ),
            text=in_dist["cell_id"].apply(lambda s: s.replace("CELL_", "")),
            textposition="middle center",
            textfont=dict(size=9, color="#0b0f19"),
            customdata=in_dist[["taluka_label", "rain_1d_mm", "rain_3d_mm", "susceptibility_prior", "landslide_trigger_index"]],
            hovertemplate=(
                "<b>%{text} (Pune In-District)</b><br>"
                "Taluka Proxy: %{customdata[0]}<br>"
                "24h Rain: %{customdata[1]:.1f} mm<br>"
                "3-Day Rain: %{customdata[2]:.1f} mm<br>"
                "Susceptibility Prior: %{customdata[3]:.2f}<br>"
                "Landslide Trigger Index: %{customdata[4]:.2f}<br>"
                "<extra></extra>"
            )
        ))

    # 3. Selected cell highlight halo
    sel_row = df_cells[df_cells["cell_id"] == selected_cell_id]
    if len(sel_row):
        fig.add_trace(go.Scatter(
            x=[sel_row.iloc[0]["lon"]],
            y=[sel_row.iloc[0]["lat"]],
            mode="markers",
            name=f"Selected: {selected_cell_id}",
            marker=dict(
                size=46,
                symbol="circle-open",
                color="#38bdf8",
                line=dict(color="#38bdf8", width=3.5)
            ),
            hoverinfo="skip"
        ))

    # Add reference labels (Ghats crestline vs Rainshadow)
    fig.add_vline(x=73.40, line_dash="dash", line_color="#f59e0b",
                  annotation_text="Western Ghats Crestline Divide", annotation_position="top left")

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,0.7)",
        height=440,
        margin=dict(l=30, r=30, t=30, b=30),
        xaxis=dict(
            title="Longitude (°E)",
            range=[72.85, 74.90],
            dtick=0.25,
            gridcolor="#1e293b"
        ),
        yaxis=dict(
            title="Latitude (°N)",
            range=[17.85, 19.15],
            dtick=0.25,
            gridcolor="#1e293b"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        )
    )
    return fig


def create_source_agreement_figure(agr_info: Dict[str, Any]) -> go.Figure:
    """Create source agreement comparison bar chart between IMD and Open-Meteo at Pune cell."""
    imd_val = agr_info.get("imd_rain_mm") or 0.0
    om_val = agr_info.get("om_rain_mm") or 0.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["IMD gridded (observed-derived)", "gridded estimate (Open-Meteo)"],
        y=[imd_val, om_val],
        marker_color=["#38bdf8", "#818cf8"],
        text=[f"{imd_val:.1f} mm", f"{om_val:.1f} mm"],
        textposition="auto"
    ))

    status = agr_info.get("status", "UNKNOWN")
    status_color = "#10b981" if status == "STRONG_AGREEMENT" else ("#f59e0b" if "MODERATE" in status else "#ef4444")

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,0.5)",
        height=240,
        margin=dict(l=20, r=20, t=30, b=20),
        title=dict(
            text=f"Pune Cell Comparison: <span style='color:{status_color}'>{status}</span> (Δ {agr_info.get('abs_delta_mm', 0):.1f} mm)",
            font=dict(size=13, color="#f8fafc")
        ),
        yaxis=dict(title="Rainfall (mm/day)", gridcolor="#1e293b")
    )
    return fig
