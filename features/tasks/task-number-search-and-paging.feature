Feature: Task search by number and task list paging

  As a project manager
  I want to find tasks by their task number and browse long task lists page by page
  So that I can reach any task quickly, whether I know its number or not

  # Depends on task-numbers.feature (task numbers) and task-search.feature (text search).

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the project manager is viewing the "Tasks" page

  # Searching by task number

  Scenario: Find a task by its task number
    Given the task "Task-7" exists
    When the project manager searches for "Task-7"
    Then the task "Task-7" should be displayed

  Scenario: Find a task by task number case-insensitively
    Given the task "Task-7" exists
    When the project manager searches for "task-7"
    Then the task "Task-7" should be displayed

  Scenario: Find a task by the number alone
    Given the task "Task-7" exists
    When the project manager searches for "7"
    Then the task "Task-7" should be displayed

  Scenario: A task number search matches exactly
    Given the tasks "Task-1" and "Task-12" exist
    When the project manager searches for "Task-1"
    Then only the task "Task-1" should be displayed

  Scenario: Search for a task number that does not exist
    Given no task "Task-99" exists
    When the project manager searches for "Task-99"
    Then the project manager should be informed that no task was found

  # Paging

  Scenario: Show the task list in pages
    Given more tasks exist than fit on one page
    When the project manager views the task overview
    Then only the first page of tasks should be displayed
    And controls to move between pages should be displayed

  Scenario: Navigate between pages
    Given more tasks exist than fit on one page
    When the project manager moves to the next page
    Then the next tasks in the list should be displayed
    And the current page should be indicated

  Scenario: No paging controls for a short list
    Given fewer tasks exist than fit on one page
    Then no paging controls should be displayed

  # Interaction between search and paging

  Scenario: Search covers all tasks, not just the current page
    Given more tasks exist than fit on one page
    And a matching task is not on the current page
    When the project manager searches for it
    Then the matching task should be displayed

  Scenario: Return to the first page when searching
    Given the project manager is on a later page of the task list
    When the project manager searches
    Then the first page of results should be shown

  Scenario: Page the search results
    Given more tasks match the search than fit on one page
    When the project manager searches
    Then only the first page of matching tasks should be displayed
    And controls to move between pages of results should be displayed

  Scenario: Clearing the search returns to the full list
    Given the project manager has searched for a task
    When the project manager clears the search field
    Then the first page of all tasks should be displayed
