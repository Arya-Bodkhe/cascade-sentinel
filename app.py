
"""CASCADE SENTINEL - Streamlit decision-support UI (five panels).
Run: streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.common.model import HYPS, KINDS
from src.belief.engine import Engine
from src.ledger.ledger import Ledger
from src.policy.policy import Policy, ACTIONS
from src.runtime import run_episode
from src.sim.world import (
    generate_episode,
    generate_twin,
    STRESSORS,
)

# ------------------------------------------------------------------
# Page configuration
# ------------------------------------------------------------------

st.set_page_config(
    page_title="CASCADE SENTINEL",
    layout="wide",
)

st.title("CASCADE SENTINEL - the first 10 minutes")

st.caption(
    "Research prototype for analyst decision support. "
    "Not an official warning system. "
    "All data on this screen is SIMULATED. "
    "Public alerts (ESCALATE) always need human confirmation."
)

# ------------------------------------------------------------------
# Panel 5: Replay lab
# ------------------------------------------------------------------

with st.sidebar:
    st.header("5 - Replay lab")

    mode = st.radio(
        "Mode",
        [
            "Single episode",
            "Twin pair (NOISE vs CASCADE)",
        ],
    )

    seed = st.number_input(
        "Seed",
        min_value=0,
        max_value=10_000,
        value=41,
    )

    fam = st.selectbox(
        "Scenario family",
        ["A", "B", "C"],
    )

    truth = st.selectbox(
        "Hidden truth (for replay)",
        ["random"] + HYPS,
    )

    stress = st.multiselect(
        "Stressors",
        STRESSORS,
    )

    t_now = st.slider(
        "Wall-clock minute",
        min_value=1,
        max_value=14,
        value=9,
    )


# ------------------------------------------------------------------
# Replay function
# ------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def replay(
    seed,
    fam,
    truth,
    stress,
    which=0,
    twin=False,
):
    rng = np.random.default_rng(seed)

    if twin:
        # Current simulator interface:
        # generate_twin(rng, fam=fam)
        #
        # IMPORTANT:
        # This call does not apply the selected stressors.
        # Do not claim stress testing in Twin Pair mode
        # until the simulator supports it explicitly.

        ep = generate_twin(
            rng,
            fam=fam,
        )[which]

    else:
        # Single Episode mode supports stressors.
        ep = generate_episode(
            rng,
            fam=fam,
            hyp=None if truth == "random" else truth,
            stress=stress,
            T=16,
        )

    led = Ledger(seed)

    recs = run_episode(
        ep,
        Engine(),
        {"SENTINEL": Policy()},
        T_run=14,
        seed=seed,
        ledger=led,
    )

    return (
        ep,
        recs,
        led.entries,
        led.to_json(),
        led.to_csv(),
        led.verify(),
    )


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def rec_at(recs, t):
    return recs[t - 1]


# ------------------------------------------------------------------
# Single Episode Mode
# ------------------------------------------------------------------

if mode == "Single episode":

    ep, recs, entries, js, csv_, ok = replay(
        seed,
        fam,
        truth,
        tuple(stress),
    )

    r = rec_at(recs, t_now)

    c1, c2 = st.columns([1.2, 1])

    # --------------------------------------------------------------
    # Panel 1: Crisis picture
    # --------------------------------------------------------------

    with c1:

        st.subheader("1 - Crisis picture")

        lv = r["levels"]["SENTINEL"]

        action_label = ACTIONS[lv]

        if lv == 3:
            action_label += " (human confirmation required)"

        st.metric(
            "Recommended action",
            action_label,
        )

        probs = pd.DataFrame(
            {
                "hypothesis": HYPS,
                "probability": r["p"],
            }
        )

        fig_probs = px.bar(
            probs,
            x="hypothesis",
            y="probability",
            range_y=[0, 1],
            text_auto=".2f",
        )

        st.plotly_chart(
            fig_probs,
            use_container_width=True,
        )

        m1, m2, m3 = st.columns(3)

        m1.metric(
            "Source coverage",
            f"{r['coverage']:.0%}",
        )

        m2.metric(
            "Entropy (nats)",
            f"{r['entropy']:.2f}",
        )

        m3.metric(
            "Quarantined events",
            r["quarantined"],
        )

        st.caption(
            f"Hidden truth: **{ep['hyp_name']}** | "
            f"stressors: {', '.join(ep['stress']) or 'none'} | "
            "calibration badge: SIMULATED, "
            "low-sample hypotheses flagged in reports/RESULTS.md"
        )

    # --------------------------------------------------------------
    # Panel 3: Foresight
    # --------------------------------------------------------------

    with c2:

        st.subheader("3 - Foresight: next events")

        if r["forecast"]:

            forecast_df = pd.DataFrame(
                [
                    {
                        "event": f["kind"],
                        "P (10 min)": round(f["p"], 2),
                        "80% window (min)": (
                            f"{f['window'][0]:.1f} - "
                            f"{f['window'][1]:.1f}"
                        ),
                    }
                    for f in r["forecast"]
                ]
            )

            st.table(forecast_df)

        else:

            st.info(
                "No pending downstream events predicted "
                "at this minute."
            )

        # ----------------------------------------------------------
        # Probability over time
        # ----------------------------------------------------------

        st.subheader("Probability over time")

        fig = go.Figure()

        for i, h in enumerate(HYPS):

            fig.add_scatter(
                x=[x["t"] for x in recs],
                y=[x["p"][i] for x in recs],
                name=h,
            )

        fig.add_vline(
            x=t_now,
            line_dash="dot",
        )

        fig.update_yaxes(
            range=[0, 1],
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

    # --------------------------------------------------------------
    # Panel 2: Evidence timeline
    # --------------------------------------------------------------

    st.subheader(
        "2 - Evidence timeline "
        "(event time vs arrival time)"
    )

    df = pd.DataFrame(
        [
            {
                "kind": e["kind"],
                "event_time": e["event_time"],
                "received_at": e["received_at"],
            }
            for e in ep["events"]
            if (
                e["kind"] in KINDS + ["silence"]
                and e["received_at"] <= t_now
            )
        ]
    )

    if len(df):

        fig_timeline = px.scatter(
            df,
            x="event_time",
            y="received_at",
            color="kind",
        )

        st.plotly_chart(
            fig_timeline,
            use_container_width=True,
        )

    else:

        st.info(
            "No evidence events are available "
            "for the selected minute."
        )

    st.write(
        f"Gateways masked as down: **{r['n_down']}** "
        "(counted once, not per sensor) | "
        f"citizen reports: **{r['raw_citizen']}** raw "
        f"-> **{r['eff_citizen']:.1f}** effective "
        f"({r['n_origins']} origins)"
    )

    # --------------------------------------------------------------
    # Panel 4: Why-ledger
    # --------------------------------------------------------------

    st.subheader(
        "4 - Why-ledger (hash-chained)"
    )

    st.write(
        "Chain verifies: "
        + ("YES" if ok else "NO")
    )

    for e in entries:

        if e["t"] <= t_now:

            with st.expander(
                f"minute {e['t']}: "
                f"{e['action_from']} -> {e['action_to']} | "
                f"P(CASCADE) "
                f"{e['p_before'][3]:.2f} -> "
                f"{e['p_after'][3]:.2f}"
            ):

                st.write("**Because:**")

                for k, v in e["because"]:

                    st.write(
                        f"- {v:+.2f}  {k}"
                    )

                for n in e["notes"]:

                    st.write(
                        f"- note: {n}"
                    )

                st.write(
                    f"**Reverses if:** {e['reverses_if']}"
                )

                st.code(
                    f"model {e['model']} | "
                    f"seed {e['seed']} | "
                    f"input {e['input_hash']} | "
                    f"prev {e['prev_hash'][:8]} | "
                    f"hash {e['hash'][:8]}"
                )

    st.download_button(
        "Download ledger JSON",
        js,
        "ledger.json",
    )

    st.download_button(
        "Download ledger CSV",
        csv_,
        "ledger.csv",
    )


# ------------------------------------------------------------------
# Twin Pair Mode
# ------------------------------------------------------------------

else:

    st.subheader(
        "Twin test: identical first 7 minutes, "
        "then the futures split"
    )

    # --------------------------------------------------------------
    # Important simulator limitation
    # --------------------------------------------------------------

    if stress:

        st.warning(
            "Selected stressors are NOT applied in Twin Pair mode "
            "with the current generate_twin() integration. "
            "The twin episodes below use the simulator's "
            "existing default twin generation."
        )

    else:

        st.info(
            "Twin Pair mode is using the simulator's "
            "default twin generation."
        )

    # --------------------------------------------------------------
    # Generate twins
    # --------------------------------------------------------------

    a = replay(
        seed,
        fam,
        "NOISE",
        (),
        0,
        True,
    )

    b = replay(
        seed,
        fam,
        "CASCADE",
        (),
        1,
        True,
    )

    # --------------------------------------------------------------
    # Twin probability comparison
    # --------------------------------------------------------------

    fig = go.Figure()

    for name, x in (
        ("Twin A (NOISE)", a),
        ("Twin B (CASCADE)", b),
    ):

        fig.add_scatter(
            x=[r["t"] for r in x[1]],
            y=[r["p"][3] for r in x[1]],
            name=name + " P(CASCADE)",
        )

    fig.add_vline(
        x=7,
        line_dash="dot",
        annotation_text="split",
    )

    fig.update_yaxes(
        range=[0, 1],
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    # --------------------------------------------------------------
    # Twin actions and probabilities
    # --------------------------------------------------------------

    c1, c2 = st.columns(2)

    for col, name, x in (
        (c1, "Twin A (NOISE)", a),
        (c2, "Twin B (CASCADE)", b),
    ):

        r = rec_at(
            x[1],
            t_now,
        )

        col.metric(
            name + " action",
            ACTIONS[r["levels"]["SENTINEL"]],
        )

        col.write(
            {
                h: round(float(p), 3)
                for h, p in zip(HYPS, r["p"])
            }
        )


# ------------------------------------------------------------------
# Footer
# ------------------------------------------------------------------

st.divider()

st.caption(
    "Decision support only. "
    "Cost parameters are editable assumptions "
    "(src/policy/policy.py: CostModel), "
    "not validated numbers."
)

