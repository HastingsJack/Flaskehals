Feature: AI-assisted task creation and developer assignment

  As a project manager
  I want to describe a task and have AI generate a technical specification and recommend a developer
  So that I can create well-defined tasks and assign them efficiently

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the OpenRouter API is configured

  # Task creation

  Scenario: Open the task creation form
    When the project manager opens task creation
    Then a task creation form should be displayed
    And the form should include a task title
    And the form should include a task description
    And OpenRouter should be used for specification generation

  Scenario: Generate a technical specification
    Given the project manager has entered a task title and description
    When the project manager requests specification generation
    Then the description should be sent to OpenRouter
    And a technical specification should be generated
    And the specification should be displayed for review

  Scenario: Generate a structured technical specification
    Given the project manager has submitted a task description
    When OpenRouter generates the specification
    Then the specification should include an objective
    And functional requirements
    And relevant technical considerations
    And data requirements where applicable
    And acceptance criteria
    And relevant edge cases

  Scenario: Handle incomplete or ambiguous descriptions
    Given the project manager has submitted an incomplete or ambiguous description
    When OpenRouter generates the specification
    Then missing or unclear requirements should be identified
    And clarification should be requested where necessary

  Scenario: Handle OpenRouter failure
    Given OpenRouter is unavailable
    When the project manager requests specification generation
    Then an appropriate error should be displayed
    And the original task description should be preserved

  # Specification review and regeneration

  Scenario: Edit a generated specification
    Given a technical specification has been generated
    When the project manager edits the specification
    Then the changes should be reflected in the specification

  Scenario: Provide feedback for regeneration
    Given a technical specification has been generated
    When the project manager enters feedback
    Then the feedback should be available for regeneration

  Scenario: Regenerate a specification using feedback
    Given a technical specification has been generated
    And the project manager has provided feedback
    When the project manager requests regeneration
    Then the original task description should be sent to OpenRouter
    And the current specification should be sent to OpenRouter
    And the feedback should be sent to OpenRouter
    And an updated specification should be generated
    And the updated specification should be displayed for review

  Scenario: Regenerate without feedback
    Given a technical specification has been generated
    When the project manager requests regeneration without feedback
    Then an updated specification should be generated
    And the updated specification should be displayed for review

  # Automatic developer assignment

  Scenario: Automatically recommend a developer
    Given a technical specification has been generated
    And developers exist in Neo4j
    When the assignment agent evaluates the task
    Then a suitable developer should be recommended
    And the recommendation should consider current workload
    And previous tasks and relevant experience
    And the developer's experience level
    And the recommended developer should be displayed as the default selection

  Scenario: Consider task requirements when recommending a developer
    Given a technical specification contains technical requirements
    When the assignment agent evaluates the task
    Then the developer's relevant experience should be compared against the task requirements
    And the recommendation should reflect the relevance of that experience

  Scenario: Re-evaluate developer assignment after specification regeneration
    Given a developer has already been recommended
    When the technical specification is regenerated
    Then the assignment agent should evaluate the updated requirements
    And the developer recommendation should be updated where appropriate

  Scenario: Allow the project manager to override the recommendation
    Given the assignment agent has recommended a developer
    When the project manager selects another developer from the dropdown
    Then the selected developer should replace the recommendation
    And the selected developer should be assigned when the task is accepted

  Scenario: Handle unavailable developer recommendations
    Given no suitable developer can be identified
    When the assignment agent evaluates the task
    Then the project manager should be notified
    And the project manager should be able to select a developer manually

  Scenario: Handle missing developer information
    Given a developer has incomplete workload or experience information
    When the assignment agent evaluates the task
    Then available information should still be considered
    And missing information should not cause assignment to fail

  Scenario: Handle an empty developer list
    Given no developers exist in Neo4j
    When the assignment agent evaluates the task
    Then the project manager should be notified
    And no developer should be automatically assigned

  # Task approval and persistence

  Scenario: Accept a specification and developer assignment
    Given a technical specification has been generated or edited
    And a developer has been recommended or manually selected
    When the project manager accepts the task
    Then the task should be saved as approved in Neo4j
    And the approved technical specification should be stored
    And the original task description should be stored
    And the final assigned developer should be stored
    And the original developer recommendation should be retained
    And the task should be available in the application

  Scenario: Reject a generated task
    Given a technical specification has been generated
    When the project manager rejects the task
    Then the task should not be saved as an approved task
    And the original task description should remain available

  Scenario: Retrieve previously created tasks
    Given an approved task exists
    When the project manager views the task overview
    Then the task should be displayed with its title and description
    And its technical specification should be available
    And its assigned developer should be displayed

  # Error handling

  Scenario: Handle database failure during task approval
    Given the project manager accepts a task
    And Neo4j is unavailable
    When the application attempts to save the task
    Then an appropriate error should be displayed
    And the task should not be presented as successfully saved