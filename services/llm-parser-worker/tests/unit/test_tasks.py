from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import MaxRetriesExceededError


def _make_task_mocks(user_row=None):
    """Return (mock_db, mock_cursor, mock_parsed_llm) for parse_with_llm tests."""
    mock_db = MagicMock()
    mock_conn = mock_db.return_value
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [
        {"raw_scraped_data": {"some": "data"}},
        user_row,
    ]
    mock_parsed_llm = MagicMock()
    mock_parsed_llm.model_dump.return_value = {"parsed": "ok"}
    return mock_db, mock_cursor, mock_parsed_llm


def _task_patches(mock_db, mock_parsed_llm):
    from app.schemas.confidence import ConfidenceResult

    return [
        patch("app.tasks.get_db_connection", mock_db),
        patch("app.tasks.build_user_prompt", return_value="prompt"),
        patch("app.tasks.llm_client.generate_json", return_value='{"parsed": "ok"}'),
        patch("app.tasks.LlmOutput.model_validate_json", return_value=mock_parsed_llm),
        patch(
            "app.tasks.compute_confidence",
            return_value=ConfidenceResult(scores={"overall_avg": 0.9}, overall="HIGH"),
        ),
        patch("app.tasks.is_daily_quota_exhausted", return_value=False),
        patch("app.tasks.wait_for_token", return_value=None),
        patch("app.tasks.record_llm_request", return_value=None),
    ]


def test_parse_with_llm_sends_email():
    """Email is sent when a user email is found after READY transition."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks(
        user_row={"email": "test@example.com", "slug": "123-fake-st"}
    )

    patches = _task_patches(mock_db, mock_parsed_llm)
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        mock_send_email = stack.enter_context(patch("app.services.email.send_report_ready_email"))
        parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_send_email.assert_called_once_with(
        to_email="test@example.com",
        address="123 Fake St",
        slug="123-fake-st",
    )


def test_parse_with_llm_no_email_when_no_user():
    """Email is NOT sent when no user requested the report."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks(user_row=None)

    patches = _task_patches(mock_db, mock_parsed_llm)
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        mock_send_email = stack.enter_context(patch("app.services.email.send_report_ready_email"))
        parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_send_email.assert_not_called()


def test_parse_with_llm_email_failure_is_non_fatal():
    """A Resend API failure during email send does not raise from parse_with_llm."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks(
        user_row={"email": "test@example.com", "slug": "123-fake-st"}
    )

    patches = _task_patches(mock_db, mock_parsed_llm)
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch(
                "app.services.email.send_report_ready_email",
                side_effect=Exception("Resend down"),
            )
        )
        # Should not raise
        parse_with_llm("prop_1", "rep_1", "123 Fake St")


def test_parse_with_llm_redacts_credentials_in_error_message():
    """Any credential matching key=, api_key=, or Bearer must be redacted
    in error_message and logs.
    """
    from app.tasks import parse_with_llm

    mock_db, mock_cursor, mock_parsed_llm = _make_task_mocks()
    raw_secret = "AIzaSyD-secret-key-12345678"
    raw_ant_secret = "sk-ant-api03-abcdef1234567890"
    raw_bearer_token = "sk-proj-openai-secret-token-12345678"

    patches = _task_patches(mock_db, mock_parsed_llm)
    # Force llm_client.generate_json to raise with embedded API key
    patches[2] = patch(
        "app.tasks.llm_client.generate_json",
        side_effect=RuntimeError(
            f"HTTP 500: API failed with key={raw_secret}, api_key={raw_ant_secret}, "
            f"and Authorization: Bearer {raw_bearer_token}"
        ),
    )

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(patch.object(parse_with_llm, "max_retries", 3))
        stack.enter_context(patch.object(parse_with_llm.request, "retries", 3))
        parse_with_llm("prop_1", "rep_1", "123 Fake St")

    # Find the UPDATE query executed on failure
    execute_calls = mock_cursor.execute.call_args_list
    failed_call = next(
        (call for call in execute_calls if "status='FAILED'" in call[0][0]),
        None,
    )
    assert failed_call is not None, "Expected an UPDATE setting status='FAILED'"
    error_param = failed_call[0][1][0]

    assert raw_secret not in error_param
    assert raw_ant_secret not in error_param
    assert raw_bearer_token not in error_param
    assert "key=[REDACTED]" in error_param
    assert "api_key=[REDACTED]" in error_param
    assert "Bearer [REDACTED]" in error_param


def test_parse_with_llm_calls_rate_limiter_and_records_on_success():
    """Rate limiter token is requested and quota recorded on success."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks()
    patches = _task_patches(mock_db, mock_parsed_llm)

    with ExitStack() as stack:
        for p in patches[:5]:
            stack.enter_context(p)
        mock_is_exhausted = stack.enter_context(
            patch("app.tasks.is_daily_quota_exhausted", return_value=False)
        )
        mock_wait_token = stack.enter_context(patch("app.tasks.wait_for_token"))
        mock_record_quota = stack.enter_context(patch("app.tasks.record_llm_request"))

        parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_is_exhausted.assert_called_once()
    mock_wait_token.assert_called_once()
    mock_record_quota.assert_called_once()


