"""Dining philosophers as a Petri net, with a state-space proof.

Five philosophers sit around a table. Each needs the fork on either side in
order to eat, and both forks are taken in one step. The reachability graph of
that net is small enough to check mutual exclusion, 1-safety, deadlock
freedom, and the liveness notion built into cpnpy.
"""

from cpnpy.analysis.analyzer import StateSpaceAnalyzer
from cpnpy.analysis.reachability import equiv_marking_to_key
from cpnpy.cpn.cpn_imp import (
    Arc,
    CPN,
    EvaluationContext,
    Marking,
    Place,
    Transition,
)
from cpnpy.cpn.colorsets import ColorSetParser

N = 5


def build_dining_philosophers(n: int = N):
    """Return the net, the initial marking, and an empty evaluation context.

    Every place holds unit tokens (the value ``()``). Input arcs bind the
    variable ``u`` because this library only accepts a variable on an input
    arc. Output arcs write the constant ``()``.
    """
    if n < 2:
        raise ValueError("dining philosophers needs at least two seats")

    unit = ColorSetParser().parse_definitions("colset UNIT = unit;")["UNIT"]
    cpn = CPN()
    thinking = [Place(f"think_{i}", unit) for i in range(n)]
    eating = [Place(f"eat_{i}", unit) for i in range(n)]
    forks = [Place(f"fork_{i}", unit) for i in range(n)]
    for place in (*thinking, *eating, *forks):
        cpn.add_place(place)

    for i in range(n):
        left = forks[i]
        right = forks[(i + 1) % n]
        take = Transition(f"take_{i}", variables=["u"])
        put = Transition(f"put_{i}", variables=["u"])
        cpn.add_transition(take)
        cpn.add_transition(put)

        cpn.add_arc(Arc(thinking[i], take, "u"))
        cpn.add_arc(Arc(left, take, "u"))
        cpn.add_arc(Arc(right, take, "u"))
        cpn.add_arc(Arc(take, eating[i], "()"))

        cpn.add_arc(Arc(eating[i], put, "u"))
        cpn.add_arc(Arc(put, thinking[i], "()"))
        cpn.add_arc(Arc(put, left, "()"))
        cpn.add_arc(Arc(put, right, "()"))

    marking = Marking()
    for i in range(n):
        marking.set_tokens(f"think_{i}", [()])
        marking.set_tokens(f"fork_{i}", [()])
    return cpn, marking, EvaluationContext()


def _tokens(marking: Marking, place_name: str) -> int:
    return len(marking.get_multiset(place_name).tokens)


def prove(n: int = N) -> StateSpaceAnalyzer:
    """Explore every reachable marking and reject the run if a property fails.

    The analyzer's live-transition check means each transition is enabled
    inside every terminal strongly connected component. For this net that
    component is the whole state space. It does not prove that an unfair
    scheduler cannot starve one philosopher.
    """
    cpn, marking, context = build_dining_philosophers(n)
    analyzer = StateSpaceAnalyzer(cpn, marking, context)
    report = analyzer.summarize()

    print("=== Dining philosophers state space ===")
    for key, value in report.items():
        print(f"{key}: {value}")

    names = {transition.name for transition in cpn.transitions}
    terminal = [
        node for node in analyzer.SG.nodes() if analyzer.SG.out_degree(node) == 0
    ]
    # Independent sets of the 5-cycle, including the all-thinking marking.
    expected_markings = {5: 11}.get(n)

    if expected_markings is not None:
        assert analyzer.RG.number_of_nodes() == expected_markings, (
            f"expected {expected_markings} markings, "
            f"found {analyzer.RG.number_of_nodes()}"
        )

    for place_name, (low, high) in report["place_bounds"].items():
        assert high <= 1, f"{place_name} holds {high} tokens"
        assert low >= 0, f"{place_name} has a negative lower bound"

    for node in analyzer.RG.nodes():
        state = analyzer.RG.nodes[node]["marking"]
        for i in range(n):
            eating = _tokens(state, f"eat_{i}")
            neighbor = _tokens(state, f"eat_{(i + 1) % n}")
            thinking = _tokens(state, f"think_{i}")
            fork = _tokens(state, f"fork_{i}")
            left_neighbor_eating = _tokens(state, f"eat_{(i - 1) % n}")
            assert eating + neighbor <= 1, f"neighbors {i} and {(i + 1) % n} both eat"
            assert thinking + eating == 1, f"philosopher {i} is not thinking xor eating"
            assert fork == int(eating == 0 and left_neighbor_eating == 0), (
                f"fork {i} does not match its neighbors"
            )

    assert report["dead_markings"] == [], "the net can deadlock"
    assert report["dead_transitions"] == [], "some transition is never enabled"
    assert len(terminal) == 1, "the state space is not a single home component"
    initial_key = equiv_marking_to_key(marking)
    assert initial_key in report["home_markings"], (
        "the all-thinking marking is not a home marking"
    )
    assert names <= set(report["live_transitions"]), (
        "a pickup or release leaves the home space"
    )

    print("All checked properties hold.")
    print(
        "Not claimed: starvation freedom. An unfair scheduler can keep feeding "
        "one philosopher's neighbors forever."
    )
    return analyzer


if __name__ == "__main__":
    prove()
