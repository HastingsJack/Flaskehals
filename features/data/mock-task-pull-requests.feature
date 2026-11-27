Feature: Mock task pull requests

  As a developer of the PR Review Assistant
  I want every seeded task linked to a seeded pull request and listed in order
  So that the GitHub status in each task title can be shown with realistic data
  And the seeded tasks are easy to find on the Tasks page

  # Depends on mock-data-seeding.feature and task-github-status-in-title.feature.
  # Only seeded tasks and seeded pull requests are linked. Real data is not touched.

  Background:
    Given the application is configured with Neo4j connection settings
    And seeded tasks and seeded pull requests exist

  Scenario: Every seeded task has a pull request
    When I run the mock data seed
    Then each seeded task should be linked to at least one seeded pull request
    And no seeded task should show only its own status in the title

  Scenario: The seeded pull requests cover every status
    When I run the mock data seed
    Then the linked pull requests should include open, draft, merged and closed ones
    And the task titles should show each of those statuses

  Scenario: Some tasks have several pull requests
    When I run the mock data seed
    Then at least one seeded task should be linked to more than one pull request
    And its title should show the status with the pull request count

  Scenario: Tasks are listed in numerical order
    When the project manager opens the Tasks page
    Then the tasks should be listed by task number, lowest first
    And "Task-2" should be listed before "Task-10"
    And the order should not depend on when the tasks were created

  Scenario: Search keeps the numerical order
    When the project manager searches for tasks
    Then the matching tasks should still be listed by task number, lowest first

  Scenario: Real data is left alone
    When I run the mock data seed
    Then tasks and pull requests that are not seeded should not be linked or changed

  Scenario: Seeding twice does not duplicate links
    Given the mock data seed has already been run
    When I run the mock data seed again
    Then each task should still have the same number of linked pull requests
