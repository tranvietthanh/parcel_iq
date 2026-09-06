from unittest.mock import MagicMock, patch


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
    ]


def test_parse_with_llm_sends_email():
    """Email is sent when a user email is found after READY transition."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks(
        user_row={"email": "test@example.com", "slug": "123-fake-st"}
    )

    patches = _task_patches(mock_db, mock_parsed_llm)
    patches.append(patch("app.services.email.send_report_ready_email"))

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as mock_send_email:
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
    patches.append(patch("app.services.email.send_report_ready_email"))

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as mock_send_email:
        parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_send_email.assert_not_called()


def test_parse_with_llm_email_failure_is_non_fatal():
    """A Resend API failure during email send does not raise from parse_with_llm."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks(
        user_row={"email": "test@example.com", "slug": "123-fake-st"}
    )

    patches = _task_patches(mock_db, mock_parsed_llm)
    patches.append(
        patch(
            "app.services.email.send_report_ready_email",
            side_effect=Exception("Resend down"),
        )
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
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

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        with patch.object(parse_with_llm, "max_retries", 3), \
             patch.object(parse_with_llm.request, "retries", 3):
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
