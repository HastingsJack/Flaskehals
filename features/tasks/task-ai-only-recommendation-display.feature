Feature: Show only the AI response for developer and reviewer recommendations

  As a project manager
  I want to see only the AI's recommendation and reasoning
  So that the page is not cluttered with rule-based score breakdowns

  # Supersedes the scenarios that require the rule-based scores to be viewable:
  # - "Show the rule-based evidence beside the decision" in
  #   task-llm-developer-recommendation.feature
  # - "Show the reasoning on the task" in
  #   pull-request-llm-reviewer-recommendation.feature
  #   ("the scores of the other candidates should be viewable")
  # The rule-based scores are still computed and sent to the model as evidence,
  # and are still the fallback. They are only no longer displayed.

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the OpenRouter API is configured

  # Developer recommendation

  Scenario: Show only the AI response for a recommended developer
    Given the model has recommended a developer for a task
    When the project manager views the developer recommendation
    Then the recommended developer should be displayed
    And the model's reasoning should be displayed
    And no "How the developer recommendation was scored" dropdown should be displayed
    And no rule-based score or score explanation should be displayed

  Scenario: Show the AI response when re-assigning a task
    Given the project manager opens the re-assignment of a task
    When the model has recommended a developer
    Then the recommended developer and the model's reasoning should be displayed
    And no "How the developer recommendation was scored" dropdown should be displayed

  Scenario: The developer dropdown still lists every developer
    Given the model has recommended a developer
    When the project manager views the developer selection
    Then every developer should still be selectable
    And the recommended developer should be the default selection

  # Reviewer recommendation

  Scenario: Show only the AI response for a recommended reviewer
    Given the model has recommended a reviewer for a pull request
    When the project manager views the task
    Then the recommended reviewer should be displayed
    And the model's reasoning should be displayed
    And no "How the reviewer recommendation was scored" dropdown should be displayed
    And no rule-based score or score explanation should be displayed

  Scenario: Show the AI response when re-assigning a reviewer
    Given the project manager opens the re-assignment of a reviewer
    When the model has recommended a reviewer
    Then the recommended reviewer and the model's reasoning should be displayed
    And no "How the reviewer recommendation was scored" dropdown should be displayed

  Scenario: The reviewer dropdown still lists every eligible developer
    Given the model has recommended a reviewer
    When the project manager views the reviewer selection
    Then every developer except the task's developer should still be selectable
    And the recommended reviewer should be the default selection

  # When there is no AI response

  Scenario Outline: No AI response is available
    Given <problem>
    When the project manager views the <role> recommendation
    Then the rule-based recommendation should still be used
    And the project manager should be told the AI recommendation was unavailable
    And no score breakdown should be displayed
    And the project manager should still be able to select any eligible developer

    Examples:
      | problem                                      | role      |
      | the OpenRouter API key is not configured     | developer |
      | OpenRouter is unavailable or rate limited    | developer |
      | the model answers with something unparseable | developer |
      | the OpenRouter API key is not configured     | reviewer  |
      | OpenRouter is unavailable or rate limited    | reviewer  |
      | the model answers with something unparseable | reviewer  |

  Scenario: Show the stored AI reasoning for an earlier recommendation
    Given a reviewer was recommended earlier by the model
    When the project manager views the task
    Then the recommended reviewer and the stored reasoning should be displayed
    And no score breakdown should be displayed

  Scenario: Show an earlier recommendation made without the model
    Given a reviewer was recommended earlier without the model
    When the project manager views the task
    Then the recommended reviewer should be displayed
    And the notice that the AI recommendation was unavailable should be displayed
    And no score breakdown should be displayed

  # Scope

  Scenario: The scores are still used behind the scenes
    When a developer or reviewer recommendation is evaluated
    Then the rule-based scores should still be computed
    And the rule-based scores should still be sent to the model as evidence
    And the rule-based scores should still be stored with the recommendation
