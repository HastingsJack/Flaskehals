Feature: Keep GitHub developer labels in step with task re-assignment

  As a project manager
  I want re-assigning a task to update the "dev:" label on its pull requests
  So that GitHub, the sync and the task overview all show the same developer

  # Today a task re-assignment only changes Neo4j. The pull request keeps its old
  # "dev:" label, and flaskehals-sync keeps recording the old developer as the
  # author. This feature closes that gap, the same way task-reviewer-reassignment
  # does for the "reviewer:" label.
  #
  # The update happens when the project manager confirms the re-assignment, by
  # calling the GitHub API. It does not use a webhook: webhooks are sent by
  # GitHub to the application, and the application only runs locally.
  # Depends on task-reassignment.feature, task-reviewer-reassignment.feature,
  # and pull-request-sync.feature (the dev: and reviewer: label convention).

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the application is configured to read and label pull requests on GitHub
    And the task "Task-1" is assigned to the developer "Hans"
    And the task "Task-1" has an open pull request labelled "dev:Hans" and "reviewer:Peter"

  # Updating the labels

  Scenario: Re-assigning a task updates the developer label
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the pull request should be labelled "dev:Maria"
    And the pull request should not be labelled "dev:Hans"
    And the pull request should have exactly one "dev:" label
    And the task "Task-1" should be assigned to "Maria"

  Scenario: Only the developer label is changed
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the pull request should still be labelled "reviewer:Peter"
    And every other label on the pull request should be unchanged

  Scenario: Update every open pull request of the task
    Given the task "Task-1" has two open pull requests
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then both pull requests should be labelled "dev:Maria"
    And neither should be labelled "dev:Hans"

  Scenario: Leave closed and merged pull requests alone
    Given the task "Task-1" also has a merged pull request labelled "dev:Hans"
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the merged pull request should still be labelled "dev:Hans"

  Scenario: A task without a pull request is re-assigned as before
    Given the task "Task-1" has no linked pull request
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the task "Task-1" should be assigned to "Maria"
    And GitHub should not be contacted

  Scenario: The button click triggers the update
    When the project manager confirms the re-assignment
    Then the labels should be changed by the application calling the GitHub API
    And no webhook should be required

  # Keeping Neo4j in step

  Scenario: Update the stored developer on the pull request
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the pull request should be recorded in Neo4j as authored by "Maria"
    And the stored reviewer recommendation should record "Maria" as the developer
    And workload should count the pull request for "Maria" and not for "Hans"

  Scenario: The next sync agrees with the re-assignment
    Given the project manager has re-assigned the task "Task-1" to "Maria"
    When the pull request sync is run
    Then the pull request should still be recorded as authored by "Maria"

  Scenario: Keep the reviewer when the new developer is the reviewer
    When the project manager re-assigns the task "Task-1" to "Peter" and confirms
    Then the pull request should be labelled "dev:Peter"
    And the pull request should still be labelled "reviewer:Peter"
    And the re-assignment should not be blocked

  # Recommending the new developer

  Scenario: The AI is nudged away from a developer who would review their own code
    Given the project manager opens the re-assignment of the task "Task-1"
    When the developer recommendation is evaluated
    Then the model should be told who reviews the task's open pull requests
    And the model should be instructed to prefer a developer who is not reviewing the task's own code
    And this should be guidance in the prompt only
    And no developer should be excluded or blocked because of it

  Scenario: The project manager can still choose the reviewer
    Given the AI recommended a developer who is not the reviewer
    When the project manager selects the reviewer as the new developer
    Then the selected developer should be assigned when the re-assignment is confirmed

  # Failure handling

  Scenario: GitHub is not configured
    Given no GitHub token is configured
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the task "Task-1" should be assigned to "Maria" in Neo4j
    And the project manager should be told the pull request labels were not updated

  Scenario: GitHub fails while changing the labels
    Given GitHub is unavailable or the rate limit is reached
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then an appropriate error should be displayed
    And the task "Task-1" should still be assigned to "Hans"
    And the pull request labels should be as they were

  Scenario: GitHub fails after some pull requests were changed
    Given the task "Task-1" has two open pull requests
    And GitHub fails on the second one
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the labels already changed should be restored on a best-effort basis
    And the task "Task-1" should still be assigned to "Hans"

  Scenario: Neo4j fails after the labels were changed
    Given Neo4j fails when the re-assignment is saved
    When the project manager re-assigns the task "Task-1" to "Maria" and confirms
    Then the labels should be restored on a best-effort basis
    And an appropriate error should be displayed
    And the task "Task-1" should still be assigned to "Hans"

  Scenario: The task changed since the project manager opened the re-assignment
    Given the task "Task-1" has since been assigned to "Peter" by someone else
    When the project manager confirms the re-assignment
    Then nothing should be changed on GitHub
    And the project manager should be asked to reload

  Scenario: Use the least GitHub access needed
    Then the application should only read pull requests and add or remove labels
    And it should not be able to merge, push code, or change repository settings
