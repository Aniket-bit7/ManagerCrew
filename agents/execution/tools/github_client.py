import os
import json
import requests
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

class GitHubConnector:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("GITHUB_TOKEN", "").strip()
        owner = os.getenv("GITHUB_OWNER", "Aniket-bit7").strip()
        repo_name = os.getenv("GITHUB_REPO", "").strip()
        if not repo_name:
            repo_name = "ManagerCrew"
        if "/" in repo_name:
            self.repo_full = repo_name.strip("/")
        else:
            self.repo_full = f"{owner}/{repo_name}".strip("/")
        
        self.state_file = "mock_github_state.json"
        self._init_mock_state()
        self.last_error = None
        
        # Determine if we should mock GitHub actions
        self.mock_mode = os.getenv("GITHUB_MOCK", "false").lower() == "true"
        
        if self.mock_mode:
            print("[MOCK GITHUB] Mock active. Running in simulated GitHub mode.")
        else:
            print(f"✅ GitHub Live Integration Active on {self.repo_full}")
            self.base_url = f"https://api.github.com/repos/{self.repo_full}"
            self.headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }

    def _init_mock_state(self):
        if not os.path.exists(self.state_file):
            initial_state = {
                "issues": [],
                "prs": []
            }
            with open(self.state_file, "w") as f:
                json.dump(initial_state, f, indent=2)

    def _load_mock_state(self) -> dict:
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception:
            return {"issues": [], "prs": []}

    def _save_mock_state(self, state: dict):
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving mock GitHub state: {str(e)}")

    def add_collaborator(self, username: str, permission: str = "maintain") -> bool:
        """
        Invites a user to be a collaborator on the repository.
        Attempts to grant the requested permission (e.g. 'maintain'), falling back
        to 'push' (write) if the repository type does not support it (e.g. personal repos).
        """
        if self.mock_mode:
            print(f"[MOCK GITHUB] Invited collaborator: {username} with permission: {permission}")
            return True
            
        url = f"https://api.github.com/repos/{self.repo_full}/collaborators/{username}"
        payload = {"permission": permission}
        try:
            response = requests.put(url, json=payload, headers=self.headers)
            if response.status_code in [201, 204]:
                print(f"✅ Proactively invited/added collaborator '{username}' to {self.repo_full} with permission '{permission}'")
                return True
            elif response.status_code == 422 and permission == "maintain":
                # Fallback to 'push' if 'maintain' is not supported on this repo type (e.g. personal repository)
                print(f"⚠️ 'maintain' permission not supported for {self.repo_full}. Falling back to 'push' (write).")
                payload_fallback = {"permission": "push"}
                response = requests.put(url, json=payload_fallback, headers=self.headers)
                if response.status_code in [201, 204]:
                    print(f"✅ Proactively invited/added collaborator '{username}' to {self.repo_full} with fallback permission 'push'")
                    return True
            print(f"⚠️ Failed to invite collaborator '{username}': {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"⚠️ Error inviting collaborator '{username}': {str(e)}")
            return False

    def _parse_github_error(self, response: requests.Response) -> str:
        try:
            data = response.json()
            msg = data.get("message", "")
        except Exception:
            msg = response.text or ""
            
        if response.status_code == 410:
            return f"Issues are disabled in repository '{self.repo_full}'. Please enable them in repository Settings."
        elif response.status_code == 404:
            return f"Repository '{self.repo_full}' not found. Check repository settings and access permissions."
        elif response.status_code == 401:
            return "Invalid GitHub Token. Please check your credentials."
        elif response.status_code == 403:
            return f"Access Forbidden (403). Your token might not have write access to '{self.repo_full}'."
        elif response.status_code == 422:
            return f"Validation Error (422): {msg}"
        return f"GitHub Error {response.status_code}: {msg}"

    def create_issue(self, title: str, body: str, assignee: Optional[str] = None) -> Optional[dict]:
        """
        Creates an issue on GitHub.
        """
        self.last_error = None
        if self.mock_mode:
            state = self._load_mock_state()
            issue_number = len(state["issues"]) + 101
            issue = {
                "number": issue_number,
                "title": title,
                "body": body,
                "assignee": assignee,
                "state": "open",
                "html_url": f"https://github.com/{self.repo_full}/issues/{issue_number}"
            }
            state["issues"].append(issue)
            self._save_mock_state(state)
            print(f"[MOCK GITHUB] Created Issue #{issue_number}: '{title}' assigned to {assignee}")
            return issue

        # Live mode
        if assignee:
            self.add_collaborator(assignee)

        url = f"{self.base_url}/issues"
        payload = {
            "title": title,
            "body": body
        }
        if assignee:
            payload["assignees"] = [assignee]

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code == 201:
                data = response.json()
                print(f"✅ Created Live GitHub Issue #{data.get('number')}: '{title}'")
                return {
                    "number": data.get("number"),
                    "title": data.get("title"),
                    "body": data.get("body"),
                    "assignee": assignee,
                    "state": data.get("state"),
                    "html_url": data.get("html_url")
                }
            elif response.status_code == 422 and assignee:
                # Fallback retry without assignee if collaborator validation failed
                print(f"⚠️ Assignee '{assignee}' is not a collaborator yet. Retrying issue creation without assignee.")
                payload_retry = {
                    "title": title,
                    "body": body + f"\n\n*(Note: Proactively invited @{assignee} as a collaborator. Assignee will show once they accept the invite.)*"
                }
                response = requests.post(url, json=payload_retry, headers=self.headers)
                if response.status_code == 201:
                    data = response.json()
                    print(f"✅ Created Live GitHub Issue #{data.get('number')}: '{title}' (Unassigned fallback)")
                    return {
                        "number": data.get("number"),
                        "title": data.get("title"),
                        "body": data.get("body"),
                        "assignee": None,
                        "state": data.get("state"),
                        "html_url": data.get("html_url")
                    }
                else:
                    print(f"⚠️ Failed to create GitHub issue on fallback retry: {response.status_code} - {response.text}")
                    self.last_error = self._parse_github_error(response)
                    return None
            else:
                print(f"⚠️ Failed to create GitHub issue: {response.status_code} - {response.text}")
                self.last_error = self._parse_github_error(response)
                return None
        except Exception as e:
            print(f"⚠️ Error creating GitHub issue: {str(e)}")
            self.last_error = f"Network or unexpected error: {str(e)}"
            return None

    def assign_issue(self, issue_number: int, assignee: str, invite_collaborator: bool = True) -> bool:
        """
        Assigns a GitHub issue to a collaborator.
        """
        if self.mock_mode:
            state = self._load_mock_state()
            for issue in state["issues"]:
                if issue["number"] == issue_number:
                    issue["assignee"] = assignee
                    self._save_mock_state(state)
                    print(f"[MOCK GITHUB] Assigned Issue #{issue_number} to {assignee}")
                    return True
            return False

        # Live mode: first ensure collaborator has invite sent
        if invite_collaborator:
            self.add_collaborator(assignee, permission="maintain")
        url = f"{self.base_url}/issues/{issue_number}/assignees"
        payload = {"assignees": [assignee]}
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code in [200, 201]:
                # Verify that assignee is actually set in response JSON (if they accepted, it will be in the assignees list)
                data = response.json()
                assignees = [a.get("login", "").lower() for a in data.get("assignees", []) if a]
                if assignee.lower() in assignees:
                    print(f"✅ Successfully assigned Live GitHub Issue #{issue_number} to {assignee}")
                    return True
                else:
                    print(f"⚠️ Invited assignee @{assignee} is not in the assignees list yet (pending collaborator invite acceptance).")
                    return False
            else:
                print(f"⚠️ Failed to assign GitHub Issue #{issue_number}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"⚠️ Error assigning GitHub Issue #{issue_number}: {str(e)}")
            return False

    def get_issues(self) -> List[dict]:
        if self.mock_mode:
            state = self._load_mock_state()
            return state["issues"]

        # Live mode
        url = f"{self.base_url}/issues"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                issues = response.json()
                result = []
                for data in issues:
                    # Ignore PRs which are returned by the issues endpoint
                    if "pull_request" in data:
                        continue
                    assignee_data = data.get("assignee")
                    result.append({
                        "number": data.get("number"),
                        "title": data.get("title"),
                        "body": data.get("body"),
                        "assignee": assignee_data.get("login") if assignee_data else None,
                        "state": data.get("state"),
                        "html_url": data.get("html_url")
                    })
                return result
            else:
                print(f"⚠️ Failed to fetch GitHub issues: {response.status_code}")
                return []
        except Exception as e:
            print(f"⚠️ Error fetching GitHub issues: {str(e)}")
            return []

    def create_pr(self, title: str, head_branch: str, base_branch: str = "main", body: str = "", assignee: Optional[str] = None) -> Optional[dict]:
        """
        Creates a pull request.
        """
        if self.mock_mode:
            state = self._load_mock_state()
            pr_number = len(state["prs"]) + 201
            pr = {
                "number": pr_number,
                "title": title,
                "head": head_branch,
                "base": base_branch,
                "body": body,
                "assignee": assignee,
                "reviewer": None,
                "state": "open",
                "diff": self._get_mock_diff(title),
                "html_url": f"https://github.com/{self.repo_full}/pull/{pr_number}",
                "comments": []
            }
            state["prs"].append(pr)
            self._save_mock_state(state)
            print(f"[MOCK GITHUB] Created Pull Request #{pr_number}: '{title}' for branch {head_branch}")
            return pr

        # Live mode
        url = f"{self.base_url}/pulls"
        payload = {
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code == 201:
                data = response.json()
                pr_number = data.get("number")
                print(f"✅ Created Live GitHub Pull Request #{pr_number}: '{title}'")
                
                if assignee:
                    self.add_collaborator(assignee)
                    requests.post(f"{self.base_url}/issues/{pr_number}/assignees", json={"assignees": [assignee]}, headers=self.headers)
                
                return {
                    "number": pr_number,
                    "title": data.get("title"),
                    "head": head_branch,
                    "base": base_branch,
                    "body": data.get("body"),
                    "assignee": assignee,
                    "reviewer": None,
                    "state": data.get("state"),
                    "html_url": data.get("html_url"),
                    "comments": []
                }
            else:
                print(f"⚠️ Failed to create GitHub PR: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"⚠️ Error creating GitHub PR: {str(e)}")
            return None

    def assign_pr_reviewer(self, pr_number: int, reviewer: str) -> bool:
        """
        Assigns a reviewer to a Pull Request.
        """
        state = self._load_mock_state()
        found_in_mock = False
        for pr in state["prs"]:
            if pr["number"] == pr_number:
                pr["reviewer"] = reviewer
                self._save_mock_state(state)
                print(f"[SIMULATED GITHUB] Assigned Reviewer '{reviewer}' to PR #{pr_number}")
                found_in_mock = True
                break

        if self.mock_mode or pr_number >= 201:
            return found_in_mock

        url = f"{self.base_url}/pulls/{pr_number}/requested_reviewers"
        payload = {"reviewers": [reviewer]}
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code in [200, 201]:
                print(f"✅ Assigned Live Reviewer '{reviewer}' to PR #{pr_number}")
                return True
            else:
                print(f"⚠️ Failed to assign reviewer to PR #{pr_number}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"⚠️ Error assigning reviewer: {str(e)}")
            return False

    def get_pr_diff(self, pr_number: int) -> str:
        """
        Gets the diff of a PR for review analysis.
        """
        if not self.mock_mode:
            url = f"{self.base_url}/pulls/{pr_number}"
            diff_headers = self.headers.copy()
            diff_headers["Accept"] = "application/vnd.github.v3.diff"
            try:
                response = requests.get(url, headers=diff_headers)
                if response.status_code == 200:
                    return response.text
                else:
                    print(f"⚠️ Failed to get PR diff from GitHub: {response.status_code}")
                    return ""
            except Exception as e:
                print(f"⚠️ Error getting PR diff from GitHub: {str(e)}")
                return ""

        # Fallback to local simulated/mock PR diff if live fetch fails or mock is active
        state = self._load_mock_state()
        for pr in state["prs"]:
            if pr["number"] == pr_number:
                return pr.get("diff", "")
        return ""

    def merge_pr(self, pr_number: int) -> bool:
        """
        Merges a Pull Request.
        """
        state = self._load_mock_state()
        found_in_mock = False
        for pr in state["prs"]:
            if pr["number"] == pr_number:
                pr["state"] = "merged"
                self._save_mock_state(state)
                print(f"[SIMULATED GITHUB] Merged PR #{pr_number} successfully.")
                found_in_mock = True
                break

        if self.mock_mode or pr_number >= 201:
            return found_in_mock

        url = f"{self.base_url}/pulls/{pr_number}/merge"
        payload = {
            "commit_title": "Auto-merge by Review Agent",
            "merge_method": "merge"
        }
        try:
            response = requests.put(url, json=payload, headers=self.headers)
            if response.status_code == 200:
                print(f"✅ Successfully Merged Live GitHub PR #{pr_number}")
                return True
            else:
                print(f"⚠️ Failed to merge GitHub PR #{pr_number}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"⚠️ Error merging GitHub PR: {str(e)}")
            return False

    def close_pr(self, pr_number: int) -> bool:
        """
        Closes a Pull Request without merging.
        """
        state = self._load_mock_state()
        found_in_mock = False
        for pr in state["prs"]:
            if pr["number"] == pr_number:
                pr["state"] = "closed"
                self._save_mock_state(state)
                print(f"[SIMULATED GITHUB] Closed PR #{pr_number} successfully.")
                found_in_mock = True
                break

        if self.mock_mode or pr_number >= 201:
            return found_in_mock

        url = f"{self.base_url}/pulls/{pr_number}"
        payload = {
            "state": "closed"
        }
        try:
            response = requests.patch(url, json=payload, headers=self.headers)
            if response.status_code == 200:
                print(f"✅ Successfully Closed Live GitHub PR #{pr_number}")
                return True
            else:
                print(f"⚠️ Failed to close GitHub PR #{pr_number}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"⚠️ Error closing GitHub PR: {str(e)}")
            return False

    def get_prs(self) -> List[dict]:
        if self.mock_mode:
            return self._load_mock_state().get("prs", [])

        # Query live pulls including all states (open + closed + merged)
        url = f"{self.base_url}/pulls?state=all&per_page=50"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                prs = response.json()
                live_prs = []
                for data in prs:
                    assignee_data = data.get("assignee")
                    reviewers_data = data.get("requested_reviewers", [])
                    is_merged = data.get("merged_at") is not None
                    state = "merged" if is_merged else data.get("state")
                    
                    live_prs.append({
                        "number": data.get("number"),
                        "title": data.get("title"),
                        "head": data.get("head", {}).get("ref"),
                        "base": data.get("base", {}).get("ref"),
                        "body": data.get("body", ""),
                        "assignee": assignee_data.get("login") if assignee_data else None,
                        "reviewer": reviewers_data[0].get("login") if reviewers_data else None,
                        "state": state,
                        "html_url": data.get("html_url"),
                        "comments": []
                    })
                return live_prs
            else:
                print(f"⚠️ Failed to fetch GitHub PRs: {response.status_code}")
                return []
        except Exception as e:
            print(f"⚠️ Error fetching GitHub PRs: {str(e)}")
            return []

    def _get_mock_diff(self, pr_title: str) -> str:
        """
        Generates simulated diffs based on target PR title templates.
        """
        title_lower = pr_title.lower()
        if "auth" in title_lower or "sensitive" in title_lower:
            return """diff --git a/src/auth/middleware.py b/src/auth/middleware.py
new file mode 100644
--- /dev/null
+++ b/src/auth/middleware.py
@@ -0,0 +1,15 @@
+import jwt
+import os
+
+JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-default-key") # SECURITY ALERT: hardcoded fallback
+
+def authenticate_user(token: str):
+    try:
+        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
+        return payload
+    except jwt.ExpiredSignatureError:
+        return {"error": "Token expired"}
+    except jwt.InvalidTokenError:
+        return {"error": "Invalid token"}
+"""
        elif "bug" in title_lower or "flaw" in title_lower or "bad code" in title_lower:
            return """diff --git a/src/payments/handler.py b/src/payments/handler.py
--- a/src/payments/handler.py
+++ b/src/payments/handler.py
@@ -10,4 +10,12 @@
-def charge_card(card_details, amount):
+def charge_card(card_details, amount):
+    # Complexity: 8/10, No tests, high nested branches
+    if amount <= 0:
+        raise ValueError("Invalid amount")
+    if not card_details:
+        raise ValueError("No card")
+    # Hardcoded sensitive logs - Security Risk!
+    print(f"Processing charge for card: {card_details['card_number']} CVV: {card_details['cvv']}")
+    stripe.Charge.create(amount=amount, card=card_details)
+    return True
"""
        else:
            # Normal simple feature
            return """diff --git a/src/components/Button.jsx b/src/components/Button.jsx
new file mode 100644
--- /dev/null
+++ b/src/components/Button.jsx
@@ -0,0 +1,10 @@
+import React from 'react';
+
+export const PremiumButton = ({ label, onClick }) => {
+  return (
+    <button className="bg-gradient-to-r from-purple-500 to-indigo-600 text-white font-semibold py-2 px-4 rounded-lg shadow-md hover:scale-105 transition-all duration-200" onClick={onClick}>
+      {label}
+    </button>
+  );
+};
+"""
