"""Strict fake tools shared by ToolRuntime contract tests."""

from pydantic import ConfigDict

from backend.agent.runtime.contracts import StrictContract


class EchoInput(StrictContract):
    text: str


class EchoOutput(StrictContract):
    echoed: str


class DDLInput(StrictContract):
    statement: str


class DDLOutput(StrictContract):
    accepted: bool


class SensitiveOutput(StrictContract):
    model_config = ConfigDict(extra="forbid")

    token: str
    rows: list[dict]


def echo(text: str) -> dict:
    return {"echoed": text}


def invalid_echo(text: str) -> dict:
    return {"wrong": text}


def fake_ddl(statement: str) -> dict:
    return {"accepted": bool(statement)}
