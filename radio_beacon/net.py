"""Two radios as tokens moving between Sleep, Tx, and Rx.

Hear records the beacon offset on the radio that is in Rx.
Receive writes Message when the sender is in Tx and the receiver is in Rx
on that second, including data heard during the listen. The counter stays
1 until both beacons have been heard. Message stores the counter that was
sent. The next data send carries the next counter, and that sender waits.
EndTx and EndRx are what leave Tx and Rx.
"""

import protocol
from cpnpy.cpn.colorsets import ColorSetParser
from cpnpy.cpn.cpn_imp import Arc, CPN, EvaluationContext, Marking, Place, Transition
from protocol import make_radio, set_boots


def _transition(name, variables, guard, action, priority=0):
    return Transition(name, guard=guard, variables=variables, action=action, priority=priority)


def _to_rx_or_sleep(cpn, transition, rx, sleep, prefix):
    cpn.add_arc(Arc(transition, rx, f"{prefix}_rx @+{prefix}_rx_dt"))
    cpn.add_arc(Arc(transition, sleep, f"{prefix}_sleep @+{prefix}_sleep_dt"))


def build_radio_beacon(boot_a=0, offset_a=3, boot_b=50, offset_b=7):
    """Return the net, the initial marking, and the evaluation context."""
    colorsets = ColorSetParser().parse_definitions(
        """
        colset NODE = record id:string * offset:int * peer_offset:int * counter:int * hold:int * tx:string * at:int timed;
        colset MSG = record txNode:string * rxNode:string * counter:int timed;
        """
    )
    cpn = CPN()
    sleep = Place("Sleep", colorsets["NODE"])
    tx = Place("Tx", colorsets["NODE"])
    rx = Place("Rx", colorsets["NODE"])
    message = Place("Message", colorsets["MSG"])
    for place in (sleep, tx, rx, message):
        cpn.add_place(place)

    # EndTx and EndRx lose to any other step enabled on this second. A radio
    # has to enter Tx or Rx, and Hear or Receive, before it can leave.
    start_rx = _transition("StartRx", ["n"], "wants_rx(n, n['at'])", None)
    start_tx = _transition("StartTx", ["n"], "wants_tx(n, n['at'])", "start_tx(n, output)")
    hear = _transition("Hear", ["tx", "rx"], "can_hear(tx, rx)", "hear(tx, rx, output)")
    receive = _transition("Receive", ["tx", "rx"], "can_receive(tx, rx)", "receive(tx, rx, output)")
    end_tx = _transition("EndTx", ["n"], None, "leave(n, output)", 1)
    end_rx = _transition("EndRx", ["n"], None, "leave(n, output)", 1)
    for transition in (start_rx, start_tx, hear, receive, end_tx, end_rx):
        cpn.add_transition(transition)

    cpn.add_arc(Arc(sleep, start_rx, "n"))
    cpn.add_arc(Arc(start_rx, rx, "n @+0"))
    cpn.add_arc(Arc(sleep, start_tx, "n"))
    cpn.add_arc(Arc(start_tx, tx, "node @+dt"))

    cpn.add_arc(Arc(tx, hear, "tx"))
    cpn.add_arc(Arc(rx, hear, "rx"))
    cpn.add_arc(Arc(hear, tx, "sender @+0"))
    cpn.add_arc(Arc(hear, rx, "receiver @+0"))

    cpn.add_arc(Arc(tx, receive, "tx"))
    cpn.add_arc(Arc(rx, receive, "rx"))
    cpn.add_arc(Arc(receive, tx, "sender @+0"))
    cpn.add_arc(Arc(receive, rx, "receiver @+0"))
    cpn.add_arc(Arc(receive, message, "msg @+0"))

    cpn.add_arc(Arc(tx, end_tx, "n"))
    _to_rx_or_sleep(cpn, end_tx, rx, sleep, "node")
    cpn.add_arc(Arc(rx, end_rx, "n"))
    _to_rx_or_sleep(cpn, end_rx, rx, sleep, "node")

    set_boots(boot_a, boot_b)
    radio_a = make_radio("A", offset_a)
    radio_b = make_radio("B", offset_b)
    marking = Marking()
    marking.set_tokens("Sleep", [radio_a, radio_b], timestamps=[boot_a, boot_b])
    context = EvaluationContext(user_code=protocol)
    return cpn, marking, context
