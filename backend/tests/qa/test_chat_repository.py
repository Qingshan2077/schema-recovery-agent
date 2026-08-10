from backend.chat.repository import SQLiteChatRepository


def test_idempotency_key_reuses_the_same_message_and_run(tmp_path):
    repository = SQLiteChatRepository(tmp_path / "chat.db")
    thread = repository.create_thread(owner_id="local", title="QA")

    first = repository.start_run(
        thread_id=thread.thread_id,
        owner_id="local",
        content="products表有哪些字段",
        idempotency_key="request-0001",
    )
    second = repository.start_run(
        thread_id=thread.thread_id,
        owner_id="local",
        content="products表有哪些字段",
        idempotency_key="request-0001",
    )

    assert second.reused is True
    assert second.message_id == first.message_id
    assert second.run_id == first.run_id


def test_owner_boundary_hides_threads_and_runs(tmp_path):
    repository = SQLiteChatRepository(tmp_path / "chat.db")
    thread = repository.create_thread(owner_id="tenant-a")
    started = repository.start_run(
        thread_id=thread.thread_id,
        owner_id="tenant-a",
        content="list tables",
        idempotency_key=None,
    )

    assert repository.get_thread(thread.thread_id, owner_id="tenant-b") is None
    assert repository.get_run(started.run_id, owner_id="tenant-b") is None
