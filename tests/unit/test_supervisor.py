from app.agents.state import AgentState
from app.agents.supervisor import SupervisorDecision, route_supervisor


def _make_state(next_agent=None, iteration_count=0) -> AgentState:
    return {
        "messages": [],
        "user_id": "u1",
        "conversation_id": "c1",
        "user_facts": [],
        "requires_human": False,
        "human_feedback": None,
        "iteration_count": iteration_count,
        "error": None,
        "next_agent": next_agent,
    }


def test_route_supervisor_returns_next_agent():
    state = _make_state(next_agent="research")
    assert route_supervisor(state) == "research"


def test_route_supervisor_defaults_to_finish():
    state = _make_state(next_agent=None)
    assert route_supervisor(state) == "FINISH"


def test_route_supervisor_finish_explicit():
    state = _make_state(next_agent="FINISH")
    assert route_supervisor(state) == "FINISH"


def test_supervisor_decision_model():
    d = SupervisorDecision(next="email", reasoning="User asked about email")
    assert d.next == "email"
    assert "email" in d.reasoning
