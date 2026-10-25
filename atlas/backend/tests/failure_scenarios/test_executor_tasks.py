from unittest.mock import patch

import pytest
from celery.exceptions import Retry

from atlas.apps.executor import tasks
from tests.fakes import RecordingNotifier


def test_kill_switch_task_alerts_and_retries_when_broker_unavailable():
    notifier = RecordingNotifier()
    retried = []

    def no_gateway():
        raise RuntimeError("no credentials")

    def fake_retry(*, exc):
        retried.append(exc)
        return Retry(exc=exc)

    task = tasks.kill_switch_actions
    with (
        patch.object(tasks, "get_gateway", no_gateway),
        patch.object(tasks, "build_notifier", lambda: notifier),
        patch.object(task, "retry", fake_retry),
        pytest.raises(Retry),
    ):
        task.run()
    assert retried and isinstance(retried[0], RuntimeError)
    text, critical = notifier.messages[0]
    assert critical and "cannot reach the broker" in text and "[PAPER]" in text
