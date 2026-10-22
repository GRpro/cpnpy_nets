"""State-space checks for the two-radio beacon net."""

import networkx as nx

import protocol
from cpnpy.analysis.analyzer import StateSpaceAnalyzer

from net import build_radio_beacon

SCENARIOS = (
    ("boots one second apart", 0, 2, 1, 4),
    ("boots 0 and 50", 0, 3, 50, 7),
)


def _radios(marking):
    found = []
    for place in ("Sleep", "Tx", "Rx"):
        for token in marking.get_multiset(place).tokens:
            found.append((place, token.timestamp, token.value))
    return found


def _messages(marking):
    return [(token.timestamp, token.value) for token in marking.get_multiset("Message").tokens]


def _check_scenario(name, boot_a, offset_a, boot_b, offset_b):
    cpn, marking, context = build_radio_beacon(boot_a, offset_a, boot_b, offset_b)
    analyzer = StateSpaceAnalyzer(cpn, marking, context)
    dead = analyzer.list_dead_markings()
    assert len(dead) == 1, f"{name}: the run never finishes"
    assert not context.guard_errors, f"{name}: guard errors {context.guard_errors}"
    looping = [component for component in nx.strongly_connected_components(analyzer.RG) if len(component) > 1]
    assert not looping, f"{name}: the state space loops"
    assert not analyzer.list_dead_transitions(), (name, analyzer.list_dead_transitions())

    ready = []
    heard_at = {}
    for node in analyzer.RG.nodes():
        state = analyzer.RG.nodes[node]["marking"]
        radios = _radios(state)
        ids = [item[2]["id"] for item in radios]
        assert len(ids) == len(set(ids)), f"{name}: a radio is in two places at once"
        txs = [radio for place, _, radio in radios if place == "Tx"]
        rxs = [radio for place, _, radio in radios if place == "Rx"]
        for tx in txs:
            for rx in rxs:
                if protocol.can_hear(tx, rx):
                    heard_at[rx["id"]] = min(rx["at"], heard_at.get(rx["id"], rx["at"]))
                if protocol.can_receive(tx, rx):
                    ready.append((rx["at"], rx["id"]))
        for place, timestamp, radio in radios:
            assert timestamp == radio["at"], (name, place, timestamp, radio["at"])
            if place != "Tx":
                continue
            assert not protocol.in_listen(radio, timestamp), name
            if radio["tx"] == "data":
                assert not protocol.is_beacon_time(radio, timestamp), name

    for node in dead:
        state = analyzer.RG.nodes[node]["marking"]
        found = _radios(state)
        assert {item[0] for item in found} == {"Sleep"}, name
        radios = [item[2] for item in found]
        by_id = {item["id"]: item for item in radios}
        assert set(by_id) == {"A", "B"}, name
        for radio in radios:
            other = by_id["B" if radio["id"] == "A" else "A"]
            if radio["peer_offset"]:
                assert radio["peer_offset"] == other["offset"], name
        heard = {radio["id"] for radio in radios if radio["peer_offset"]}
        assert heard == set(heard_at), (name, heard, set(heard_at))
        messages = sorted(_messages(state), key=lambda item: item[0])
        assert messages, f"{name}: no delivery"
        first_at, first_id = min(ready)
        assert messages[0][0] == first_at, (name, messages[0], first_at)
        assert messages[0][1]["rxNode"] == first_id
        assert messages[0][1]["counter"] == 1
        specs = {"A": (boot_a, offset_a), "B": (boot_b, offset_b)}
        previous_at = None
        for moment, value in messages:
            assert set(value) == {"txNode", "rxNode", "counter"}, (name, value)
            assert value["txNode"] != value["rxNode"]
            assert previous_at is None or moment > previous_at, (name, moment)
            previous_at = moment
            sender = {"id": value["txNode"], "offset": specs[value["txNode"]][1]}
            assert protocol.is_data_time(sender, moment), (name, moment, value)
            heard_offset = (
                sender["offset"]
                if value["rxNode"] in heard_at and heard_at[value["rxNode"]] <= moment
                else 0
            )
            receiver = {
                "id": value["rxNode"],
                "offset": specs[value["rxNode"]][1],
                "peer_offset": heard_offset,
            }
            assert protocol.in_listen(receiver, moment) or protocol.is_peer_data(receiver, moment), (name, moment)
            assert protocol.wants_rx(receiver, moment), (name, moment)
            if value["rxNode"] not in heard_at or heard_at[value["rxNode"]] > moment:
                assert value["counter"] == 1, (name, moment, value)
                assert protocol.in_listen(receiver, moment), (name, moment)
        increased = [(moment, value) for moment, value in messages if value["counter"] > 1]
        if heard != {"A", "B"}:
            assert len(heard) == 1, name
            assert not increased, name
            assert len(messages) > 1, name
            assert {value["rxNode"] for _, value in messages} == heard, name
            for radio in radios:
                assert radio["counter"] == 1 and radio["hold"] == 0, (name, radio)
            continue
        late = max(heard_at, key=heard_at.get)
        before = [value for moment, value in messages if value["rxNode"] == late and moment < heard_at[late]]
        assert before and all(value["counter"] == 1 for value in before), name
        assert increased, name
        previous = None
        for offset, (moment, value) in enumerate(increased):
            assert value["counter"] == offset + 2, (name, moment, value)
            assert moment > max(heard_at.values()), (name, moment)
            assert previous is None or value["txNode"] != previous, (name, moment, value)
            previous = value["txNode"]
        plain = [value for moment, value in messages if moment < increased[0][0]]
        assert plain and all(value["counter"] == 1 for value in plain), name
        last = messages[-1][1]
        for radio in radios:
            if radio["id"] == last["rxNode"]:
                assert radio["counter"] == last["counter"] + 1, (name, radio)
                assert radio["hold"] == 0, (name, radio)
            else:
                assert radio["counter"] == last["counter"], (name, radio)
                assert radio["hold"] == 1, (name, radio)

    sample = sorted(
        _messages(analyzer.RG.nodes[dead[0]]["marking"]),
        key=lambda item: item[0],
    )
    final = {item[2]["id"]: item[2]["counter"] for item in _radios(analyzer.RG.nodes[dead[0]]["marking"])}
    print(
        f"{name}: {analyzer.RG.number_of_nodes()} markings, "
        f"{len(sample)} exchanges, heard {', '.join(sorted(heard_at))}, "
        f"A {final['A']}, B {final['B']}"
    )


def prove():
    print("=== Radio beacon state space ===")
    for scenario in SCENARIOS:
        _check_scenario(*scenario)
    print("All checked properties hold.")
    print("Each draw stops at 400 seconds. The counter does not grow past that horizon.")


if __name__ == "__main__":
    prove()
