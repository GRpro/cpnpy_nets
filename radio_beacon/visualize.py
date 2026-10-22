"""Streamlit view of the two-radio beacon net.

Run with: venv/bin/streamlit run radio_beacon/visualize.py
"""

import traceback

import streamlit as st

from cpnpy.simulation.simu import get_enabled_transitions
from cpnpy.visualization.streamlit import CPNStreamlitVisualizer, format_simulation_error

from net import build_radio_beacon


class _RadioVisualizer(CPNStreamlitVisualizer):
    """Refresh the sidebar after the clock jumps to the next timed token.

    The base visualizer decides which transitions are enabled, then moves the
    clock. A jump that makes StartRx or StartTx ready would otherwise leave the
    Fire button hidden until something else redraws the page.
    """

    def _coalesce_manual_time_advance(self, *, transitions_enabled=None):
        before = self.marking.global_clock
        super()._coalesce_manual_time_advance(transitions_enabled=transitions_enabled)
        if self.marking.global_clock == before:
            return
        if get_enabled_transitions(self.cpn, self.marking, self.context):
            self._request_rerun()


def main():
    st.set_page_config(layout="wide", page_title="Radio beacons")
    st.title("Radio beacons")
    st.caption(
        "Each radio is one token. It sleeps, transmits from Tx, and listens in Rx. "
        "Hear and Receive leave it there. EndTx and EndRx move it on. "
        "The first listen is 30 seconds, then a beacon every 30 seconds and data every 10. "
        "A radio stores the beacon offset only while it is in Rx and the other radio "
        "is sending that beacon. Data heard in that listen is recorded too. "
        "The counter stays 1 until both radios have heard each other. "
        "Message stores txNode, rxNode, and the counter that was sent. "
        "The next send after that carries the next counter. "
        "A radio token has no boot or text field. "
        "It stores the second it is due, and the arc delay waits until the next one. "
        "Radio A boots at 0 with offset 3, radio B at 50 with offset 7."
    )

    if "cpn_built" not in st.session_state:
        try:
            cpn, marking, context = build_radio_beacon()
        except Exception as exc:
            st.error(f"Failed to build the net — {format_simulation_error(exc)}")
            with st.expander("Error details", expanded=False):
                st.code(traceback.format_exc(), language="text")
            st.stop()
        st.session_state["radio_cpn"] = cpn
        st.session_state["radio_context"] = context
        st.session_state["radio_initial_marking"] = marking
        st.session_state["cpn_built"] = True

    viz = _RadioVisualizer(
        st.session_state["radio_cpn"],
        st.session_state["radio_initial_marking"],
        context=st.session_state["radio_context"],
        session_key="radio_runtime",
    )
    viz.render(height=800)


if __name__ == "__main__":
    main()
