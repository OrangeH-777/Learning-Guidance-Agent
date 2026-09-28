from copy import deepcopy

import pytest
from cryptography.fernet import Fernet

from agents.schemas.resources import resource_draft_adapter
from agents.validators.data_structure import brackets_match, check_data_structure
from backend.app.core.security import CredentialCipher
from tests.unit.test_learning_workflow import RESOURCES


@pytest.mark.parametrize(
    "sequence,expected",
    [("", True), ("([])", True), ("([)]", False), ("(()", False), (")(", False)],
)
def test_bracket_reference(sequence, expected):
    assert brackets_match(sequence) is expected


def test_known_fact_error_and_answer_contradiction_are_rejected():
    lecture = deepcopy(RESOURCES[0])
    lecture["sections"][0]["explanation"] = "二分查找适用于任意无序数组"
    assert check_data_structure(resource_draft_adapter.validate_python(lecture))
    exercise = deepcopy(RESOURCES[1])
    exercise["questions"][1]["answer"] = "匹配"
    assert check_data_structure(resource_draft_adapter.validate_python(exercise))
    assert check_data_structure(resource_draft_adapter.validate_python(RESOURCES[1])) == ()


def test_fernet_rotation_new_key_reads_all_old_ciphertexts():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    encoded = CredentialCipher([old]).encrypt("fixture-secret")
    rotated = CredentialCipher([new, old]).rotate(encoded)
    assert CredentialCipher([new]).decrypt(rotated) == "fixture-secret"
    with pytest.raises(ValueError):
        CredentialCipher([old]).decrypt(rotated)
