Feature: Pull request task assignment and reviewer recommendation

  As a project manager
  I want a pull request opened for a task to be labelled with its developer and given a recommended reviewer
  So that ownership and review responsibility are clear without manual labelling

  # The application polls GitHub for open pull requests when the assignment
  # command is run. It does not receive webhooks, as it only runs locally.
  # Depends on task-numbers.feature (task numbers and branch name resolution),
  # task-creation-developer-assignment.feature (developer recommendation),
  # and pull-request-sync.feature (the dev: and reviewer: label convention).

  Background:
    Given the application is connected to Neo4j
    And the application is configured to read and label pull requests on GitHub
    And the task "Task-1" is assigned to the developer "Hans"

  # Finding pull requests

  Scenario: Process an open pull request for a task
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then the pull request should be linked to the task "Task-1"

  Scenario Outline: Resolve the task from different branch name styles
    Given a pull request from the branch "<branch>" is open and has not been processed
    When the assignment command is run
    Then the pull request should be linked to the task "Task-1"

    Examples:
      | branch            |
      | feat/task-1       |
      | fix/Task-1        |
      | feature/TASK-1    |
      | feat/task-1-login |

  Scenario Outline: Ignore a pull request that does not refer to a task
    Given a pull request from the branch "<branch>" is open and has not been processed
    When the assignment command is run
    Then no task should be linked
    And no label should be added to the pull request
    And no reviewer should be recommended

    Examples:
      | branch        |
      | main          |
      | feat/login    |
      | feat/mytask-1 |

  Scenario: Ignore a pull request for a task that does not exist
    Given no task "Task-99" exists
    And a pull request from the branch "feat/task-99" is open and has not been processed
    When the assignment command is run
    Then no label should be added to the pull request
    And no reviewer should be recommended

  Scenario: Ignore pull requests that are not open
    Given a pull request from the branch "feat/task-1" is closed or merged
    When the assignment command is run
    Then no label should be added to the pull request
    And no reviewer should be recommended

  Scenario: Ignore draft pull requests until they are ready for review
    Given a draft pull request from the branch "feat/task-1" is open
    When the assignment command is run
    Then no label should be added to the pull request
    And no reviewer should be recommended

  Scenario: Report what was processed
    Given several open pull requests, some for tasks and some not
    When the assignment command is run
    Then the number of pull requests labelled, skipped, and failed should be reported

  # Labelling the developer

  Scenario: Label the pull request with the assigned developer
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then the pull request should be labelled "dev:Hans"

  Scenario: Use the developer assigned at the time the pull request is opened
    Given the task "Task-1" has been re-assigned from "Hans" to "Peter"
    And a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then the pull request should be labelled "dev:Peter"
    And the pull request should not be labelled "dev:Hans"

  Scenario: Do not duplicate an existing developer label
    Given the pull request already has the label "dev:Hans"
    And a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then the pull request should have exactly one "dev:" label

  # Recommending a reviewer

  Scenario: Recommend a reviewer for the task
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then a reviewer should be recommended for the task
    And the pull request should be labelled "reviewer:" followed by the recommended reviewer
    And the reviewer is identified by the label only, as there is a single GitHub user

  Scenario: Never recommend the task's own developer as reviewer
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then the recommended reviewer should not be "Hans"

  Scenario: Reviewer ranking is deterministic
    Given the same developers, workloads, and task
    When the reviewer recommendation is evaluated twice
    Then the same ranking should be produced both times

  Scenario: Reviewer ranking considers expertise, review history, and workload
    When the reviewer recommendation is evaluated
    Then each developer's score should consider expertise relevant to the task specification
    And each developer's score should consider their previous reviews of related work
    And each developer's score should consider their current workload, including open reviews

  Scenario: The language model does not decide the ranking
    When the reviewer recommendation is evaluated
    Then the ranking should be produced without the language model
    And the language model may only be used to phrase the explanation
    And any explanation should be based on the retrieved project data

  # Recording the recommendation on the task

  Scenario: Store the reviewer recommendation on the task
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then the task "Task-1" should record the recommended reviewer in Neo4j
    And the task should be linked to the pull request

  Scenario: Store the reasoning with the recommendation
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    When the assignment command is run
    Then the task should record the score of each candidate reviewer
    And the task should record the reasons behind the recommended reviewer's score
    And the task should record when the recommendation was made

  Scenario: Show the recommended reviewer on the task
    Given a reviewer has been recommended for the task "Task-1"
    When the project manager views the task "Task-1"
    Then the recommended reviewer should be displayed
    And the pull request linked to the task should be displayed

  Scenario: Show the reasoning on the task
    Given a reviewer has been recommended for the task "Task-1"
    When the project manager views the task "Task-1"
    Then the reasoning behind the recommendation should be displayed
    And the scores of the other candidates should be viewable

  # Repeated runs

  Scenario: Process each pull request only once
    Given a pull request has already been processed for the task "Task-1"
    When the assignment command is run again
    Then no duplicate label should be added
    And the task should have only one reviewer recommendation for that pull request

  Scenario: The recommendation replaces an existing reviewer label
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    And the pull request already has the label "reviewer:Bob"
    And the recommended reviewer is "Peter"
    When the assignment command is run
    Then the pull request should be labelled "reviewer:Peter"
    And the pull request should not be labelled "reviewer:Bob"
    And the pull request should have exactly one "reviewer:" label

  Scenario: Pick up a pull request that failed on an earlier run
    Given a pull request could not be labelled on an earlier run
    When the assignment command is run again
    Then the pull request should be labelled without a new recommendation being created

  # Configuration and validation

  Scenario: Fail securely when configuration is missing
    Given the GitHub token, repository, or Neo4j settings are not configured
    When the assignment command is run
    Then the command should stop without contacting GitHub or changing anything
    And the missing configuration should be reported without exposing any secret

  Scenario: Validate data read from GitHub
    Given a pull request has a malformed branch name or label value
    When the assignment command is run
    Then that pull request should be skipped
    And no branch name or label value from GitHub should be used unvalidated

  # Error handling and access

  Scenario: Handle GitHub failure while listing pull requests
    Given GitHub is unavailable or the rate limit is reached
    When the assignment command is run
    Then the failure should be reported
    And nothing should be changed in Neo4j

  Scenario: Handle GitHub failure while labelling
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    And GitHub fails when the labels are added
    When the assignment command is run
    Then the failure should be reported for that pull request
    And the reviewer recommendation should still be stored on the task
    And the labelling should be retried on the next run

  Scenario: Handle database failure while processing
    Given a pull request from the branch "feat/task-1" is open and has not been processed
    And Neo4j is unavailable
    When the assignment command is run
    Then the failure should be reported
    And no label should be added for a recommendation that was not stored
    And the pull request should be processed on the next run

  Scenario: Continue after one pull request fails
    Given several pull requests are open and one fails
    When the assignment command is run
    Then the remaining pull requests should still be processed

  Scenario: Use the least GitHub access needed
    Then the application should only be granted permission to read pull requests and write labels
    And the application should not be able to merge, push code, or change repository settings
