import os
import requests
from requests.auth import HTTPBasicAuth
from typing import Dict

class WIPMonitor:
    def __init__(self):
        self.base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL", "")
        self.api_token = os.getenv("JIRA_API_TOKEN", "")
        self.mock_mode = os.getenv("JIRA_MOCK", "false").lower() == "true"
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        # Added Content-Type and custom headers for strict API alignment
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def get_active_wip_counts(self, project_key: str) -> Dict[str, int]:
        """
        Queries Jira using JQL (Jira Query Language) to find tasks in status 
        'In Progress' or 'To Do' assigned to users.
        Returns a dictionary mapping jira_account_id -> active_ticket_count.
        """
        if self.mock_mode or not self.base_url:
            print("[MOCK WIP] Live Jira counts skipped. All engineers starting at 0 active tasks.")
            return {}

        # ✅ FIX: Wrap project_key in strict quotes for correct JQL parsing
        jql = f'project = "{project_key}" AND status IN ("In Progress", "To Do") AND assignee IS NOT EMPTY'
        url = f"{self.base_url}/rest/api/3/search"
        params = {"jql": jql, "fields": "assignee", "maxResults": 100}

        try:
            response = requests.get(url, params=params, auth=self.auth, headers=self.headers)
            wip_counts: Dict[str, int] = {}
            
            if response.status_code == 200:
                issues = response.json().get("issues", [])
                for issue in issues:
                    assignee = issue["fields"].get("assignee")
                    if assignee:
                        account_id = assignee.get("accountId")
                        if account_id:
                            wip_counts[account_id] = wip_counts.get(account_id, 0) + 1
                return wip_counts
            else:
                # If GET fails with 410 or 400, let's gracefully fall back to an empty capacity tracking state
                print(f"⚠️ Warning: Could not fetch live WIP counts ({response.status_code}). Response: {response.text[:100]}. Defaulting to 0.")
                return {}
        except Exception as e:
            print(f"⚠️ Exception querying Jira WIP: {str(e)}. Defaulting to 0.")
            return {}