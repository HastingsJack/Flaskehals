Feature: GitHub pull request synchronisation

  As a PR Review Assistant
  I want to retrieve pull request information from GitHub
  So that I can analyse developer activity, workload and review history

  Background:
    Given a GitHub repository is configured
    And GitHub API access is configured
    And a Neo4j database is available

  # Pull request data

  Scenario: Retrieve open pull requests
    When the application synchronises with GitHub
    Then all open pull requests should be retrieved
    And each pull request should include its number, title, URL
    And each pull request should include its draft status
    And each pull request should include its creation and update timestamps

  Scenario: Retrieve pull request change statistics
    When the application synchronises with GitHub
    Then each pull request should include its lines added
    And its lines deleted
    And its number of changed files

  # Label interpretation

  Scenario: Identify the simulated developer
    Given a pull request has the label "dev:Alice"
    When the application processes the pull request
    Then Alice should be identified as the simulated developer responsible for the pull request

  Scenario: Identify the assigned reviewer
    Given a pull request has the label "reviewer:Bob"
    When the application processes the pull request
    Then Bob should be identified as the assigned reviewer

  Scenario Outline: Identify pull request priority
    Given a pull request has the label "priority:<priority>"
    When the application processes the pull request
    Then its priority should be "<priority>"

    Examples:
      | priority |
      | low      |
      | medium   |
      | high     |
      | critical |

  Scenario: Handle missing or unrecognised labels
    Given a pull request has missing or unrecognised custom labels
    When the application processes the pull request
    Then the available information should still be synchronised
    And missing or unrecognised values should not cause synchronisation to fail

  # Comments as simulated reviews

  Scenario: Retrieve pull request comments
    Given a pull request has comments
    When the application synchronises with GitHub
    Then its comments should be retrieved
    And each comment should include its author, content and timestamp

  Scenario: Interpret a comment as an approval
    Given a pull request has a comment from its assigned reviewer
    And the comment starts with "[APPROVED]"
    When the application processes the comment
    Then the comment should be recorded as an approval

  Scenario: Interpret a comment as a request for changes
    Given a pull request has a comment from its assigned reviewer
    And the comment starts with "[CHANGES_REQUESTED]"
    When the application processes the comment
    Then the comment should be recorded as a request for changes

  Scenario: Ignore comments without a review outcome
    Given a pull request has a comment without a recognised review prefix
    When the application processes the comment
    Then the comment should be stored as a general comment
    And it should not be counted as a completed review

  # Neo4j synchronisation

  Scenario: Store pull request information in Neo4j
    Given GitHub pull request data has been retrieved
    When the application synchronises with Neo4j
    Then pull request nodes should be created or updated
    And developer relationships should be created or updated
    And repository relationships should be created or updated
    And labels and comments should be associated with their pull requests

  Scenario: Avoid duplicate records during synchronisation
    Given a pull request has already been synchronised
    When the application synchronises with GitHub again
    Then existing records should be updated
    And duplicate pull requests and comments should not be created

  Scenario: Synchronise changes to existing pull requests
    Given a previously synchronised pull request has changed in GitHub
    When the application synchronises with GitHub
    Then its stored information should reflect the latest GitHub state

  # Error handling

  Scenario: Handle GitHub API failures
    Given GitHub is unavailable
    When the application attempts to synchronise
    Then the synchronisation should fail gracefully
    And the error should be reported
    And existing Neo4j data should remain available

  Scenario: Handle GitHub API rate limits
    Given the GitHub API rate limit has been reached
    When the application attempts to synchronise
    Then the rate limit response should be handled
    And the application should not continue making unrestricted requests