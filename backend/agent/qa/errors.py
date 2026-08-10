"""Public QA error taxonomy."""

from __future__ import annotations


class QAError(RuntimeError):
    code = "qa_error"


class UnsafeQuestionError(QAError):
    code = "unsafe_question"


class EntityNotFoundError(QAError):
    code = "entity_not_found"


class AmbiguousEntityError(QAError):
    code = "ambiguous_entity"


class GroundingError(QAError):
    code = "grounding_failed"
