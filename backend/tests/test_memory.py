from backend.agent.memory.global_memory import GlobalMemory
from backend.agent.memory.session_memory import SessionMemory


def test_session_memory_roundtrip():
    memory = SessionMemory("test_session")
    memory.set("survey_result", {"status": "success"})
    assert memory.get("survey_result")["status"] == "success"
    assert memory.get_messages()


def test_global_memory_defaults():
    memory = GlobalMemory()
    assert memory.get_by_category("naming")
    assert memory.get_by_category("non_fk")

