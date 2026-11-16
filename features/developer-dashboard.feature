Feature: Developer overview dashboard

  As a user
  I want to see an overview of all developers
  So that I can understand their current workload and activity

  Background:
    Given the application is connected to Neo4j

  Scenario: Display all developers
    Given Neo4j contains multiple developers
    When I open the developer dashboard
    Then all developers should be displayed
    And each developer should have their own row
    And each row should display the developer's configured profile picture
    And each row should display the developer's name

  Scenario: Display developer workload
    Given Neo4j contains developers with associated pull requests and tasks
    When I open the developer dashboard
    Then each developer should have their number of open pull requests displayed
    And their number of pull requests assigned for review displayed
    And their number of assigned tasks displayed

  Scenario: Display developers without assigned work
    Given a developer has no open pull requests
    And no pull requests assigned for review
    And no assigned tasks
    When I open the developer dashboard
    Then the developer should still be displayed
    And all workload counts should display as zero

  Scenario: Handle missing profile pictures
    Given a developer has no profile picture
    When I open the developer dashboard
    Then the developer should still be displayed
    And a default profile picture should be shown

  Scenario: Retrieve developer information from Neo4j
    When I open the developer dashboard
    Then developer information should be retrieved from Neo4j
    And workload counts should be calculated from the associated data
    And the dashboard should not use hardcoded developer information