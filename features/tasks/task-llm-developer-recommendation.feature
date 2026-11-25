Feature: AI-decided developer recommendation

  As a project manager
  I want a language model to recommend the developer for a task
  So that experience, workload and past work are weighed together with judgement

  # Supersedes the rule-based "Automatic developer assignment" scenarios in
  # task-creation-developer-assignment.feature: the model now makes the
  # decision, and the rule-based ranking is its evidence and its fallback.
  # Also applies when a task is re-assigned (task-reassignment.feature).

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the OpenRouter API is configured
    And developers exist in Neo4j

  Scenario: The language model recommends the developer
    Given a technical specification has been generated
    When the developer recommendation is evaluated
    Then the language model should choose the recommended developer
    And the recommended developer should be displayed as the default selection
    And the model's reasoning should be displayed

  Scenario: The model is given the retrieved project data
    When the developer recommendation is evaluated
    Then the model should be sent the task title and specification
    And each developer's current workload
    And each developer's experience level where recorded
    And each developer's previous pull requests and tasks
    And the rule-based score breakdown for each developer

  Scenario: The model is told which factors to weigh
    When the developer recommendation is evaluated
    Then the model should be instructed to consider relevant experience
    And current workload
    And previous completed tasks and pull requests
    And not to invent information that was not provided

  Scenario: Only a known developer can be recommended
    Given the model names a developer who does not exist in Neo4j
    When the developer recommendation is evaluated
    Then the model's answer should be rejected
    And the rule-based recommendation should be used instead
    And the project manager should be notified

  Scenario: Never recommend the excluded developer on re-assignment
    Given a task is being re-assigned from "Hans"
    And the model names "Hans"
    When the developer recommendation is evaluated
    Then the model's answer should be rejected
    And "Hans" should not be recommended

  Scenario: The model finds no suitable developer
    Given the model answers that no developer is suitable
    When the developer recommendation is evaluated
    Then no developer should be recommended
    And the project manager should be notified
    And the project manager should be able to select a developer manually

  Scenario Outline: Fall back to the rule-based recommendation
    Given <problem>
    When the developer recommendation is evaluated
    Then the rule-based recommendation should be used
    And the project manager should be told the AI recommendation was unavailable
    And the project manager should still be able to select any developer

    Examples:
      | problem                                      |
      | the OpenRouter API key is not configured     |
      | OpenRouter is unavailable or rate limited    |
      | the model answers with something unparseable |

  Scenario: Task text cannot instruct the model
    Given a task description contains instructions addressed to the model
    When the developer recommendation is evaluated
    Then the text should be sent to the model as data
    And only a developer who exists in Neo4j can be recommended

  Scenario: Show the rule-based evidence beside the decision
    Given the model has recommended a developer
    When the project manager views the recommendation
    Then the rule-based score and reasons for every developer should be viewable
    And it should be clear which part is the model's reasoning

  Scenario: Handle an empty developer list
    Given no developers exist in Neo4j
    When the developer recommendation is evaluated
    Then the model should not be called
    And the project manager should be notified
