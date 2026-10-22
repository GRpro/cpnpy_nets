"""Two radios discover each other by beacon, then count each delivery.

One token per radio. It sleeps, moves to Tx to send, and to Rx to listen.
Its first timestamp is its boot. The listen is 30 seconds every 300 seconds,
the first one at boot. After it, a beacon goes out every 30 seconds and a
data slot every 10. A beacon on the same second as data wins, and that data
send is skipped.

The beacon carries an offset from 1 to 10: seconds from the beacon to the
next data slot. Hearing a beacon stores that offset. A later beacon stores
the same one. The receiver opens Rx on that exact data second.
`peer_offset` is 0 until a beacon is heard.

The token stores that second in `at`. An output arc delays it by the gap
until the next one, so the timestamp and `at` stay the same second. The
first `at` is the boot.

Hear and Receive leave the radios in Tx and Rx. EndTx and EndRx move
them on. Only the radio in Rx learns the offset, and only from the
beacon it hears. Until that beacon, it stays in Rx for each second of
the listen and records data it hears. The counter stays 1 until both
radios have heard. Message stores the counter that was sent, so the
hop that finds both beacons heard can still show 1. The next data
send carries the next counter, and that sender waits.
"""

from copy import deepcopy

BEACON = 30
DATA = 10
LISTEN = 30
CYCLE = 300
HORIZON = 400
BOOT = {}


def set_boots(boot_a, boot_b):
    """Record the boot second of each radio. The first token uses that same time."""
    for boot in (boot_a, boot_b):
        if not 0 <= boot <= 100:
            raise ValueError(f"boot time {boot} is outside 0..100")
    BOOT["A"] = boot_a
    BOOT["B"] = boot_b


def make_radio(node_id, offset):
    if node_id not in BOOT:
        raise ValueError(node_id)
    if not 1 <= offset <= DATA:
        raise ValueError(f"offset {offset} is outside 1..10")
    return {
        "id": node_id,
        "offset": offset,
        "peer_offset": 0,
        "counter": 1,
        "hold": 0,
        "tx": "",
        "at": BOOT[node_id],
    }


def _boot(node):
    return BOOT[node["id"]]


def _peer_id(node):
    return "A" if node["id"] == "B" else "B"


def in_listen(node, moment):
    origin = _boot(node)
    return moment >= origin and (moment - origin) % CYCLE < LISTEN


def is_beacon_time(node, moment):
    if moment < _boot(node) + LISTEN or moment > HORIZON or in_listen(node, moment):
        return False
    return (moment - _boot(node)) % BEACON == 0


def is_data_time(node, moment):
    if moment > HORIZON:
        return False
    first = _boot(node) + LISTEN + node["offset"]
    if moment < first or (moment - first) % DATA != 0:
        return False
    return not in_listen(node, moment) and not is_beacon_time(node, moment)


def is_peer_data(node, moment):
    """The exact second of the peer's data send."""
    if not node["peer_offset"]:
        return False
    peer = {"id": _peer_id(node), "offset": node["peer_offset"]}
    return is_data_time(peer, moment)


def wants_rx(node, moment):
    """Discovery listen, or the peer's data second, unless this second is our beacon."""
    if is_beacon_time(node, moment):
        return False
    return in_listen(node, moment) or is_peer_data(node, moment)


def wants_tx(node, moment):
    """Beacon wins. Data is sent only when this radio is not listening."""
    if is_beacon_time(node, moment):
        return True
    if in_listen(node, moment) or is_peer_data(node, moment) or node["hold"]:
        return False
    return is_data_time(node, moment)


def next_second(node, now):
    """Next second this radio listens or sends."""
    start = now + 1
    if in_listen(node, now):
        origin = _boot(node)
        end = min(origin + ((now - origin) // CYCLE) * CYCLE + LISTEN, HORIZON + 1)
        # The offset is still unknown, so stay up for the whole window.
        if not node["peer_offset"] and start < end:
            return start
        peer = {"id": _peer_id(node)}
        for moment in range(start, end):
            if is_beacon_time(peer, moment) or is_peer_data(node, moment):
                return moment
        start = end
    for moment in range(start, HORIZON + 1):
        if wants_rx(node, moment) or wants_tx(node, moment):
            return moment
    return None


def leave(node, output):
    """Delay this radio until its next listen or send."""
    radio = deepcopy(node)
    now = radio["at"]
    radio["tx"] = ""
    output["node_rx"] = []
    output["node_rx_dt"] = 0
    output["node_sleep"] = []
    output["node_sleep_dt"] = 0
    nxt = next_second(radio, now)
    if nxt is None:
        radio["at"] = HORIZON + 1
        output["node_sleep"] = radio
        output["node_sleep_dt"] = HORIZON + 1 - now
        return
    radio["at"] = nxt
    delay = nxt - now
    if wants_rx(radio, nxt):
        output["node_rx"] = radio
        output["node_rx_dt"] = delay
        return
    output["node_sleep"] = radio
    output["node_sleep_dt"] = delay


def start_tx(node, output):
    radio = deepcopy(node)
    radio["tx"] = "beacon" if is_beacon_time(radio, radio["at"]) else "data"
    output["node"] = radio
    output["dt"] = 0


def can_hear(tx, rx):
    return (
        tx["id"] != rx["id"]
        and tx["at"] == rx["at"]
        and tx["tx"] == "beacon"
        and in_listen(rx, rx["at"])
    )


def hear(tx, rx, output):
    """The radio in Rx stores this beacon's data offset. The sender learns nothing."""
    sender = deepcopy(tx)
    receiver = deepcopy(rx)
    receiver["peer_offset"] = sender["offset"]
    sender["tx"] = ""
    output["sender"] = sender
    output["receiver"] = receiver


def can_receive(tx, rx):
    return (
        tx["id"] != rx["id"]
        and tx["at"] == rx["at"]
        and tx["tx"] == "data"
        and (is_peer_data(rx, rx["at"]) or in_listen(rx, rx["at"]))
    )


def receive(tx, rx, output):
    sender = deepcopy(tx)
    receiver = deepcopy(rx)
    output["msg"] = {
        "txNode": sender["id"],
        "rxNode": receiver["id"],
        "counter": sender["counter"],
    }
    # The counter moves only after each radio has heard the other's beacon.
    # Until then the same counter is delivered again.
    if sender["peer_offset"] and receiver["peer_offset"]:
        receiver["counter"] = sender["counter"] + 1
        receiver["hold"] = 0
        sender["hold"] = 1
    sender["tx"] = ""
    output["sender"] = sender
    output["receiver"] = receiver
