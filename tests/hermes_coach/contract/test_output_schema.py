from __future__ import annotations

from hermes_coach.prompt.output_schema import coach_output_json_schema


def test_output_schema_has_one_required_question_and_no_questions_array() -> None:
    schema = coach_output_json_schema()

    assert "question" in schema["required"]
    assert schema["properties"]["question"]["type"] == "string"
    assert "questions" not in schema["properties"]

