Feature: Task re-assignment

  As a project manager
  I want to re-assign an approved task to a different developer
  So that I can adapt to changes in workload, availability, or priorities

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And an approved task is assigned to a developer

  # Initiating re-assignment

  Scenario: Open re-assignment for an assigned task
    When the project manager views the task overview
    Then each assigned task should offer a re-assign action

  Scenario: Show current assignment and candidate developers
    When the project manager chooses to re-assign a task
    Then the currently assigned developer should be displayed
    And a dropdown of developers should be displayed
    And the currently assigned developer should be indicated in the dropdown

  Scenario: Recommend a developer for re-assignment
    Given the assignment agent can evaluate the task
    When the project manager chooses to re-assign a task
    Then the assignment agent should evaluate the stored technical specification
    And the recommendation should consider current workload, experience, and experience level
    And the task's current developer should not be recommended
    And the recommended developer should be displayed as the default selection

  # Performing re-assignment

  Scenario: Re-assign a task to another developer
    Given the project manager has chosen to re-assign a task
    When the project manager selects another developer and confirms
    Then the task should be assigned to the selected developer in Neo4j
    And the previous developer should no longer be assigned to the task
    And the task overview should display the new developer

  Scenario: Update developer workload after re-assignment
    Given a task has been re-assigned
    Then the previous developer's workload should decrease
    And the new developer's workload should increase

  Scenario: Retain assignment history
    Given a task has been re-assigned
    Then the original developer recommendation should be retained
    And the previous assignment should be recorded with a timestamp
    And the developer who made the re-assignment should be recorded

  Scenario: View assignment history
    Given a task has been re-assigned more than once
    When the project manager views the task
    Then the previous assignments should be listed in chronological order

  Scenario: Preserve the task content when re-assigning
    Given a task has been re-assigned
    Then the title, description, and approved technical specification should be unchanged

  # Validation

  Scenario: Prevent re-assignment to the same developer
    Given the project manager has chosen to re-assign a task
    When the project manager selects the currently assigned developer and confirms
    Then no change should be made
    And the project manager should be informed that the developer is already assigned

  Scenario: Require a developer selection
    Given the project manager has chosen to re-assign a task
    When the project manager confirms without selecting a developer
    Then the re-assignment should not be saved
    And the project manager should be asked to select a developer

  Scenario: Cancel re-assignment
    Given the project manager has chosen to re-assign a task
    When the project manager cancels
    Then the task should remain assigned to the original developer

  # Error handling

  Scenario: Handle unavailable developer recommendations
    Given no suitable developer can be identified
    When the project manager chooses to re-assign a task
    Then the project manager should be notified
    And the project manager should be able to select a developer manually

  Scenario: Handle database failure during re-assignment
    Given the project manager confirms a re-assignment
    And Neo4j is unavailable
    When the application attempts to save the change
    Then an appropriate error should be displayed
    And the task should remain assigned to the original developer
    And the task should not be presented as re-assigned
