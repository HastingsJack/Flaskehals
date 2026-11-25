Feature: Reviewer re-assignment

  As a project manager
  I want to change the reviewer recommended for a task's pull request with a button
  So that review responsibility can follow changes in workload and availability,
  and the pull request on GitHub always shows the current reviewer

  # Extends pull-request-task-assignment.feature (the stored reviewer recommendation
  # and the "reviewer:" label) and mirrors task-reassignment.feature (the developer
  # re-assign flow). As there is a single GitHub user, the reviewer is identified on
  # the pull request by the "reviewer:" label only.

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the application is configured to read and label pull requests on GitHub
    And the task "Task-1" is assigned to the developer "Hans"
    And a reviewer "Peter" has been recommended for the pull request linked to "Task-1"
    And the pull request is labelled "reviewer:Peter"

  # Initiating re-assignment

  Scenario: Offer re-assignment of the reviewer
    When the project manager views the task "Task-1"
    Then a "Re-assign reviewer" button should be displayed for the pull request

  Scenario: No reviewer re-assignment without a pull request
    Given the task "Task-2" has no linked pull request
    When the project manager views the task "Task-2"
    Then no "Re-assign reviewer" button should be displayed

  Scenario: Show current reviewer and candidate reviewers
    When the project manager chooses to re-assign the reviewer
    Then the current reviewer "Peter" should be displayed
    And a dropdown of developers should be displayed
    And the current reviewer should be indicated in the dropdown
    And the task's own developer "Hans" should not be offered

  Scenario: Default to the best alternative reviewer
    When the project manager chooses to re-assign the reviewer
    Then the highest-ranked candidate other than the current reviewer and "Hans" should be the default selection
    And the ranking should come from the deterministic reviewer scoring, not the language model

  # Performing re-assignment

  Scenario: Re-assign the reviewer and update the pull request
    Given the project manager has chosen to re-assign the reviewer
    When the project manager selects "Niels" and confirms
    Then the task should record "Niels" as the reviewer in Neo4j
    And the pull request should be labelled "reviewer:Niels"
    And the pull request should not be labelled "reviewer:Peter"
    And the pull request should have exactly one "reviewer:" label
    And the task page should display "Niels" as the reviewer

  Scenario: Leave the developer label and other labels untouched
    Given the project manager has re-assigned the reviewer to "Niels"
    Then the pull request should still be labelled "dev:Hans"
    And no label other than "reviewer:" labels should have been changed

  Scenario: Update reviewer workload after re-assignment
    Given the reviewer has been re-assigned from "Peter" to "Niels"
    Then the open review workload of "Peter" should decrease
    And the open review workload of "Niels" should increase

  Scenario: Retain reviewer history
    Given the reviewer has been re-assigned from "Peter" to "Niels"
    Then the original recommendation and its scores and reasons should be retained
    And the previous reviewer should be recorded with a timestamp
    And the new reviewer should be recorded with a timestamp

  Scenario: View reviewer history
    Given the reviewer has been re-assigned more than once
    When the project manager views the task "Task-1"
    Then the previous reviewers should be listed in chronological order

  Scenario: Manual re-assignment is not overwritten by the assignment command
    Given the reviewer has been re-assigned from "Peter" to "Niels"
    When the assignment command is run again
    Then the pull request should still be labelled "reviewer:Niels"
    And no new reviewer recommendation should be created for that pull request

  # Validation

  Scenario: Prevent re-assignment to the current reviewer
    Given the project manager has chosen to re-assign the reviewer
    When the project manager selects "Peter" and confirms
    Then no change should be made
    And the project manager should be informed that the reviewer is already assigned

  Scenario: Prevent the task's developer from reviewing their own pull request
    Given the project manager has chosen to re-assign the reviewer
    When "Hans" is submitted as the new reviewer
    Then no change should be made
    And the project manager should be informed that the developer cannot review their own task

  Scenario: Require a reviewer selection
    Given the project manager has chosen to re-assign the reviewer
    When the project manager confirms without selecting a developer
    Then the re-assignment should not be saved
    And the project manager should be asked to select a developer

  Scenario: Validate the selected reviewer
    Given the project manager has chosen to re-assign the reviewer
    When a name that is not a known developer is submitted as the new reviewer
    Then no change should be made
    And no label should be added to the pull request

  Scenario: Cancel re-assignment
    Given the project manager has chosen to re-assign the reviewer
    When the project manager cancels
    Then the reviewer should remain "Peter"
    And the pull request labels should be unchanged

  Scenario: Changing the task's developer does not change the reviewer
    Given the task "Task-1" is re-assigned from "Hans" to "Niels" using the task re-assignment
    Then the reviewer on the task and the pull request should be unchanged

  # Error handling

  Scenario: Handle GitHub failure while updating the label
    Given GitHub fails when the labels are changed
    When the project manager selects "Niels" and confirms
    Then an appropriate error should be displayed
    And the reviewer should remain "Peter" in Neo4j
    And the task should not be presented as re-assigned

  Scenario: Handle GitHub rate limit
    Given the GitHub rate limit has been reached
    When the project manager selects "Niels" and confirms
    Then the project manager should be told when GitHub can be used again
    And the reviewer should remain "Peter" in Neo4j

  Scenario: Handle database failure after the label was updated
    Given Neo4j is unavailable when the new reviewer is saved
    When the project manager selects "Niels" and confirms
    Then an appropriate error should be displayed
    And the pull request label should be restored to "reviewer:Peter" where possible
    And the task should not be presented as re-assigned

  Scenario: Handle a pull request that is no longer open
    Given the pull request linked to "Task-1" has been closed or merged
    When the project manager views the task "Task-1"
    Then no "Re-assign reviewer" button should be displayed for that pull request

  Scenario: Handle a stale view
    Given another change has made "Niels" the reviewer since the page was loaded
    When the project manager selects "Ole" and confirms
    Then no change should be made
    And the project manager should be told the reviewer has changed and to reload

  # Configuration and access

  Scenario: Fail securely when GitHub is not configured
    Given the GitHub token or repository is not configured
    When the project manager views the task "Task-1"
    Then no "Re-assign reviewer" button should be enabled
    And the missing configuration should be reported without exposing any secret

  Scenario: Use the least GitHub access needed
    When the reviewer is re-assigned
    Then the application should only read the pull request and add or remove labels
    And the application should not request reviews, merge, push code, or change repository settings
