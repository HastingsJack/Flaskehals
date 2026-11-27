Feature: Show the GitHub status in the task title

  As a project manager
  I want each task's drop-down title to show the status of its pull request on GitHub
  So that I can see where every task stands without opening it

  # The status is derived from the pull requests already synced into Neo4j
  # (state, draft and merged_at). Showing it does not call GitHub, so the task
  # overview stays fast and works when GitHub is unavailable or rate limited.
  # Depends on task-numbers.feature, task-reassignment.feature and
  # pull-request-sync.feature.
  #
  # Status values: "Draft", "Open", "Merged", "Closed". A task without a pull
  # request shows its own status stored in Neo4j (for example "Approved"), so a
  # status is always shown and "No PR" is never displayed.
  # The status is shown at the end of the title in square brackets, for example
  # "Task-1 - Add login - Hans [Open]", using GitHub's colours as filled badges so they are easy to see:
  # Open green, Draft grey, Merged purple, Closed red, task status grey.

  Background:
    Given the project manager is authenticated
    And the application is connected to Neo4j
    And the project manager is viewing the task overview

  # Showing the status

  Scenario: The title shows the status of an open pull request
    Given the task "Task-1" has an open pull request
    Then the drop-down title of "Task-1" should show the status "Open"

  Scenario: The title shows a draft pull request
    Given the task "Task-1" has a draft pull request
    Then the drop-down title of "Task-1" should show the status "Draft"

  Scenario: The title shows a merged pull request
    Given the task "Task-1" has a merged pull request
    Then the drop-down title of "Task-1" should show the status "Merged"

  Scenario: The title shows a closed pull request
    Given the task "Task-1" has a pull request that was closed without merging
    Then the drop-down title of "Task-1" should show the status "Closed"

  Scenario: A task without a pull request shows its own status
    Given the task "Task-1" has no linked pull request
    And the task "Task-1" has the status "approved" in Neo4j
    Then the drop-down title of "Task-1" should show the status "Approved"
    And the title should not show "No PR"

  Scenario: The status is at the end of the title in square brackets
    Given the task "Task-1" is assigned to "Hans" and has an open pull request
    Then the drop-down title of "Task-1" should show "Task-1", "Hans" and then "[Open]" at the end

  Scenario: The title of an unassigned task still shows the status
    Given the task "Task-1" is unassigned and has no linked pull request
    Then the drop-down title of "Task-1" should show "unassigned" and the status "Approved"

  # Tasks with several pull requests

  Scenario: Open work takes priority over finished work
    Given the task "Task-1" has a merged pull request and an open pull request
    Then the drop-down title of "Task-1" should show the status "Open"

  Scenario: A draft is shown while no pull request is open
    Given the task "Task-1" has a draft pull request and a closed pull request
    Then the drop-down title of "Task-1" should show the status "Draft"

  Scenario: Merged takes priority over closed
    Given the task "Task-1" has a merged pull request and a closed pull request
    Then the drop-down title of "Task-1" should show the status "Merged"

  Scenario: The title shows how many pull requests the task has
    Given the task "Task-1" has two open pull requests
    Then the drop-down title of "Task-1" should show "[Open (2)]" at the end

  # Keeping the status current

  Scenario: The status follows the pull request sync
    Given the task "Task-1" has an open pull request
    And the pull request has since been merged on GitHub
    When the pull request sync is run
    And the project manager reloads the task overview
    Then the drop-down title of "Task-1" should show the status "Merged"

  # Display

  Scenario Outline: The status uses GitHub's colours
    Given the task "Task-1" has the status "<status>"
    Then the status in the title of "Task-1" should be shown in <colour>

    Examples:
      | status | colour |
      | Open   | green  |
      | Draft  | grey   |
      | Merged | purple |
      | Closed | red    |
      | Approved | grey |

  Scenario: The status is readable without relying on colour
    Then the status should be shown as text
    And any colour or icon used should only be an addition to the text

  Scenario: Status text is not taken as markup
    Given the task "Task-1" has a pull request with a title containing markup
    Then the drop-down title of "Task-1" should show only the task number, developer and status

  # Failure handling

  Scenario: The overview works without GitHub
    Given GitHub is unavailable, rate limited or not configured
    Then the drop-down titles should still show the last synced status
    And no GitHub API call should be made to render the titles

  Scenario: Neo4j has no pull request data for the task
    Given the pull requests have never been synced
    Then the drop-down title of "Task-1" should show the task's own status
    And the task overview should not fail

  # Search and paging

  Scenario: Search and paging are unchanged
    Given the title shows the GitHub status
    When the project manager searches for or pages through tasks
    Then the same tasks should be found as before
    And each task's title should still show its status
