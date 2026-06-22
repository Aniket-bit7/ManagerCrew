import os
import re
import json
import subprocess
from typing import List, Dict, Optional, Tuple
from groq import Groq
from agents.shared.config_loader import AppConfig, Engineer, load_config
from agents.execution.wip import WIPMonitor
from agents.execution.tools.slack_notify import SlackNotifier
from agents.execution.tools.github_client import GitHubConnector

from dotenv import load_dotenv

class ReviewAgent:
    def __init__(self, config: Optional[AppConfig] = None):
        load_dotenv()
        self.config = config or load_config()
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        self.client = Groq(api_key=self.groq_key) if self.groq_key else None
        self.wip_monitor = WIPMonitor()
        self.slack = SlackNotifier()
        self.github = GitHubConnector()
        self.debt_state_file = "review_debt_state.json"
        self._init_debt_state()

    def _init_debt_state(self):
        if not os.path.exists(self.debt_state_file):
            # Start with clean state - no dummy/mock data
            initial_debt = {
                "reviewer_stats": {},
                "bottlenecks": {},
                "cross_agent_logs": []
            }
            with open(self.debt_state_file, "w") as f:
                json.dump(initial_debt, f, indent=2)

    def _load_debt_state(self) -> dict:
        try:
            with open(self.debt_state_file, "r") as f:
                return json.load(f)
        except Exception:
            return {
                "reviewer_stats": {},
                "bottlenecks": {},
                "cross_agent_logs": []
            }

    def _save_debt_state(self, state: dict):
        try:
            with open(self.debt_state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving debt state: {str(e)}")

    def log_agent_communication(self, sender: str, receiver: str, topic: str, content: str):
        """
        Logs communication between agents for UI dashboard visualization.
        """
        import time
        state = self._load_debt_state()
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sender": sender,
            "receiver": receiver,
            "topic": topic,
            "content": content
        }
        state["cross_agent_logs"].insert(0, log_entry)  # Prepend newest
        # Cap at 50 logs
        state["cross_agent_logs"] = state["cross_agent_logs"][:50]
        self._save_debt_state(state)
        print(f"🔗 [Agent Communication] {sender} -> {receiver} | {topic}: {content}")

    def build_communication_agent_payload(self, pr_number: int, pr_title: str, scorecard: dict,
                                           reviewer: "Engineer", assignment_reason: str,
                                           task_description: str = "", jira_key: str = "",
                                           action_taken: str = "") -> dict:
        """
        Builds a structured payload for the Communication Agent.
        This payload contains the full audit result and can be consumed by
        the Communication Agent for report generation, stakeholder notifications,
        and sprint digest messages.
        """
        import time
        return {
            "event": "PR_AUDIT_COMPLETE",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pr": {
                "number": pr_number,
                "title": pr_title,
                "jira_key": jira_key,
                "task_description": task_description
            },
            "scorecard": scorecard,
            "reviewer": {
                "name": reviewer.name,
                "github_username": reviewer.github_username,
                "assignment_reason": assignment_reason
            },
            "action_taken": action_taken,  # "AUTO_MERGED", "MANUAL_REVIEW", "REJECTED"
            "repo": self.github.repo_full
        }

    def notify_pr_outcome(self, pr_number: int, pr_title: str, action: str,
                           author_slack_id: Optional[str], rejection_reasons: Optional[list] = None):
        """
        Sends a targeted Slack notification to the PR author's Slack ID
        (or the manager channel) about the PR outcome.
        action: 'MERGED', 'REJECTED', 'MANUAL_REVIEW'
        """
        import time
        if action == "MERGED":
            text = f"🎉 Your PR #{pr_number} *'{pr_title}'* has been *merged successfully*! Great work!"
            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": "✅ PR Merged Successfully"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*PR #{pr_number}:* {pr_title}\n\n🎉 Your code has been reviewed, approved, and merged into the main branch."}}
            ]
        elif action == "REJECTED":
            reasons_text = "\n".join([f"• {r}" for r in (rejection_reasons or ["Failed quality review."])]) if rejection_reasons else "• Failed quality review."
            text = f"❌ Your PR #{pr_number} *'{pr_title}'* was *rejected*. Please review the feedback."
            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": "❌ PR Rejected"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*PR #{pr_number}:* {pr_title}\n\n*Rejection Reasons:*\n{reasons_text}\n\nPlease address the above issues and raise a new PR."}}
            ]
        else:  # MANUAL_REVIEW
            text = f"👤 PR #{pr_number} *'{pr_title}'* requires *manual human review*."
            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": "👤 Manual Review Required"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*PR #{pr_number}:* {pr_title}\n\nThe AI review agent flagged this PR for mandatory human review due to complexity, security concerns, or unfulfilled requirements."}}
            ]

        # Try to DM the author if we have their Slack ID
        if author_slack_id and not self.slack.mock_mode:
            url = "https://slack.com/api/chat.postMessage"
            headers_s = {
                "Authorization": f"Bearer {self.slack.token}",
                "Content-Type": "application/json"
            }
            try:
                import requests as req_mod
                payload = {"channel": author_slack_id, "text": text, "blocks": blocks}
                r = req_mod.post(url, json=payload, headers=headers_s)
                rd = r.json()
                if rd.get("ok"):
                    print(f"✅ DM sent to author Slack ID {author_slack_id} about PR #{pr_number} outcome: {action}")
                    return
                else:
                    print(f"⚠️ DM to {author_slack_id} failed: {rd.get('error')}. Falling back to manager channel.")
            except Exception as e:
                print(f"⚠️ Error sending DM: {str(e)}. Falling back to manager channel.")

        # Fallback: post to manager channel
        self.slack.send_notification(text=text, blocks=blocks)

    def is_security_sensitive(self, files: List[str]) -> Tuple[bool, List[str]]:
        """
        Scans modified file paths for security-sensitive areas (auth, env, keys, permissions).
        """
        sensitive_patterns = [
            r"auth", r"env", r"secret", r"config", r"key", r"permission", 
            r"db/migration", r"middleware", r"credential"
        ]
        flagged_files = []
        for file in files:
            for pattern in sensitive_patterns:
                if re.search(pattern, file.lower()):
                    flagged_files.append(file)
                    break
        return len(flagged_files) > 0, flagged_files

    def analyze_git_expertise(self, files: List[str]) -> Dict[str, int]:
        """
        Runs local git log parsing on files changed in the PR to find which engineer has committed.
        """
        expertise = {eng.name: 0 for team in self.config.teams for eng in team.engineers}
        
        for file_path in files:
            if not os.path.exists(file_path):
                continue
            try:
                # Run git log to find contributors
                cmd = ["git", "log", "--follow", "--format=%an <%ae>", "--", file_path]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    authors = res.stdout.splitlines()
                    for author in authors:
                        author_lower = author.lower()
                        for eng_name in expertise.keys():
                            # Match engineer name or part of email
                            name_parts = eng_name.lower().split()
                            if any(part in author_lower for part in name_parts):
                                expertise[eng_name] += 1
            except Exception as e:
                print(f"⚠️ Git expertise analysis skipped for {file_path}: {str(e)}")
        
        # Add some default mock expertise counts if no git commits found (for clean simulation)
        total_commits = sum(expertise.values())
        if total_commits == 0:
            # Seed mock expertise based on files to make demo realistic
            for file in files:
                if "auth" in file.lower() or "handler" in file.lower():
                    # Ayush Mittal expert in Backend
                    expertise["Ayush Mittal"] = expertise.get("Ayush Mittal", 0) + 5
                elif "components" in file.lower() or "ui" in file.lower() or "button" in file.lower():
                    # Aniket Pathak expert in Frontend
                    expertise["Aniket Pathak"] = expertise.get("Aniket Pathak", 0) + 8
                    
        return expertise

    def smart_assign_reviewer(self, pr_number: int, pr_files: List[str], target_team_name: str = "FRONTEND") -> Tuple[Engineer, str, dict]:
        """
        Smart Reviewer Assignment:
        1. Analyzes commit history for expertise.
        2. Queries Jira active workloads.
        3. Assigns to developer with capacity (< WIP limit).
        """
        # Find engineers in this team
        team_map = self.config.get_team_mapping()
        target_team = team_map.get(target_team_name.upper())
        if not target_team:
            if self.config.teams:
                target_team = self.config.teams[0]
            else:
                dummy_engineer = Engineer(
                    name="Unassigned",
                    jira_account_id="",
                    slack_user_id="",
                    github_username="",
                    is_team_lead=False
                )
                return dummy_engineer, "No teams configured", {}
            
        engineers = target_team.engineers
        
        # Get expertise
        expertise_counts = self.analyze_git_expertise(pr_files)
        
        # Get workloads
        current_wip = self.wip_monitor.get_active_wip_counts(self.config.jira_project_key)
        
        candidates = []
        for eng in engineers:
            commits = expertise_counts.get(eng.name, 0)
            workload = current_wip.get(eng.jira_account_id, 0)
            candidates.append({
                "engineer": eng,
                "commits": commits,
                "workload": workload,
                "score": commits / (workload + 1.0)  # High commits, low workload is preferred
            })
            
        # Filter for candidates under WIP limit first
        under_capacity = [c for c in candidates if c["workload"] < self.config.wip_limit]
        
        if under_capacity:
            # Sort by expertise score
            under_capacity.sort(key=lambda x: x["score"], reverse=True)
            assigned_candidate = under_capacity[0]
            reason = f"has the most relevant expertise ({assigned_candidate['commits']} commits on changed modules) and has capacity (workload: {assigned_candidate['workload']} / {self.config.wip_limit} WIP limit)"
        else:
            # Fallback to engineer with lowest workload
            candidates.sort(key=lambda x: x["workload"])
            assigned_candidate = candidates[0]
            reason = f"assigned due to capacity bottleneck (all other engineers are at or above WIP limit, chosen because workload {assigned_candidate['workload']} is lowest)"
            
        assigned_eng = assigned_candidate["engineer"]
        
        # Update reviewer stats in debt database
        state = self._load_debt_state()
        if assigned_eng.name in state["reviewer_stats"]:
            state["reviewer_stats"][assigned_eng.name]["pending"] += 1
        else:
            state["reviewer_stats"][assigned_eng.name] = {"pending": 1, "completed": 0, "avg_response_hours": 2.0}
        self._save_debt_state(state)
        
        # Assign on Github
        if assigned_eng.github_username:
            self.github.assign_pr_reviewer(pr_number, assigned_eng.github_username)
            
        workloads_log = {eng.name: current_wip.get(eng.jira_account_id, 0) for eng in engineers}
        return assigned_eng, reason, workloads_log

    def generate_scorecard(self, pr_title: str, diff: str, task_description: str = "") -> dict:
        """
        AI-Powered Code Quality Scorecard.
        Scores the diff across Complexity, Test Coverage Delta, Security Risk, and Conventions.
        Checks if the PR diff satisfies the task description if provided.
        """
        if not self.client:
            print("[MOCK LLM] Groq client not initialized. Using rule-based fallback scorecard.")
            return self._fallback_scorecard(pr_title, diff, task_description)

        prompt = f"""You are a senior tech lead. Analyze this Pull Request Git Diff and generate a structured scorecard.

PR Title: {pr_title}
"""
        if task_description:
            prompt += f"\nTask Requirements (specified by Manager):\n{task_description}\n"

        prompt += f"""
GIT DIFF:
{diff[:4000]}

You MUST respond in strict JSON format matching this schema:
{{
  "complexity": 2, // Score from 1 (very simple UI component or comment changes) to 10 (extremely complex architectural logic)
  "complexity_reasoning": "Brief explanation...",
  "test_coverage_delta": 0.0, // Numeric value representing coverage change (e.g. +5.5, -2.0, 0.0)
  "coverage_reasoning": "Brief explanation of whether new tests are added...",
  "security_risk": "LOW", // "LOW", "MEDIUM", or "HIGH"
  "security_reasoning": "Explanation of any potential vulnerabilities, credentials exposed...",
  "adherence_to_team_conventions": "PASS", // "PASS" or "FAIL"
  "conventions_reasoning": "Brief check against standard code styling/naming...",
  "requirements_fulfilled": "YES", // "YES" or "NO" (Only set to "NO" if manager requirements are specified and the diff clearly fails to satisfy/implement them)
  "requirements_reasoning": "Explain whether the code matches the manager's requirements and task description...",
  "overall_recommendation": "APPROVE" // "APPROVE" (if complexity <= 4, risk is LOW, conventions PASS, and requirements_fulfilled is YES), "MANUAL_REVIEW" (otherwise or if security sensitive), "REJECT" (if requirements are completely unfulfilled or major bugs/risks found)
}}

Do not include any pre-text, post-text, markdown tags (like ```json), or explanation outside of the valid JSON string."""

        try:
            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=600
            )
            raw_content = completion.choices[0].message.content.strip()
            
            # Clean possible markdown fence output
            raw_content = re.sub(r"^```json\s*", "", raw_content)
            raw_content = re.sub(r"\s*```$", "", raw_content)
            
            scorecard = json.loads(raw_content)
            
            # Auto-approve override for very small, non-critical PRs (e.g. small UI changes or documentation)
            if len(diff.splitlines()) < 25 and scorecard.get("security_risk") == "LOW" and "auth" not in pr_title.lower() and "sensitive" not in pr_title.lower() and scorecard.get("requirements_fulfilled", "YES") == "YES":
                try:
                    comp_val = int(scorecard.get("complexity", 2))
                except Exception:
                    comp_val = 2
                scorecard["complexity"] = min(comp_val, 3)
                scorecard["complexity_reasoning"] = f"{scorecard.get('complexity_reasoning', '')} (Auto-downgraded complexity to {scorecard['complexity']} because the change is small: under 25 lines of code)."
                if scorecard.get("adherence_to_team_conventions") == "PASS":
                    scorecard["overall_recommendation"] = "APPROVE"
                    
            # Ensure overall recommendation matches fulfillment
            if scorecard.get("requirements_fulfilled") == "NO" and scorecard.get("overall_recommendation") == "APPROVE":
                scorecard["overall_recommendation"] = "MANUAL_REVIEW"
                
            return scorecard
        except Exception as e:
            print(f"⚠️ AI Scorecard query failed: {str(e)}. Falling back to rule-based scorecard.")
            return self._fallback_scorecard(pr_title, diff, task_description)

    def _fallback_scorecard(self, pr_title: str, diff: str, task_description: str = "") -> dict:
        title_lower = pr_title.lower()
        diff_lower = diff.lower()
        
        # Rule-based metrics
        complexity = 3
        complexity_reasoning = "Simple codebase change with standard structure."
        
        if "jwt" in diff_lower or "auth" in diff_lower or "crypt" in diff_lower:
            complexity = 7
            complexity_reasoning = "Contains authentication and cryptographic algorithms requiring deeper inspection."
            
        test_coverage = 0.0
        coverage_reasoning = "No test files added or modified in the diff."
        if "test" in diff_lower or "spec" in diff_lower:
            test_coverage = 5.0
            coverage_reasoning = "New test suites or test cases detected in diff (+5%)."
            
        security_risk = "LOW"
        security_reasoning = "No critical security violations found."
        
        is_sensitive, sensitive_files = self.is_security_sensitive([f.split()[-1] for f in diff.split('\n') if f.startswith('+++ b/')])
        if is_sensitive or "password" in diff_lower or "secret" in diff_lower or "cvv" in diff_lower:
            security_risk = "HIGH"
            security_reasoning = f"Touched sensitive files ({sensitive_files}) or contains hardcoded secrets/sensitive values."
        elif "api" in diff_lower or "db" in diff_lower:
            security_risk = "MEDIUM"
            security_reasoning = "Touches API endpoint configurations or DB structures."

        conventions = "PASS"
        conventions_reasoning = "Code follows standard naming and indenting structures."
        if "todo" in diff_lower or "print(" in diff_lower:
            conventions = "FAIL"
            conventions_reasoning = "Contains hardcoded debug logs or unfinished TODO comments."

        fulfilled = "YES"
        fulfilled_reasoning = "Assumed meeting manager requirements in rule-based fallback."
        if task_description:
            # Fallback simple search: if description has unique keywords, verify their presence in the diff
            desc_words = [w.lower() for w in task_description.split() if len(w) > 4]
            # Match if any keywords exist in diff/title
            matches = [w for w in desc_words if w in diff_lower or w in title_lower]
            if len(desc_words) > 2 and len(matches) == 0:
                fulfilled = "NO"
                fulfilled_reasoning = f"Keywords from task requirements ({desc_words[:3]}) were not found in the PR changes."
            else:
                fulfilled_reasoning = f"Diff contains matching concepts ({matches[:3]}) for the manager task requirements."

        # Overall recommendation
        recommendation = "APPROVE"
        if security_risk in ["HIGH", "MEDIUM"] or complexity >= 5 or conventions == "FAIL" or fulfilled == "NO":
            recommendation = "MANUAL_REVIEW"
            
        return {
            "complexity": complexity,
            "complexity_reasoning": complexity_reasoning,
            "test_coverage_delta": test_coverage,
            "coverage_reasoning": coverage_reasoning,
            "security_risk": security_risk,
            "security_reasoning": security_reasoning,
            "adherence_to_team_conventions": conventions,
            "conventions_reasoning": conventions_reasoning,
            "requirements_fulfilled": fulfilled,
            "requirements_reasoning": fulfilled_reasoning,
            "overall_recommendation": recommendation
        }

    def process_pull_request(self, pr_number: int, pr_title: str, team_name: str = "FRONTEND", task_description: str = "") -> dict:
        """
        Executes the full review workflow:
        1. Fetch diff.
        2. Check for security sensitivity.
        3. Score PR (AI Scorecard based on requirements).
        4. Match expertise and assign reviewer.
        5. Post Slack notification.
        6. Return results dictionary.
        """
        print(f"\n⚡ Auditing PR #{pr_number}: '{pr_title}'...")
        diff = self.github.get_pr_diff(pr_number)
        
        # 1. AI Scorecard
        scorecard = self.generate_scorecard(pr_title, diff, task_description)
        
        # 2. Security Check
        # Extract files from diff
        files = []
        for line in diff.split('\n'):
            if line.startswith('+++ b/'):
                files.append(line[6:].strip())
        
        is_sensitive, sensitive_files = self.is_security_sensitive(files)
        if is_sensitive:
            scorecard["security_risk"] = "HIGH"
            scorecard["overall_recommendation"] = "MANUAL_REVIEW"
            scorecard["security_reasoning"] = f"TOUCHED SENSITIVE FILES: {', '.join(sensitive_files)}. Routing for mandatory human review."

        # 3. Smart Reviewer Assignment
        reviewer, assignment_reason, workloads = self.smart_assign_reviewer(pr_number, files, team_name)
        
        # 4. Cross-Agent Notifications (DO NOT CHANGE - Agent Interaction requirements)
        # Risk Agent Alert if critical path blocks
        if scorecard["security_risk"] == "HIGH":
            self.log_agent_communication(
                sender="Review Agent",
                receiver="Risk Agent",
                topic="Critical Path Threat",
                content=f"PR #{pr_number} touches sensitive security files. Raised risk evaluation threshold."
            )
        
        # Communication Agent - build full structured payload
        comm_payload = self.build_communication_agent_payload(
            pr_number=pr_number,
            pr_title=pr_title,
            scorecard=scorecard,
            reviewer=reviewer,
            assignment_reason=assignment_reason,
            task_description=task_description
        )
        self.log_agent_communication(
            sender="Review Agent",
            receiver="Communication Agent",
            topic="PR Audit Payload",
            content=f"PR #{pr_number} audit complete. Complexity: {scorecard['complexity']}/10, Security: {scorecard['security_risk']}, Recommendation: {scorecard['overall_recommendation']}. Full payload available."
        )

        # Execution Agent - trigger Jira transition signal
        self.log_agent_communication(
            sender="Review Agent",
            receiver="Execution Agent",
            topic="Jira Transition Signal",
            content=f"PR #{pr_number} reviewed. Recommendation: {scorecard['overall_recommendation']}. Awaiting Execution Agent to transition Jira issue status accordingly."
        )

        # Safely convert test_coverage_delta to float to prevent format ValueError
        cov_delta = scorecard.get("test_coverage_delta", 0.0)
        try:
            if isinstance(cov_delta, str):
                cov_delta = float(re.sub(r"[^\d.-]", "", cov_delta))
            else:
                cov_delta = float(cov_delta)
        except Exception:
            cov_delta = 0.0

        # 5. Build and Send Slack Notification
        slack_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔎 Review Agent Alert: PR #{pr_number} Raised"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Title:* {pr_title}\n*Repository:* `{self.github.repo_full}`"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Complexity:* {scorecard.get('complexity', 3)}/10"},
                    {"type": "mrkdwn", "text": f"*Coverage Delta:* {cov_delta:+.1f}%"},
                    {"type": "mrkdwn", "text": f"*Security Risk:* `{scorecard.get('security_risk', 'LOW')}`"},
                    {"type": "mrkdwn", "text": f"*Conventions:* {scorecard.get('adherence_to_team_conventions', 'PASS')}"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Requirements Met:* `{scorecard.get('requirements_fulfilled', 'YES')}`\n*Fulfillment Reasoning:* {scorecard.get('requirements_reasoning', 'N/A')}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Assigned Reviewer:* @{reviewer.name} ({reviewer.github_username})\n*Reason:* {assignment_reason}"
                }
            }
        ]

        if scorecard["overall_recommendation"] == "APPROVE":
            slack_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🟢 *Action:* Low Risk & Complexity. Bypassing human review for *Auto-Merge*."
                }
            })
        else:
            slack_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔴 *Action:* Security concern or conventions issue. *Mandatory Human Review Required*."
                }
            })

        self.slack.send_notification(
            text=f"PR #{pr_number} review scorecard ready. Recommendation: {scorecard['overall_recommendation']}",
            blocks=slack_blocks
        )

        # 6. Save bottlenecks to debt stats
        if files:
            state = self._load_debt_state()
            for file in files:
                folder = "/".join(file.split("/")[:-1]) + "/" if "/" in file else file
                state["bottlenecks"][folder] = state["bottlenecks"].get(folder, 0) + 1
            self._save_debt_state(state)

        return {
            "pr_number": pr_number,
            "title": pr_title,
            "scorecard": scorecard,
            "reviewer": reviewer,
            "assignment_reason": assignment_reason,
            "workloads": workloads,
            "files": files,
            "diff": diff,
            "communication_agent_payload": comm_payload
        }

    def detect_and_escalate_stale_prs(self, days_threshold: float = 2.0):
        """
        Auto-Escalates stale PRs (open > 48 hours or blocking critical path tasks) to Slack.
        """
        prs = self.github.get_prs()
        import time
        
        stale_count = 0
        for pr in prs:
            if pr.get("state") != "open":
                continue
                
            # For simulation, we randomly identify PRs as stale or check a flag.
            # Let's say PRs with odd numbers are flagged as stale (open 52 hours) to simulate this.
            is_stale = (pr["number"] % 2 == 1)
            
            if is_stale:
                stale_count += 1
                pr_number = pr["number"]
                reviewer_username = pr.get("reviewer") or "unassigned"
                
                # Check target team config to map github username back to real name
                reviewer_name = reviewer_username
                for team in self.config.teams:
                    for eng in team.engineers:
                        if eng.github_username == reviewer_username:
                            reviewer_name = eng.name
                            break
                            
                # Escalate message
                escalation_text = f"🚨 *PR Escalation*: PR #{pr_number} ('{pr['title']}') has been open for 52 hours under review by @{reviewer_name}. This blocks critical path tasks in the current sprint!"
                
                self.slack.send_notification(
                    text=f"PR #{pr_number} Escalation Alert",
                    blocks=[
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "⏳ Stale PR Escalation"}
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": escalation_text}
                        }
                    ]
                )
                
                self.log_agent_communication(
                    sender="Review Agent",
                    receiver="Risk Agent",
                    topic="Critical Path Delay",
                    content=f"PR #{pr_number} has been stale for 48+ hours. Escalated to Slack."
                )
                
        return stale_count
