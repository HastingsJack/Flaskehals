Feature: Developer graph details drop-down

  As a user
  I want to expand a developer on the dashboard with a clickable arrow
  So that I can see the developer's nodes and relationships stored in Neo4j

  Background:
    Given the application is connected to Neo4j
    And Neo4j contains developers with related pull requests and tasks

  Scenario: Show an expand arrow on each developer row
    When I open the developer dashboard
    Then each developer row should display a drop-down arrow
    And all developer rows should be collapsed by default

  Scenario: Expand a developer to see a graph of nodes and relationships
    Given I am on the developer dashboard
    When I click the drop-down arrow for a developer
    Then the developer's details should be expanded
    And the arrow should indicate the expanded state
    And a graph visualisation similar to the Neo4j Browser should be displayed
    And the developer should be shown as a node at the centre of the graph
    And each connected node should be shown as a circle labelled with its node label and name or title
    And each relationship should be shown as a directed arrow between nodes
    And each relationship arrow should display its relationship type

  Scenario: Distinguish node types visually
    Given a developer is connected to pull requests, tasks, and labels
    When I expand that developer
    Then nodes with the same label should share the same colour
    And nodes with different labels should have different colours
    And a legend should list each node label and relationship type shown

  Scenario: Inspect node properties
    Given a developer is expanded and the graph is displayed
    When I select a node in the graph
    Then the node's label and all of its properties should be displayed

  Scenario: Display relationships grouped by type
    Given a developer has authored pull requests, is assigned pull requests for review, and is assigned tasks
    When I expand that developer
    Then the graph should include AUTHORED, ASSIGNED_TO_REVIEW, and ASSIGNED_TO relationships where present
    And RECOMMENDED relationships should not be displayed
    And the number of nodes for each relationship type should be displayed

  Scenario: Show nodes connected to the developer's pull requests
    Given a developer has authored a pull request that has labels
    When I expand that developer
    Then the graph should also show the pull request's Label nodes
    And their HAS_LABEL relationships should be displayed
    And no Repository nodes or IN_REPOSITORY relationships should be displayed

  Scenario: Show the graph details consistent with workload counts
    Given a developer has open pull requests, review assignments, and assigned tasks
    When I expand that developer
    Then the number of connected nodes shown should match the workload counts on the dashboard row

  Scenario: Collapse an expanded developer
    Given a developer is expanded
    When I click the drop-down arrow again
    Then the developer's details should be hidden
    And the arrow should indicate the collapsed state

  Scenario: Expand multiple developers independently
    Given I have expanded one developer
    When I expand a second developer
    Then both developers' details should be visible
    And collapsing one developer should not affect the other

  Scenario: Developer without any relationships
    Given a developer has no relationships in Neo4j
    When I expand that developer
    Then the graph should display only the developer's own node
    And a message should state that the developer has no connected nodes

  Scenario: Retrieve graph details from Neo4j
    When I expand a developer
    Then the nodes and relationships should be retrieved from Neo4j
    And the graph details should not use hardcoded data

  Scenario: Handle a Neo4j failure when expanding
    Given Neo4j is unavailable when I expand a developer
    When I click the drop-down arrow
    Then an error message should be displayed within the expanded section
    And the rest of the dashboard should remain usable
    And no credentials or internal error details should be exposed
