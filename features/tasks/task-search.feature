Feature: Task search

  As a project manager
  I want to search for tasks on the Tasks page
  So that I can quickly find a specific task, for example by its task number

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the project manager is viewing the "Tasks" page

  # Search input

  Scenario: Show a search field
    Then a search field should be displayed above the task list

  Scenario: Show all tasks when the search field is empty
    Given tasks exist
    When the search field is empty
    Then all tasks should be listed

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

  # Searching by text

  Scenario: Find tasks by title
    Given a task titled "Add login page" exists
    When the project manager searches for "login"
    Then the task "Add login page" should be displayed

  Scenario: Text search is case-insensitive
    Given a task titled "Add login page" exists
    When the project manager searches for "LOGIN"
    Then the task "Add login page" should be displayed

  Scenario: Show only matching tasks
    Given several tasks exist and only some match the search
    When the project manager searches
    Then only the matching tasks should be displayed

  # Searching by assignee

  Scenario: Find tasks by assigned developer
    Given tasks are assigned to the developer "Hans"
    When the project manager searches for "Hans"
    Then the tasks assigned to "Hans" should be displayed

  # Clearing

  Scenario: Clear the search
    Given the project manager has searched for a task
    When the project manager clears the search field
    Then all tasks should be listed again

  # No results and validation

  Scenario: No matching tasks
    Given no task matches the search
    When the project manager searches
    Then the project manager should be informed that no task was found
    And the task list should be empty

  Scenario: Ignore surrounding whitespace
    Given the task "Task-7" exists
    When the project manager searches for "  Task-7  "
    Then the task "Task-7" should be displayed

  Scenario: Reject excessively long or unsafe input
    When the project manager searches for a value that is too long or contains unsafe characters
    Then the input should be validated
    And no unsafe value should be passed to the database query

  # Error handling

  Scenario: Handle database failure during search
    Given Neo4j is unavailable
    When the project manager searches for a task
    Then an appropriate error should be displayed
    And the project manager should not be shown incorrect results
