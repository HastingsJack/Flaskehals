Feature: Developer merged pull request statistics

  As a user
  I want to see how many pull requests each developer has had merged
  So that I can understand their recent contribution and review activity

  Background:
    Given the application is connected to Neo4j

  Scenario: Display merged pull requests authored by a developer
    Given a developer authored pull requests that were merged
    When I open the developer dashboard
    Then the developer should show how many of their authored pull requests were merged in the last 7 days
    And how many were merged in the last 30 days

  Scenario: Display merged pull requests a developer commented on
    Given a developer wrote comments on pull requests authored by others
    And those pull requests were merged
    When I open the developer dashboard
    Then the developer should show how many such pull requests were merged in the last 7 days
    And how many were merged in the last 30 days

  Scenario: Count each pull request once
    Given a developer wrote several comments on the same merged pull request
    When I open the developer dashboard
    Then that pull request should be counted once

  Scenario: Own pull requests do not count as commented on
    Given a developer commented on a merged pull request they authored
    When I open the developer dashboard
    Then it should count as authored and merged
    But it should not count as merged and commented on

  Scenario: Only merged pull requests are counted
    Given a developer has open pull requests and pull requests closed without merging
    When I open the developer dashboard
    Then those pull requests should not be included in any merged count

  Scenario: Only pull requests merged inside the window are counted
    Given a pull request was merged more than 30 days ago
    And another was merged 10 days ago
    When I open the developer dashboard
    Then the older one should not be counted in either window
    And the other should be counted in the 30 day window only

  Scenario: Developers without merged activity
    Given a developer has no merged pull requests
    When I open the developer dashboard
    Then the developer should still be displayed
    And all merge statistics should display as zero

  Scenario: Retrieve statistics from Neo4j
    When I open the developer dashboard
    Then merge statistics should be calculated from the stored pull request data
    And the windows should be rolling periods ending now
