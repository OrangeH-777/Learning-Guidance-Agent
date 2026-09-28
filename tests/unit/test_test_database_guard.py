import pytest

from scripts.test_database import require_test_database


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        "not-a-url-secret",
        "sqlite:///lga_test",
        "postgresql://u:secret@localhost/",
        "postgresql://u:secret@localhost/lga_dev",
        "postgresql://u:secret@localhost/lga_test?dbname=lga_dev",
        "postgresql://u:secret@localhost/lga_test?service=production",
        "postgresql://u:secret@localhost/lga_test?host=production",
    ],
)
def test_reject_unsafe_test_database_without_exposing_credentials(candidate):
    with pytest.raises(ValueError) as error:
        require_test_database(candidate, "postgresql://u:secret@localhost/lga_dev")
    assert "secret" not in str(error.value)


def test_same_database_other_role_or_alias_cannot_bypass_guard():
    with pytest.raises(ValueError):
        require_test_database(
            "postgresql+psycopg://test_role:secret@127.0.0.1:5432/shared_test",
            "postgresql://app_role:other@localhost/shared_test",
        )


def test_separate_database_is_allowed():
    url = "postgresql+psycopg://test_role:secret@localhost/lga_test"
    assert require_test_database(url, "postgresql://app@localhost/lga_dev") == url
