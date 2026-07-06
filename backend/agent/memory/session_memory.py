"""L1 session memory."""

from datetime import datetime


class SessionMemory:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._data = {
            "survey_result": None,
            "column_result": None,
            "name_result": None,
            "code_result": None,
            "orm_result": None,
            "merge_result": None,
        }
        self._messages: list[dict] = []

    def set(self, key: str, value: dict):
        if key in self._data:
            self._data[key] = value
            self._messages.append({"type": "worker_output", "key": key, "timestamp": self._now()})

    def get(self, key: str) -> dict | None:
        return self._data.get(key)

    def get_all(self) -> dict:
        return dict(self._data)

    def add_message(self, role: str, content: str):
        self._messages.append({"role": role, "content": content[:500], "timestamp": self._now()})

    def get_messages(self) -> list[dict]:
        return self._messages

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

