Feature: Mock data seeding

  As a developer of the PR Review Assistant
  I want a repeatable way to load realistic mock data into Neo4j
  So that every developer appears on the dashboard with meaningful statistics

  Background:
    Given the application is configured with Neo4j connection settings

  Scenario: Seed all developers
    Given a developer profile picture exists for Hans, Karen, Niels, Ole and Peter
    When I run the mock data seed
    Then Neo4j should contain a developer for each of them
    And each developer should reference their configured profile picture

  Scenario: Seed merged pull requests with a spread of dates
    When I run the mock data seed
    Then Neo4j should contain merged pull requests authored by each developer
    And merge dates should fall within the last 7 days, between 8 and 30 days ago, and older than 30 days
    So that the 7 day and 30 day statistics differ between developers

  Scenario: Seed pull requests that must not be counted as merged
    When I run the mock data seed
    Then Neo4j should contain open pull requests
    And pull requests closed without being merged
    And neither should contribute to any merged count

  Scenario: Seed review comments
    When I run the mock data seed
    Then merged pull requests should have comments written by developers other than the author
    And at least one developer should have several comments on the same pull request
    And at least one developer should have commented on their own pull request

  Scenario: Seed workload for the dashboard
    When I run the mock data seed
    Then some developers should have open pull requests
    And some should be assigned for review
    And some should have approved tasks assigned
    And every developer should have at least some merged pull request activity

  Scenario: Seed data follows the real data model
    When I run the mock data seed
    Then pull requests, comments, labels and repositories should use the same labels, properties and relationships as the GitHub sync
    And comments should be attributed to the reviewer through the WROTE relationship

  Scenario: Seeding is repeatable
    Given the mock data seed has already been run
    When I run it again
    Then no duplicate nodes or relationships should be created
    And dates should be recalculated relative to now so the windows stay meaningful

  Scenario: Seeded data is identifiable and removable
    Given the mock data seed has been run
    When I run the seed cleanup
    Then only seeded nodes should be removed
    And data from the real GitHub sync should remain untouched

  Scenario: Seeded data does not clash with the GitHub sync
    Given mock pull requests exist in Neo4j
    When the GitHub sync runs
    Then synced pull requests should be written as usual
    And mock pull requests should not be modified or deleted by the sync

  Scenario: Seed fails securely without configuration
    Given the Neo4j connection settings are missing
    When I run the mock data seed
    Then it should stop with a clear error
    And no data should be written

  Scenario: Seed refuses to run against an unintended database
    Given the target database already contains real synced data
    When I run the mock data seed without explicitly confirming
    Then it should not write anything
