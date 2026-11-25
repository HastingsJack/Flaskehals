Feature: AI-decided reviewer recommendation

  As a project manager
  I want a language model to recommend the reviewer for a pull request
  So that expertise, review history and workload are weighed together with judgement

  # Supersedes the scenarios "Reviewer ranking is deterministic" and "The
  # language model does not decide the ranking" in
  # pull-request-task-assignment.feature. The model decides; the rule-based
  # ranking is its evidence and its fallback. Also applies when the project
  # manager re-assigns a reviewer (task-reviewer-reassignment.feature).

  Background:
    Given the application is connected to Neo4j
    And the application is configured to read and label pull requests on GitHub
    And the OpenRouter API is configured
    And the task "Task-1" is assigned to the developer "Hans"
    And a pull request from the branch "feat/task-1" is open and has not been processed

  Scenario: The language model recommends the reviewer
    When the assignment command is run
    Then the language model should choose the recommended reviewer
    And the pull request should be labelled "reviewer:" followed by that reviewer

  Scenario: The model is given the retrieved project data
    When the assignment command is run
    Then the model should be sent the task title and specification
    And each developer's current workload, including open reviews
    And each developer's experience level where recorded
    And each developer's previous pull requests, reviews and tasks
    And the rule-based score breakdown for each developer

  Scenario: The model is told which factors to weigh
    When the assignment command is run
    Then the model should be instructed to consider expertise relevant to the task
    And previous reviews of related work
    And current workload
    And that the task's own developer must not review the pull request

  Scenario: Never recommend the task's own developer as reviewer
    Given the model names "Hans"
    When the assignment command is run
    Then the model's answer should be rejected
    And the recommended reviewer should not be "Hans"

  Scenario: Only a known developer can be recommended
    Given the model names a developer who does not exist in Neo4j
    When the assignment command is run
    Then the model's answer should be rejected
    And the rule-based reviewer should be used instead

  Scenario: The model finds no suitable reviewer
    Given the model answers that no developer is suitable
    When the assignment command is run
    Then no reviewer label should be added
    And the task should record that no suitable reviewer was found

  Scenario Outline: Fall back to the rule-based reviewer
    Given <problem>
    When the assignment command is run
    Then the rule-based reviewer should be recommended
    And the stored recommendation should say the AI recommendation was unavailable
    And the pull request should still be processed

    Examples:
      | problem                                      |
      | the OpenRouter API key is not configured     |
      | OpenRouter is unavailable or rate limited    |
      | the model answers with something unparseable |

  Scenario: Store the model's reasoning with the recommendation
    When the assignment command is run
    Then the task should record the model's reasoning
    And the task should record the rule-based score of each candidate
    And the task should record when the recommendation was made

  Scenario: Show the reasoning on the task
    Given a reviewer has been recommended for the task "Task-1"
    When the project manager views the task "Task-1"
    Then the model's reasoning should be displayed
    And the scores of the other candidates should be viewable

  Scenario: Recommend a reviewer when re-assigning
    Given the project manager re-assigns the reviewer of the pull request
    When the re-assignment is opened
    Then the model should recommend a reviewer using today's workload
    And the recommended reviewer should be the default selection
    And the current reviewer and the task's developer should not be the default

  Scenario: Do not ask the model again for a processed pull request
    Given the pull request has already been processed
    When the assignment command is run again
    Then the model should not be called
    And no second recommendation should be stored

  Scenario: Task text cannot instruct the model
    Given the task specification contains instructions addressed to the model
    When the assignment command is run
    Then the text should be sent to the model as data
    And only a developer who exists in Neo4j other than "Hans" can be recommended
