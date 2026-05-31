from unittest.mock import patch, MagicMock


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
        patch("app.tasks.compute_confidence", return_value=ConfidenceResult(scores={"overall_avg": 0.9}, overall="HIGH")),
    ]


def test_parse_with_llm_sends_email():
    """Email is sent when a user email is found after READY transition."""
    from app.tasks import parse_with_llm

    mock_db, _, mock_parsed_llm = _make_task_mocks(user_row={"email": "test@example.com"})

    patches = _task_patches(mock_db, mock_parsed_llm)
    patches.append(patch("app.services.email.send_report_ready_email"))

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as mock_send_email:
        parse_with_llm("prop_1", "rep_1", "123 Fake St")

    mock_send_email.assert_called_once_with(
        to_email="test@example.com",
        address="123 Fake St",
        property_id="prop_1",
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

    mock_db, _, mock_parsed_llm = _make_task_mocks(user_row={"email": "test@example.com"})

    patches = _task_patches(mock_db, mock_parsed_llm)
    patches.append(patch("app.services.email.send_report_ready_email", side_effect=Exception("Resend down")))

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        # Should not raise
        parse_with_llm("prop_1", "rep_1", "123 Fake St")
