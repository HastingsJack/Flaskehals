"""Deterministic, explainable developer recommendation for a task.

Pure functions with no I/O and no LLM: the same inputs always give the same
ranking, and every score comes with the facts behind it.

Score (0-100) = workload + relevance + experience level, where each factor is
a 0-1 value multiplied by its weight:

- workload (40): 1 - load / highest load among developers, where load is open
  authored PRs + PRs assigned for review + approved tasks. No load = 1.
- relevance (40): keywords of the task title and specification found in the
  developer's history (authored and reviewed PR titles and labels, titles and
  specifications of previously assigned tasks), divided by the highest match
  count among developers. No match = 0.
- experience level (20): junior 0.25, mid 0.5, senior 1. Not recorded = 0.

Missing information never raises: that factor simply contributes 0 and the
explanation says so. A developer is only recommended when their score is
above 0; otherwise the project manager chooses manually.
"""

import re
from dataclasses import dataclass, field

WORKLOAD_WEIGHT = 40
RELEVANCE_WEIGHT = 40
EXPERIENCE_WEIGHT = 20

EXPERIENCE_LEVELS: dict[str, float] = {"junior": 0.25, "mid": 0.5, "senior": 1.0}

MIN_KEYWORD_LENGTH = 3
MAX_MATCHES_SHOWN = 8
_TOKEN = re.compile(r"[a-z0-9]+")

# Generic words (and the specification's own section headings) say nothing
# about technical experience, so they are never matched.
STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "will",
        "would",
        "should",
        "must",
        "can",
        "able",
        "not",
        "but",
        "all",
        "any",
        "each",
        "when",
        "then",
        "than",
        "into",
        "onto",
        "over",
        "under",
        "about",
        "after",
        "before",
        "also",
        "such",
        "only",
        "both",
        "has",
        "have",
        "had",
        "its",
        "their",
        "there",
        "which",
        "while",
        "where",
        "who",
        "what",
        "how",
        "why",
        "use",
        "used",
        "using",
        "user",
        "users",
        "new",
        "add",
        "adds",
        "adding",
        "via",
        "per",
        "objective",
        "functional",
        "requirements",
        "requirement",
        "technical",
        "considerations",
        "consideration",
        "data",
        "acceptance",
        "criteria",
        "edge",
        "cases",
        "case",
        "open",
        "questions",
        "question",
        "none",
        "applicable",
        "task",
        "tasks",
        "feature",
    ]
)


@dataclass(frozen=True)
class DeveloperProfile:
    """What Neo4j knows about a developer. Missing information stays empty."""

    name: str
    open_pull_requests: int = 0
    review_assignments: int = 0
    assigned_tasks: int = 0
    experience_level: str | None = None
    history_texts: tuple[str, ...] = ()

    @property
    def workload(self) -> int:
        return self.open_pull_requests + self.review_assignments + self.assigned_tasks


@dataclass(frozen=True)
class DeveloperScore:
    name: str
    total: float
    matched_keywords: tuple[str, ...] = ()
    explanation: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class AssignmentResult:
    scores: tuple[DeveloperScore, ...]
    recommended: str | None
    notice: str | None = None


def extract_keywords(text: str) -> frozenset[str]:
    """Lowercase alphanumeric words that could indicate technical experience."""
    return frozenset(
        word
        for word in _TOKEN.findall(text.lower())
        if len(word) >= MIN_KEYWORD_LENGTH and word not in STOPWORDS
    )


def recommend_developer(
    profiles: list[DeveloperProfile],
    title: str,
    specification: str,
    exclude: str | None = None,
) -> AssignmentResult:
    """Rank developers for a task and recommend the best suitable one.

    ``exclude`` (the current assignee when re-assigning) is still scored and
    shown, but is never the recommendation.
    """
    if not profiles:
        return AssignmentResult(
            scores=(),
            recommended=None,
            notice="No developers exist in Neo4j, so no developer was recommended.",
        )

    task_keywords = extract_keywords(f"{title}\n{specification}")
    matches = {
        profile.name: sorted(
            task_keywords & extract_keywords("\n".join(profile.history_texts))
        )
        for profile in profiles
    }
    max_load = max(profile.workload for profile in profiles)
    max_matches = max(len(found) for found in matches.values())

    scores = sorted(
        (
            _score(profile, matches[profile.name], max_load, max_matches)
            for profile in profiles
        ),
        key=lambda score: (-score.total, score.name.lower(), score.name),
    )
    best = next((score for score in scores if score.name != exclude), None)
    if best is None or best.total <= 0:
        return AssignmentResult(
            scores=tuple(scores),
            recommended=None,
            notice=(
                "No suitable developer could be identified from the available "
                "data. Please select a developer manually."
            ),
        )
    return AssignmentResult(scores=tuple(scores), recommended=best.name)


def _score(
    profile: DeveloperProfile,
    matched: list[str],
    max_load: int,
    max_matches: int,
) -> DeveloperScore:
    workload = 1.0 - profile.workload / max_load if max_load else 1.0
    relevance = len(matched) / max_matches if max_matches else 0.0
    level = (profile.experience_level or "").strip().lower()
    experience = EXPERIENCE_LEVELS.get(level, 0.0)

    workload_points = workload * WORKLOAD_WEIGHT
    relevance_points = relevance * RELEVANCE_WEIGHT
    experience_points = experience * EXPERIENCE_WEIGHT

    explanation = [
        (
            f"Workload: {profile.workload} item(s) "
            f"({profile.open_pull_requests} open PR(s), "
            f"{profile.review_assignments} for review, "
            f"{profile.assigned_tasks} task(s)) "
            f"-> {workload_points:.1f}/{WORKLOAD_WEIGHT}"
        ),
    ]
    if matched:
        shown = ", ".join(matched[:MAX_MATCHES_SHOWN])
        more = len(matched) - MAX_MATCHES_SHOWN
        suffix = f" (+{more} more)" if more > 0 else ""
        explanation.append(
            f"Relevant experience: {len(matched)} matching term(s) "
            f"[{shown}{suffix}] -> {relevance_points:.1f}/{RELEVANCE_WEIGHT}"
        )
    elif profile.history_texts:
        explanation.append(
            f"Relevant experience: no matching terms -> 0/{RELEVANCE_WEIGHT}"
        )
    else:
        explanation.append(
            f"Relevant experience: no history available -> 0/{RELEVANCE_WEIGHT}"
        )
    if experience:
        explanation.append(
            f"Experience level: {level} -> {experience_points:.1f}/{EXPERIENCE_WEIGHT}"
        )
    else:
        explanation.append(f"Experience level: not recorded -> 0/{EXPERIENCE_WEIGHT}")

    return DeveloperScore(
        name=profile.name,
        total=workload_points + relevance_points + experience_points,
        matched_keywords=tuple(matched),
        explanation=tuple(explanation),
    )
