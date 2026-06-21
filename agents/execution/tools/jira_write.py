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