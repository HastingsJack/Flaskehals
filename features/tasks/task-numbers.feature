Feature: Task numbers

  As a project manager
  I want every task to have a short, readable task number such as Task-1
  So that I can refer to, find, and discuss tasks without using internal identifiers

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j

  # Assigning numbers

  Scenario: Assign the first task number
    Given no tasks exist
    When the project manager approves a new task
    Then the task should be stored with the task number "Task-1"

  Scenario: Assign sequential task numbers
    Given the highest existing task number is "Task-3"
    When the project manager approves a new task
    Then the task should be stored with the task number "Task-4"

  Scenario: Task numbers are unique
    Given two tasks are approved at the same time
    Then each task should receive a different task number

  Scenario: Task numbers are not reused
    Given "Task-2" has been created
    And a later task "Task-3" exists
    When the project manager approves a new task
    Then the new task should receive "Task-4"

  Scenario: Task number is immutable
    Given a task has the task number "Task-5"
    When the task is re-assigned to a different developer
    Then the task number should still be "Task-5"

  Scenario: Task number is not part of the generated content
    When the AI generates a technical specification for a task
    Then the task number should not be generated or editable by the AI
    And the project manager should not be able to edit the task number

  # Displaying numbers

  Scenario: Show task number in the task overview
    Given tasks exist
    When the project manager views the task overview
    Then each task should display its task number
    And the task number should be shown before the task title

  Scenario: Show task number in task details
    When the project manager views a task
    Then the task number should be displayed

  Scenario: Show task number on re-assignment and history views
    When the project manager chooses to re-assign a task
    Then the task number should be displayed with the task
    And the assignment history should refer to the task by its task number

  Scenario: Show task number on the developer dashboard
    Given a developer has assigned tasks
    When the project manager views the developer's details
    Then each assigned task should be shown with its task number

  # Branch compatibility
  # Task numbers are used in branch names such as "feat/task-1", so the format
  # must be simple, unambiguous and safe to use in a Git branch name.

  Scenario: Task number format is safe for branch names
    Given a task has the task number "Task-12"
    Then the number part should be a plain positive integer
    And the task number should contain no spaces or special characters
    And the lowercase form "task-12" should be usable in a branch name

  Scenario: Task numbers are unique across the whole application
    Given tasks exist for several developers
    Then no two tasks should share the same number
    So that a number in a branch name identifies exactly one task

  Scenario: Resolve a task from a branch name
    Given the task "Task-1" exists
    When the application is given the branch name "feat/task-1"
    Then the task "Task-1" should be resolved

  Scenario Outline: Resolve a task from different branch name styles
    Given the task "Task-12" exists
    When the application is given the branch name "<branch>"
    Then the task "Task-12" should be resolved

    Examples:
      | branch             |
      | feat/task-12       |
      | fix/Task-12        |
      | feature/TASK-12    |
      | feat/task-12-login |

  Scenario Outline: Do not match a branch name without a valid task number
    When the application is given the branch name "<branch>"
    Then no task should be resolved

    Examples:
      | branch        |
      | main          |
      | feat/login    |
      | feat/task-    |
      | feat/task-0   |
      | feat/mytask-1 |

  Scenario: Branch name referring to a task that does not exist
    Given no task "Task-99" exists
    When the application is given the branch name "feat/task-99"
    Then no task should be resolved
    And no developer should be assigned

  # Existing data

  Scenario: Number existing tasks without a task number
    Given tasks exist that were created before task numbers were introduced
    When the application starts
    Then each of those tasks should receive a task number in order of creation
    And tasks that already have a task number should not be changed

  Scenario: Numbering existing tasks is repeatable
    Given all existing tasks already have task numbers
    When the application starts again
    Then no task numbers should change

  # Error handling

  Scenario: Handle database failure while assigning a number
    Given the project manager approves a task
    And Neo4j is unavailable
    When the application attempts to save the task
    Then an appropriate error should be displayed
    And no task number should be consumed or shown for the failed task

  Scenario: Task numbers have no gaps from failed saves
    Given a task save fails
    When the project manager approves a new task successfully
    Then the new task number should follow the highest stored task number
