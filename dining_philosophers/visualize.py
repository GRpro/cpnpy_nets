"""Streamlit view of the dining-philosophers net.

Run with: venv/bin/streamlit run dining_philosophers/visualize.py
"""

import traceback

import streamlit as st

from cpnpy.visualization.streamlit import CPNStreamlitVisualizer, format_simulation_error

from dining_philosophers import build_dining_philosophers


def main():
    st.set_page_config(layout="wide", page_title="Dining philosophers")
    st.title("Dining philosophers")
    st.caption(
        "Each philosopher takes both neighboring forks in one step. "
        "Fire take_i to eat, then put_i to return the forks."
    )

    if "cpn_built" not in st.session_state:
        try:
            cpn, marking, context = build_dining_philosophers()
        except Exception as exc:
            st.error(f"Failed to build the net — {format_simulation_error(exc)}")
            with st.expander("Error details", expanded=False):
                st.code(traceback.format_exc(), language="text")
            st.stop()
        st.session_state["dining_cpn"] = cpn
        st.session_state["dining_context"] = context
        st.session_state["dining_initial_marking"] = marking
        st.session_state["cpn_built"] = True

    viz = CPNStreamlitVisualizer(
        st.session_state["dining_cpn"],
        st.session_state["dining_initial_marking"],
        context=st.session_state["dining_context"],
        session_key="dining_runtime",
    )
    viz.render(height=800)


if __name__ == "__main__":
    main()
