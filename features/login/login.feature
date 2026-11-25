Feature: Application Authentication

  As an authorised user
  I want to log into the PR Review Assistant
  So that access to the application is restricted.

  Background:
    Given the application is running
    And authentication is enabled

  Scenario: Display login page when unauthenticated
    Given I have not authenticated
    When I open the application
    Then I should see the login page
    And I should not be able to access the dashboard

  Scenario: Successfully authenticate with valid credentials
    Given I am on the login page
    When I enter the configured username
    And I enter the correct password
    And I submit the login form
    Then I should be authenticated
    And I should be redirected to the dashboard

  Scenario: Reject invalid username
    Given I am on the login page
    When I enter an incorrect username
    And I enter the correct password
    And I submit the login form
    Then authentication should fail
    And I should see an error message
    And I should remain on the login page

  Scenario: Reject invalid password
    Given I am on the login page
    When I enter the correct username
    And I enter an incorrect password
    And I submit the login form
    Then authentication should fail
    And I should see an error message
    And I should remain on the login page

  Scenario: Maintain authenticated session
    Given I have successfully authenticated
    When the application reruns
    Then I should remain authenticated
    And I should continue to have access to the dashboard

  Scenario: Log out
    Given I am authenticated
    When I select the logout option
    Then my authenticated session should be invalidated
    And I should be redirected to the login page

  Scenario: Prevent access after logout
    Given I have logged out
    When I attempt to access the dashboard
    Then I should be redirected to the login page

  Scenario: Handle missing username configuration
    Given the application has no configured username
    When the application starts
    Then authentication should fail safely
    And the application should not grant access to the dashboard

  Scenario: Handle missing password hash configuration
    Given the application has no configured password hash
    When the application starts
    Then authentication should fail safely
    And the application should not grant access to the dashboard

# Technical constraints:
#
# - Framework: Streamlit
# - Language: Python
# - Credentials must be loaded from environment variables.
# - Passwords must be stored as bcrypt hashes.
# - Never store plaintext passwords.
# - Authentication state must use Streamlit session state.
# - Do not implement user registration.
# - Do not implement password recovery.
# - Do not implement GitHub OAuth.
# - Keep authentication logic separate from UI logic.
# - Include logout functionality.