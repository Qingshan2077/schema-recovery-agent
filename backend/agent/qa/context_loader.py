"""Bounded conversation context and focus extraction."""

from __future__ import annotations

from backend.agent.qa.contracts import CatalogEntity, ConversationTurn, QAContext


class QAContextLoader:
    def __init__(self, *, max_messages: int = 12):
        self.max_messages = max_messages

    def load(
        self,
        *,
        thread_id: str | None,
        messages: list[dict],
        inventory: list[CatalogEntity],
    ) -> QAContext:
        turns = [ConversationTurn.model_validate(message) for message in messages[-self.max_messages :]]
        focus_names: list[str] = []
        for turn in reversed(turns):
            structured = turn.structured or {}
            for entity in structured.get("entities", []):
                name = entity.get("canonical_name")
                if name and name not in focus_names:
                    focus_names.append(name)
            if focus_names:
                break
        by_name = {entity.name: entity for entity in inventory}
        return QAContext(
            thread_id=thread_id,
            messages=turns,
            focus_entities=[by_name[name] for name in focus_names if name in by_name],
        )


ThreadContextLoader = QAContextLoader
