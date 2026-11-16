"""Specification generation scenarios from features/task-creation-developer-assignment.feature."""

import json
from collections.abc import Callable

import httpx
import pytest

from flaskehals.specification import (
    DEFAULT_MODEL,
    SECTIONS,
    OpenRouterConfig,
    SpecificationError,
    build_messages,
    generate_specification,
    load_openrouter_config,
    validate_task_input,
)

CONFIG = OpenRouterConfig(api_key="sk-test", base_url="https://example.test/api/v1")


def client_with(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_generate_sends_description_and_returns_specification() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok("  ## Objective\nDo it  ")

    spec = generate_specification(
        CONFIG, "Title", "Add CSV export", client=client_with(handler)
    )
    assert spec == "## Objective\nDo it"
    request = seen[0]
    assert str(request.url) == "https://example.test/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == DEFAULT_MODEL
    assert "Add CSV export" in body["messages"][1]["content"]


def test_system_prompt_requires_every_structured_section() -> None:
    system = build_messages("T", "D")[0]["content"]
    for section in SECTIONS:
        assert f"## {section}" in system
    assert "Open questions" in system
    assert "Do not invent" in system


def test_regeneration_sends_original_description_current_spec_and_feedback() -> None:
    user = build_messages("T", "original text", "edited spec", "add rate limiting")[1][
        "content"
    ]
    assert "original text" in user
    assert "edited spec" in user
    assert "add rate limiting" in user


def test_regeneration_without_feedback_omits_feedback_block() -> None:
    user = build_messages("T", "original text", "edited spec", "  ")[1]["content"]
    assert "original text" in user
    assert "edited spec" in user
    assert "<feedback>" not in user


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(429), "rate limited"),
        (httpx.Response(401), "API key"),
        (httpx.Response(500), "error \\(500\\)"),
        (httpx.Response(200, text="not json"), "unexpected"),
        (httpx.Response(200, json={"choices": []}), "unexpected"),
        (
            httpx.Response(200, json={"choices": [{"message": {"content": " "}}]}),
            "empty",
        ),
    ],
)
def test_service_failures_raise_specification_error(
    response: httpx.Response, message: str
) -> None:
    with pytest.raises(SpecificationError, match=message):
        generate_specification(
            CONFIG, "T", "D", client=client_with(lambda request: response)
        )


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")]
)
def test_network_failures_raise_specification_error(error: httpx.HTTPError) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(SpecificationError):
        generate_specification(CONFIG, "T", "D", client=client_with(handler))


def test_error_messages_never_contain_the_api_key() -> None:
    with pytest.raises(SpecificationError) as info:
        generate_specification(
            CONFIG, "T", "D", client=client_with(lambda r: httpx.Response(401))
        )
    assert "sk-test" not in str(info.value)


def test_config_requires_api_key() -> None:
    assert load_openrouter_config({}) is None
    assert load_openrouter_config({"OPENROUTER_API_KEY": "  "}) is None


def test_config_defaults_and_overrides() -> None:
    config = load_openrouter_config({"OPENROUTER_API_KEY": "k"})
    assert config == OpenRouterConfig("k")
    config = load_openrouter_config(
        {
            "OPENROUTER_API_KEY": "k",
            "OPENROUTER_MODEL": "other/model",
            "OPENROUTER_BASE_URL": "https://proxy.test/v1/",
        }
    )
    assert config == OpenRouterConfig("k", "other/model", "https://proxy.test/v1")


def test_config_rejects_non_https_base_url() -> None:
    env = {"OPENROUTER_API_KEY": "k", "OPENROUTER_BASE_URL": "http://insecure.test"}
    assert load_openrouter_config(env) is None


@pytest.mark.parametrize(
    ("title", "description", "problem"),
    [
        ("", "d", "title"),
        ("t", "   ", "description"),
        ("x" * 201, "d", "title"),
        ("t", "x" * 10_001, "description"),
    ],
)
def test_validate_task_input_rejects_bad_input(
    title: str, description: str, problem: str
) -> None:
    result = validate_task_input(title, description)
    assert result is not None
    assert problem in result


def test_validate_task_input_accepts_good_input() -> None:
    assert validate_task_input("Title", "Description") is None
