import pytest

from flaskehals.interpretation import (
    LabelInfo,
    ReviewOutcome,
    interpret_comment,
    interpret_labels,
)


def test_identify_simulated_developer() -> None:
    assert interpret_labels(["dev:Alice"]).developer == "Alice"


def test_identify_assigned_reviewer() -> None:
    assert interpret_labels(["reviewer:Bob"]).reviewer == "Bob"


@pytest.mark.parametrize("priority", ["low", "medium", "high", "critical"])
def test_identify_priority(priority: str) -> None:
    assert interpret_labels([f"priority:{priority}"]).priority == priority


def test_all_labels_together() -> None:
    labels = ["bug", "dev:Alice", "reviewer:Bob", "priority:high"]
    assert interpret_labels(labels) == LabelInfo("Alice", "Bob", "high")


@pytest.mark.parametrize(
    "labels",
    [
        [],
        ["bug", "documentation"],
        ["priority:urgent"],
        ["dev:", "reviewer:  "],
        ["developer:Alice", "review:Bob"],
    ],
)
def test_missing_or_unrecognised_labels(labels: list[str]) -> None:
    assert interpret_labels(labels) == LabelInfo()


def test_label_values_are_trimmed_and_prefixes_case_insensitive() -> None:
    info = interpret_labels(["Dev: Alice ", "REVIEWER:Bob", "Priority:HIGH"])
    assert info == LabelInfo("Alice", "Bob", "high")


def test_first_matching_label_wins() -> None:
    assert interpret_labels(["reviewer:Bob", "reviewer:Carol"]).reviewer == "Bob"


def test_approval() -> None:
    assert interpret_comment("[APPROVED] Looks good", "Bob") is ReviewOutcome.APPROVED


def test_changes_requested() -> None:
    outcome = interpret_comment("[CHANGES_REQUESTED] Fix tests", "Bob")
    assert outcome is ReviewOutcome.CHANGES_REQUESTED


def test_leading_whitespace_allowed() -> None:
    assert interpret_comment("  \n[APPROVED]", "Bob") is ReviewOutcome.APPROVED


@pytest.mark.parametrize(
    "body",
    [
        "Looks good to me",
        "",
        "I'd say [APPROVED] once tests pass",  # prefix must start the comment
        "[approved] lowercase",  # prefixes are case-sensitive
        "[REJECTED] unknown prefix",
    ],
)
def test_comments_without_review_outcome(body: str) -> None:
    assert interpret_comment(body, "Bob") is None


def test_no_outcome_without_assigned_reviewer() -> None:
    assert interpret_comment("[APPROVED] Looks good", None) is None
