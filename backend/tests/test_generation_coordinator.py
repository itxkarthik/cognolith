import pytest
from fastapi import HTTPException

from app.services.generation_coordinator import LocalGenerationCoordinator


def test_one_reply_at_a_time_per_session() -> None:
    coordinator = LocalGenerationCoordinator()
    coordinator.start(session_id=1, message_id=10)

    with pytest.raises(HTTPException) as raised:
        coordinator.start(session_id=1, message_id=11)
    assert raised.value.status_code == 409

    coordinator.finish(session_id=1, message_id=10)
    coordinator.start(session_id=1, message_id=11)


def test_non_streaming_reservation_blocks_a_streamed_reply() -> None:
    coordinator = LocalGenerationCoordinator()

    with coordinator.exclusive(session_id=3):
        assert coordinator.is_session_active(3)
        with pytest.raises(HTTPException):
            coordinator.start(session_id=3, message_id=30)

    assert not coordinator.is_session_active(3)


def test_cancel_sets_the_reply_cancellation_event() -> None:
    coordinator = LocalGenerationCoordinator()
    cancellation = coordinator.start(session_id=5, message_id=50)

    assert coordinator.cancel(50) is True
    assert cancellation.is_set()
    assert coordinator.cancel(999) is False


def test_finishing_another_reply_does_not_release_the_session() -> None:
    coordinator = LocalGenerationCoordinator()
    coordinator.start(session_id=9, message_id=90)

    coordinator.finish(session_id=9, message_id=91)

    assert coordinator.is_session_active(9)
