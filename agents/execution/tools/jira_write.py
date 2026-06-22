import os
import json
import requests
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Optional

class JiraConnector:
    def __init__(self, config=None):
        # Read credentials directly from environment variables loaded via dotenv
        self.base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL", "")
        self.api_token = os.getenv("JIRA_API_TOKEN", "")
        self.mock_mode = os.getenv("JIRA_MOCK", "false").lower() == "true"
        
        # ✅ FIX: Dynamically pull the project key from your config file, fall back to "KAN" if missing
        if config and hasattr(config, 'jira_project_key'):
            self.project_key = config.jira_project_key
        else:
            self.project_key = os.getenv("JIRA_PROJECT_KEY", "KAN")

        # Setup standard Basic Auth headers for Jira Cloud
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def create_ticket(self, title: str, description: str, team: str, moscow: str, assignee_id: Optional[str] = None) -> str:
        """
        Creates a single task ticket in Jira.
        Returns the Jira Issue Key (e.g., 'KAN-101') or a mock key.
        """
        if self.mock_mode or not self.base_url:
            print(f"[MOCK JIRA] Created ticket: '{title}' for team {team} (Assigned: {assignee_id})")
            return f"MOCK-{abs(hash(title)) % 1000}"

        url = f"{self.base_url}/rest/api/3/issue"
        
        # Jira Cloud API payload structure
        payload = {
            "fields": {
                "project": {
                    "key": self.project_key  # Now uses your real project key dynamically!
                },
                "summary": title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"{description}\n\n[Team]: {team}\n[MoSCoW]: {moscow}"
                                }
                            ]
                        }
                    ]
                },
                "issuetype": {
                    "name": "Task"
                }
            }
        }

        # Dynamically attach assignee if provided
        if assignee_id:
            payload["fields"]["assignee"] = {"id": assignee_id}

        response = requests.post(url, json=payload, auth=self.auth, headers=self.headers)
        
        if response.status_code == 201:
            issue_key = response.json().get("key")
            print(f"✅ Live Jira Ticket Created Successfully: {issue_key}")
            return issue_key
        else:
            raise RuntimeError(f"Failed to create Jira issue: {response.status_code} - {response.text}")

    def create_dependency_link(self, outward_key: str, inward_key: str):
        """
        Establishes a block link between two tickets in Jira.
        """
        if self.mock_mode or not self.base_url:
            print(f"[MOCK JIRA] Linked: {outward_key} blocks {inward_key}")
            return

        url = f"{self.base_url}/rest/api/3/issueLink"
        
        payload = {
            "type": {
                "name": "Blocks"
            },
            "inwardIssue": {
                "key": inward_key
            },
            "outwardIssue": {
                "key": outward_key
            }
        }

        response = requests.post(url, json=payload, auth=self.auth, headers=self.headers)
        if response.status_code != 201:
            print(f"⚠️ Warning: Could not create link {outward_key} -> {inward_key}: {response.text}")

    def get_active_issues(self, project_key: str) -> List[dict]:
        """
        Fetches all active (non-completed) issues in Jira for the given project key.
        """
        if self.mock_mode or not self.base_url:
            print("[MOCK JIRA] get_active_issues called. Returning empty list.")
            return []

        url = f"{self.base_url}/rest/api/3/search/jql"
        jql = f'project = "{project_key}" AND status != "Done"'
        params = {"jql": jql, "fields": "summary,description,status,assignee,issuetype", "maxResults": 100}

        try:
            response = requests.get(url, params=params, auth=self.auth, headers=self.headers)
            if response.status_code == 200:
                issues = response.json().get("issues", [])
                result = []
                for issue in issues:
                    fields = issue.get("fields", {})
                    assignee = fields.get("assignee")
                    result.append({
                        "key": issue.get("key"),
                        "summary": fields.get("summary", ""),
                        "description": self._parse_jira_description(fields.get("description")),
                        "status": fields.get("status", {}).get("name", "Unknown"),
                        "assignee_id": assignee.get("accountId") if assignee else None,
                        "assignee_name": assignee.get("displayName") if assignee else "Unassigned"
                    })
                return result
            else:
                print(f"⚠️ Failed to fetch active issues: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"⚠️ Error fetching active issues: {str(e)}")
            return []

    def get_issue_details(self, issue_key: str) -> Optional[dict]:
        """
        Fetches details of a single Jira issue.
        """
        if self.mock_mode or not self.base_url:
            print(f"[MOCK JIRA] get_issue_details called for {issue_key}.")
            return None

        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        try:
            response = requests.get(url, auth=self.auth, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                fields = data.get("fields", {})
                assignee = fields.get("assignee")
                return {
                    "key": data.get("key"),
                    "summary": fields.get("summary", ""),
                    "description": self._parse_jira_description(fields.get("description")),
                    "status": fields.get("status", {}).get("name", "Unknown"),
                    "assignee_id": assignee.get("accountId") if assignee else None,
                    "assignee_name": assignee.get("displayName") if assignee else "Unassigned"
                }
            else:
                print(f"⚠️ Failed to get issue details for {issue_key}: {response.status_code}")
                return None
        except Exception as e:
            print(f"⚠️ Error getting issue details: {str(e)}")
            return None

    def get_project_issues_for_report(self, project_key: str) -> List[dict]:
        """
        Fetches project issues for manager performance reporting.
        This includes Done and non-Done work so completion rates are meaningful.
        """
        if self.mock_mode or not self.base_url:
            print("[MOCK JIRA] Returning sample project issue rows for performance report.")
            return [
                {
                    "key": "MOCK-101",
                    "summary": "Mock completed backend task",
                    "status": "Done",
                    "statusCategory": "done",
                    "assignee_id": "7bca777e-f275-4dd5-8a89-f3d1e0d123e3",
                    "assignee_name": "Ayush Mittal",
                },
                {
                    "key": "MOCK-102",
                    "summary": "Mock in-progress backend task",
                    "status": "In Progress",
                    "statusCategory": "in_progress",
                    "assignee_id": "7bca777e-f275-4dd5-8a89-f3d1e0d123e3",
                    "assignee_name": "Ayush Mittal",
                },
                {
                    "key": "MOCK-103",
                    "summary": "Mock todo frontend task",
                    "status": "To Do",
                    "statusCategory": "to_do",
                    "assignee_id": "8d730902-21ef-4e0a-8f45-ed10f30a4e9f",
                    "assignee_name": "Ayush Mittal",
                },
            ]

        url = f"{self.base_url}/rest/api/3/search/jql"
        jql = f'project = "{project_key}"'
        params = {"jql": jql, "fields": "summary,status,assignee", "maxResults": 200}

        try:
            response = requests.get(url, params=params, auth=self.auth, headers=self.headers)
            if response.status_code != 200:
                print(f"⚠️ Failed to fetch report issues: {response.status_code} - {response.text}")
                return []

            result = []
            for issue in response.json().get("issues", []):
                fields = issue.get("fields", {})
                status = fields.get("status", {}) or {}
                assignee = fields.get("assignee")
                status_name = status.get("name", "Unknown")
                result.append({
                    "key": issue.get("key"),
                    "summary": fields.get("summary", ""),
                    "status": status_name,
                    "statusCategory": status.get("statusCategory", {}).get("key", ""),
                    "assignee_id": assignee.get("accountId") if assignee else None,
                    "assignee_name": assignee.get("displayName") if assignee else "Unassigned",
                })
            return result
        except Exception as e:
            print(f"⚠️ Error fetching report issues: {str(e)}")
            return []

    def transition_issue(self, issue_key: str, transition_name: str = "Done") -> bool:
        """
        Finds the transition ID matching the transition_name and transitions the issue.
        """
        if self.mock_mode or not self.base_url:
            print(f"[MOCK JIRA] Transitioned issue {issue_key} to '{transition_name}' status successfully.")
            return True

        # 1. Fetch available transitions
        transitions_url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        try:
            response = requests.get(transitions_url, auth=self.auth, headers=self.headers)
            if response.status_code != 200:
                print(f"⚠️ Failed to fetch transitions for {issue_key}: {response.status_code} - {response.text}")
                return False

            transitions = response.json().get("transitions", [])
            transition_id = None
            for t in transitions:
                name = t.get("name", "").lower()
                if transition_name.lower() in name or name in transition_name.lower():
                    transition_id = t.get("id")
                    break

            if not transition_id:
                # Fallback to whatever transition looks like completion or try the first one
                print(f"⚠️ Could not find a transition matching '{transition_name}'. Available: {[t.get('name') for t in transitions]}")
                # Let's try to match anything like "Done", "Completed", "Closed", "Finish"
                for t in transitions:
                    name = t.get("name", "").lower()
                    if any(w in name for w in ["done", "complete", "close", "finish", "resolve"]):
                        transition_id = t.get("id")
                        transition_name = t.get("name")
                        break

            if not transition_id:
                print("⚠️ No valid completion transitions found.")
                return False

            # 2. Perform the transition
            payload = {
                "transition": {
                    "id": transition_id
                }
            }
            post_response = requests.post(transitions_url, json=payload, auth=self.auth, headers=self.headers)
            if post_response.status_code in [204, 200, 201]:
                print(f"✅ Successfully transitioned Jira issue {issue_key} to '{transition_name}'")
                return True
            else:
                print(f"⚠️ Failed to transition issue {issue_key}: {post_response.status_code} - {post_response.text}")
                return False
        except Exception as e:
            print(f"⚠️ Error transitioning issue: {str(e)}")
            return False

    def _parse_jira_description(self, desc) -> str:
        """
        Helper to extract plain text from ADF description.
        """
        if not desc:
            return ""
        if isinstance(desc, str):
            return desc
        try:
            # Check for ADF format (Atlassian Document Format)
            if isinstance(desc, dict) and desc.get("type") == "doc":
                text_parts = []
                for content in desc.get("content", []):
                    if content.get("type") == "paragraph":
                        for c in content.get("content", []):
                            if c.get("type") == "text":
                                text_parts.append(c.get("text", ""))
                return "\n".join(text_parts)
        except Exception:
            pass
        return str(desc)
