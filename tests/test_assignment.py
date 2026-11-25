"""Assignment scenarios from features/task-creation-developer-assignment.feature."""

from flaskehals.assignment import (
    DeveloperProfile,
    extract_keywords,
    recommend_developer,
)

SPEC = "## Objective\nExport invoices as CSV using Postgres and pandas"


def test_keywords_drop_stopwords_headings_and_short_words() -> None:
    assert extract_keywords("## Objective\nThe Neo4j API is up") == {"neo4j", "api"}


def test_lower_workload_is_recommended_when_otherwise_equal() -> None:
    result = recommend_developer(
        [
            DeveloperProfile("Busy", open_pull_requests=3, assigned_tasks=1),
            DeveloperProfile("Free", open_pull_requests=0),
        ],
        "Task",
        SPEC,
    )
    assert result.recommended == "Free"
    assert [s.name for s in result.scores] == ["Free", "Busy"]
    assert result.notice is None


def test_relevant_experience_outweighs_slightly_higher_workload() -> None:
    result = recommend_developer(
        [
            DeveloperProfile("Expert", open_pull_requests=1,
                             history_texts=("Add Postgres CSV export",)),
            DeveloperProfile("Idle", open_pull_requests=0,
                             history_texts=("Fix button colour",)),
        ],
        "Invoices",
        SPEC,
    )  # fmt: skip
    assert result.recommended == "Expert"
    expert = result.scores[0]
    assert {"postgres", "csv", "export"} <= set(expert.matched_keywords)
    assert any("matching term" in line for line in expert.explanation)


def test_previous_tasks_text_counts_as_experience() -> None:
    result = recommend_developer(
        [
            DeveloperProfile("A", history_texts=("unrelated",)),
            DeveloperProfile("B", history_texts=("Earlier task: pandas reporting",)),
        ],
        "T",
        SPEC,
    )
    assert result.recommended == "B"


def test_experience_level_breaks_otherwise_equal_scores() -> None:
    result = recommend_developer(
        [
            DeveloperProfile("Junior", experience_level="junior"),
            DeveloperProfile("Senior", experience_level="Senior"),
            DeveloperProfile("Unknown"),
        ],
        "T",
        SPEC,
    )
    assert [s.name for s in result.scores] == ["Senior", "Junior", "Unknown"]
    assert "not recorded" in result.scores[2].explanation[-1]


def test_recommendation_changes_when_specification_changes() -> None:
    profiles = [
        DeveloperProfile("Data", history_texts=("Postgres migration",)),
        DeveloperProfile("Front", history_texts=("React dashboard",)),
    ]
    assert recommend_developer(profiles, "T", "Use Postgres").recommended == "Data"
    assert recommend_developer(profiles, "T", "Use React").recommended == "Front"


def test_missing_information_does_not_fail() -> None:
    result = recommend_developer(
        [DeveloperProfile("Sparse"), DeveloperProfile("Other", assigned_tasks=2)],
        "T",
        SPEC,
    )
    assert result.recommended == "Sparse"
    sparse = result.scores[0]
    assert any("no history available" in line for line in sparse.explanation)


def test_empty_developer_list_gives_notice_and_no_recommendation() -> None:
    result = recommend_developer([], "T", SPEC)
    assert result.recommended is None
    assert result.scores == ()
    assert result.notice is not None
    assert "No developers" in result.notice


def test_no_suitable_developer_gives_notice_but_still_ranks() -> None:
    # Everyone is equally loaded, with no matching history and no level.
    result = recommend_developer(
        [
            DeveloperProfile("A", open_pull_requests=2),
            DeveloperProfile("B", open_pull_requests=2),
        ],
        "T",
        SPEC,
    )
    assert result.recommended is None
    assert result.notice is not None
    assert "manually" in result.notice
    assert len(result.scores) == 2


def test_ranking_is_deterministic_and_ties_break_by_name() -> None:
    profiles = [DeveloperProfile("zoe"), DeveloperProfile("Adam")]
    first = recommend_developer(profiles, "T", SPEC)
    second = recommend_developer(list(reversed(profiles)), "T", SPEC)
    assert first == second
    assert first.recommended == "Adam"


def test_excluded_developer_is_scored_but_never_recommended() -> None:
    result = recommend_developer(
        [
            DeveloperProfile(
                "Current",
                open_pull_requests=1,
                history_texts=("Add Postgres CSV export",),
            ),
            DeveloperProfile("Other"),
        ],
        "Invoices",
        SPEC,
        exclude="Current",
    )
    assert result.recommended == "Other"
    assert {s.name for s in result.scores} == {"Current", "Other"}


def test_only_excluded_developer_means_no_recommendation() -> None:
    result = recommend_developer(
        [DeveloperProfile("Current")], "Invoices", SPEC, exclude="Current"
    )
    assert result.recommended is None
    assert result.notice