def test_parse_with_llm_does_not_record_quota_on_failure():
    """Failed provider call must not record/increment quota."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks()
    patches = _task_patches(mock_db, mock_parsed_llm)
    patches[2] = patch(
        "app.tasks.llm_client.generate_json",
        side_effect=RuntimeError("Provider 500 error"),
    )

    with ExitStack() as stack:
        for p in patches[:5]:
            stack.enter_context(p)
        stack.enter_context(patch("app.tasks.is_daily_quota_exhausted", return_value=False))
        stack.enter_context(patch("app.tasks.wait_for_token"))
        mock_record_quota = stack.enter_context(patch("app.tasks.record_llm_request"))
        stack.enter_context(patch.object(parse_with_llm, "max_retries", 3))
        stack.enter_context(patch.object(parse_with_llm.request, "retries", 3))

        parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_record_quota.assert_not_called()


def test_parse_with_llm_rate_limit_updates_timestamp_before_retry():
    """When rate limited, updated_at is bumped in DB before retry."""
    from app.tasks import parse_with_llm

    mock_db, mock_cursor, mock_parsed_llm = _make_task_mocks()
    patches = _task_patches(mock_db, mock_parsed_llm)
    # wait_for_token times out
    patches[6] = patch(
        "app.tasks.wait_for_token",
        side_effect=RuntimeError("RATE_LIMIT: token wait exceeded max_wait_seconds"),
    )

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        mock_retry = stack.enter_context(
            patch.object(parse_with_llm, "retry", side_effect=RuntimeError("retrying"))
        )

        with pytest.raises(RuntimeError, match="retrying"):
            parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_retry.assert_called_once()
    # Check that updated_at=NOW() was executed before retry
    execute_calls = mock_cursor.execute.call_args_list
    bump_call = next(
        (
            call
            for call in execute_calls
            if "UPDATE property_reports SET updated_at=NOW() WHERE id=%s" in call[0][0]
        ),
        None,
    )
    assert bump_call is not None, "Expected an UPDATE bumping updated_at=NOW()"


def test_parse_with_llm_daily_quota_exceeded_retries_with_midnight_countdown():
    """Daily quota exhaustion calculates countdown until midnight and bumps updated_at."""
    from app.tasks import parse_with_llm

    mock_db, mock_cursor, mock_parsed_llm = _make_task_mocks()
    patches = _task_patches(mock_db, mock_parsed_llm)
    patches[5] = patch("app.tasks.is_daily_quota_exhausted", return_value=True)

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        mock_retry = stack.enter_context(
            patch.object(parse_with_llm, "retry", side_effect=RuntimeError("quota retry"))
        )

        with pytest.raises(RuntimeError, match="quota retry"):
            parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_retry.assert_called_once()
    retry_kwargs = mock_retry.call_args[1]
    assert retry_kwargs["max_retries"] == 24
    assert retry_kwargs["countdown"] > 0
    assert retry_kwargs["countdown"] <= 86400

    execute_calls = mock_cursor.execute.call_args_list
    bump_call = next(
        (
            call
            for call in execute_calls
            if "UPDATE property_reports SET updated_at=NOW() WHERE id=%s" in call[0][0]
        ),
        None,
    )
    assert bump_call is not None, "Expected an UPDATE bumping updated_at=NOW()"


def test_parse_with_llm_daily_quota_exhaustion_marks_report_failed():
    """When daily quota retries are exhausted (MaxRetriesExceededError), report is marked FAILED."""
    from app.tasks import parse_with_llm

    mock_db, mock_cursor, mock_parsed_llm = _make_task_mocks()
    patches = _task_patches(mock_db, mock_parsed_llm)
    patches[5] = patch("app.tasks.is_daily_quota_exhausted", return_value=True)

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch.object(
                parse_with_llm,
                "retry",
                side_effect=MaxRetriesExceededError("Can't retry anymore"),
            )
        )

        with pytest.raises(MaxRetriesExceededError):
            parse_with_llm("prop_1", "rep_1", "123 Fake St")

    execute_calls = mock_cursor.execute.call_args_list
    failed_call = next(
        (call for call in execute_calls if "status='FAILED'" in call[0][0]),
        None,
    )
    assert failed_call is not None, "Expected an UPDATE setting status='FAILED'"
    error_param = failed_call[0][1][0]
    assert "DAILY_QUOTA_EXCEEDED" in error_param


def test_parse_with_llm_rate_limit_exhaustion_marks_report_failed():
    """When rate-limit retries are exhausted (MaxRetriesExceededError), report is marked FAILED."""
    from app.tasks import parse_with_llm

    mock_db, mock_cursor, mock_parsed_llm = _make_task_mocks()
    patches = _task_patches(mock_db, mock_parsed_llm)
    patches[6] = patch(
        "app.tasks.wait_for_token",
        side_effect=RuntimeError("RATE_LIMIT: token wait exceeded max_wait_seconds"),
    )

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch.object(
                parse_with_llm,
                "retry",
                side_effect=MaxRetriesExceededError("Rate limit retries exhausted"),
            )
        )

        with pytest.raises(MaxRetriesExceededError):
            parse_with_llm("prop_1", "rep_1", "123 Fake St")

    execute_calls = mock_cursor.execute.call_args_list
    failed_call = next(
        (call for call in execute_calls if "status='FAILED'" in call[0][0]),
        None,
    )
    assert failed_call is not None, "Expected an UPDATE setting status='FAILED'"
    error_param = failed_call[0][1][0]
    assert "RATE_LIMIT" in error_param
