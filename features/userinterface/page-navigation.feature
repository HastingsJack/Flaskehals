Feature: Page Navigation

  As an authenticated user of the PR Review Assistant
  I want each section of the application to be its own page with its own URL
  So that I can navigate with a proper menu, use the browser's back and forward
  buttons, and bookmark or share a link to a specific page.

  Background:
    Given the application is running

  Scenario: Show a navigation menu with all pages
    Given I am authenticated
    When I open the application
    Then I should see a navigation menu in the sidebar
    And the menu should list the pages "Dashboard", "New task", and "Tasks"
    And the navigation should not be a row of radio buttons

  Scenario: Open the dashboard by default
    Given I am authenticated
    When I open the application without a page in the address
    Then the "Dashboard" page should be shown
    And "Dashboard" should be marked as the current page in the menu

  Scenario: Navigate to another page
    Given I am authenticated
    And I am viewing the "Dashboard" page
    When I select "Tasks" in the navigation menu
    Then the "Tasks" page should be shown
    And the browser address should change to the "Tasks" page
    And "Tasks" should be marked as the current page in the menu

  Scenario: Each page has its own address
    Given I am authenticated
    When I open the address of the "New task" page directly
    Then the "New task" page should be shown
    And "New task" should be marked as the current page in the menu

  Scenario: Use the browser back and forward buttons
    Given I am authenticated
    And I have navigated from "Dashboard" to "Tasks" to "New task"
    When I press the browser back button
    Then the "Tasks" page should be shown
    When I press the browser back button
    Then the "Dashboard" page should be shown
    When I press the browser forward button
    Then the "Tasks" page should be shown

  Scenario: Keep the navigation visible on every page
    Given I am authenticated
    When I navigate between all pages
    Then the navigation menu should be visible on each page
    And the "Log out" button should be available on each page

  Scenario: Preserve an unsent task draft when navigating
    Given I am authenticated
    And I have started filling in the "New task" form
    When I navigate to "Dashboard" and back to "New task"
    Then my draft task input should still be present

  Scenario: Require authentication for every page
    Given I have not authenticated
    When I open the address of the "Tasks" page directly
    Then I should see the login page
    And I should not see the navigation menu
    And no page content should be shown

  Scenario: Log out from any page
    Given I am authenticated
    And I am viewing the "Tasks" page
    When I click "Log out"
    Then I should see the login page
    And the navigation menu should no longer be shown

  Scenario: Keep the color scheme on navigation
    Given I am authenticated
    When I navigate between pages
    Then the selected page in the menu should use the primary blue
    And every page should keep the blue and white color scheme

# Technical constraints:
#
# - Framework: Streamlit
# - Language: Python
# - Use Streamlit's native multipage navigation (st.navigation and st.Page),
#   which provides the sidebar menu and per-page URLs. Do not build custom
#   routing or a custom menu.
# - Replace the page radio buttons in render_app; remove the PAGE_KEY session
#   state that only existed to drive them.
# - Page names and URL paths are defined once, in one place.
# - Page rendering stays in the existing render functions. Only the routing
#   changes. Business logic is not moved or modified.
# - Authentication is checked once in the application entry point, before
#   st.navigation runs, so no page can render for an unauthenticated user.
# - The existing draft-state handling must keep working across page changes.
# - Keep the single gradient CSS rule and the native theme from ui-color-scheme;
#   do not add further custom CSS for the menu.
# - Do not add new dependencies.
# - Do not add pages beyond Dashboard, New task, and Tasks.
# - Update the tests in tests/test_app.py that depend on the radio buttons.
