import pytest

from agents.retrieval.catalog import SourceEntry, read_source
from agents.retrieval.vector import validate_vector


@pytest.mark.parametrize(
    "values,dimensions", [([0, 0], 2), ([1], 2), ([float("nan"), 1], 2), ([True, 1], 2)]
)
def test_invalid_embedding_vectors(values, dimensions):
    with pytest.raises(ValueError):
        validate_vector(values, dimensions)


def test_course_source_cannot_escape_directory(tmp_path):
    root = tmp_path / "course"
    root.mkdir()
    (tmp_path / "secret.md").write_text("fixture secret", encoding="utf-8")
    source = SourceEntry(
        id="source",
        title="fixture",
        file="../secret.md",
        source_url="https://example.com",
        section="fixture",
        license="fixture",
        version="v1",
        review_status="approved",
    )
    with pytest.raises(ValueError, match="inside"):
        read_source(root, source)
