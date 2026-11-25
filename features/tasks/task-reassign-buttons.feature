Feature: Re-assign buttons layout

  As a project manager
  I want the developer and reviewer re-assign buttons shown side by side
  So that I can find and compare both re-assign actions for a task in one place

  # Changes the existing "Re-assign" action from task-reassignment.feature and
  # sits beside the "Re-assign reviewer" button from task-reviewer-reassignment.feature.
  # Behaviour of each re-assignment flow is unchanged; only the label and placement change.

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the task "Task-1" is assigned to the developer "Hans"

  Scenario: Rename the developer re-assign button
    When the project manager views the task "Task-1"
    Then a "Re-assign developer" button should be displayed for the task
    And no button labelled just "Re-assign" should be displayed

  Scenario: Show the developer and reviewer buttons next to each other
    Given the task "Task-1" has a linked open pull request
    When the project manager views the task "Task-1"
    Then the "Re-assign developer" button should be displayed next to the "Re-assign reviewer" button

  Scenario: Show only the developer button without a pull request
    Given the task "Task-1" has no linked pull request
    When the project manager views the task "Task-1"
    Then the "Re-assign developer" button should be displayed
    And no "Re-assign reviewer" button should be displayed

  Scenario: Developer button keeps its existing behaviour
    When the project manager chooses "Re-assign developer"
    Then the developer re-assignment flow from task-reassignment.feature should start
