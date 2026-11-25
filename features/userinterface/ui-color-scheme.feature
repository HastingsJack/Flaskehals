Feature: UI Color Scheme

  As a user of the PR Review Assistant
  I want the UI to use a consistent blue and white color scheme
  So that the application looks cohesive and is easy to read.

  Background:
    Given the application is running

  Scenario: Apply the color scheme on the login page
    Given I have not authenticated
    When I open the application
    Then the login page should use the blue and white color scheme

  Scenario: Apply the color scheme on all pages
    Given I am authenticated
    When I navigate between the dashboard, task creation, and pull request pages
    Then every page should use the blue and white color scheme

  Scenario: Use a soft blue gradient for the main background
    Given I am viewing any page
    Then the main background should be a diagonal gradient from white to light blue
    And the gradient should stay fixed while the page scrolls

  Scenario: Use light blue for secondary backgrounds
    Given I am viewing any page
    Then the secondary background, such as the sidebar and cards, should be light blue

  Scenario: Keep text readable across the whole gradient
    Given I am viewing any page
    Then dark text should meet a minimum contrast ratio of 4.5:1
    And this applies to every color stop of the background gradient

  Scenario: Fall back to a flat background
    Given the gradient styling cannot be applied
    Then the main background should be the flat white from the theme configuration
    And all text should remain readable

  Scenario: Use blue for primary elements
    Given I am viewing any page
    Then the primary color should be blue
    And buttons, links, and selected items should use the primary blue

  Scenario: Use dark text for readability
    Given I am viewing any page
    Then body text should be dark on a light background
    And text should meet a minimum contrast ratio of 4.5:1 against its background

  Scenario: Keep white text readable on blue
    Given an element has a blue background
    Then its text should be white
    And the text should meet a minimum contrast ratio of 4.5:1 against the blue

  Scenario: Keep status indicators distinguishable
    Given I am viewing review status, workload, or availability indicators
    Then each status should remain distinguishable from the others
    And meaning should not be conveyed by color alone

  Scenario: Color scheme is applied without user action
    Given I am a new user
    When I open the application
    Then the blue and white color scheme should be applied
    And I should not need to change any settings

# Technical constraints:
#
# - Framework: Streamlit
# - Language: Python
# - Define the color scheme once, using Streamlit's native theme configuration
#   (.streamlit/config.toml) where possible.
# - Colors: white base background, light blue secondary background, blue primary,
#   dark text.
# - The gradient runs from white (#FFFFFF) through #EAF3FF to #D6E8FF at 135deg.
# - Gradient colors are defined as named constants in one module, separate from
#   UI logic, and applied once from the application entry point.
# - Do not implement a theme switcher, dark mode, or user-selectable schemes.
# - Do not store color preferences in Neo4j or session state.
# - Do not add new dependencies.
# - Custom CSS is limited to a single rule for the gradient background, because
#   the native theme only supports flat colors. Everything else uses the native theme.
