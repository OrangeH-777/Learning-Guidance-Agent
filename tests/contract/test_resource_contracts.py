"""Shape regressions derived from R04, TC024/028 and TC054; not content approval."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.schemas.resources import resource_draft_adapter

FIXTURES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "resource_contracts.json").read_text(encoding="utf-8")
)["resources"]


@pytest.mark.parametrize("resource", FIXTURES, ids=["lecture", "exercise", "mindmap"])
def test_resource_samples_match_contract_and_round_trip(resource):
    parsed = resource_draft_adapter.validate_python(resource)
    assert resource_draft_adapter.validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize("field", ["source_ids", "questions"])
def test_exercise_rejects_empty_required_collections(field):
    candidate = deepcopy(FIXTURES[1])
    candidate[field] = []
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)


@pytest.mark.parametrize("analysis", [None, "", "   ", 123])
def test_missing_or_invalid_explanation_is_not_a_valid_exercise(analysis):
    candidate = deepcopy(FIXTURES[1])
    candidate["questions"][0]["analysis"] = analysis
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)


def test_answer_must_reference_an_existing_choice():
    candidate = deepcopy(FIXTURES[1])
    candidate["questions"][0]["answer"] = "C"
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)


def test_ambiguous_option_labels_are_rejected():
    candidate = deepcopy(FIXTURES[1])
    candidate["questions"][0]["options"][1]["label"] = "A"
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)


def test_duplicate_question_numbers_are_rejected():
    candidate = deepcopy(FIXTURES[1])
    candidate["questions"][1]["question_id"] = "Q1"
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)


def test_model_cannot_assign_itself_human_approval_or_ownership():
    candidate = deepcopy(FIXTURES[0])
    candidate.update(review_status="human_pass", user_id="other-user")
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)


def test_mindmap_needs_nonempty_root_and_hierarchy():
    candidate = deepcopy(FIXTURES[2])
    candidate["root"]["children"] = []
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)


def test_title_length_counts_unicode_codepoints_without_truncating():
    candidate = deepcopy(FIXTURES[0])
    candidate["title"] = "🌳" * 100
    assert len(resource_draft_adapter.validate_python(candidate).title) == 100
    candidate["title"] += "树"
    with pytest.raises(ValidationError):
        resource_draft_adapter.validate_python(candidate)
