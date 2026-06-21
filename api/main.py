import os
import re
import sys
import yaml
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory of 'api' (which is project root) to path
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents.shared.config_loader import load_config
from agents.execution.tools.jira_write import JiraConnector
from agents.execution.tools.github_client import GitHubConnector
from agents.execution.tools.slack_notify import SlackNotifier
from agents.review.agent import ReviewAgent

app = FastAPI(title="Manager Crew EM API Hub", version="1.0.0")

# Enable CORS for React Frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in local dev environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Components
config = load_config()
jira = JiraConnector(config=config)
github = GitHubConnector()
slack = SlackNotifier()
review_agent = ReviewAgent(config=config)

def reload_components():
    global config, jira, github, slack, review_agent
    load_dotenv(override=True)
    config = load_config()
    jira = JiraConnector(config=config)
    github = GitHubConnector()
    slack = SlackNotifier()
    review_agent = ReviewAgent(config=config)

def update_env_file(updates: dict):
    env_path = Path(".env")
    if not env_path.exists():
        env_content = ""
    else:
        with open(env_path, "r") as f:
            env_content = f.read()

    lines = env_content.splitlines()
    updated_keys = set()
    new_lines = []

    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key, val = line.split("=", 1)
            key = key.strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    with open(env_path, "w") as f:
        f.write("\n".join(new_lines) + "\n")

def update_team_config(wip_limit: int, jira_project_key: str, engineers: list, team_lead_slack_id: str = ""):
    config_path = Path("config/team_config.yaml")
    if not config_path.exists():
        data = {
            "wip_limit": wip_limit,
            "sprint_duration_days": 20,
            "jira_project_key": jira_project_key,
            "confidence_threshold": 0.60,
            "teams": [{
                "name": "FRONTEND",
                "slack_channel": "",
                "team_lead_slack_id": team_lead_slack_id,
                "engineers": engineers
            }]
        }
    else:
        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}
        data["wip_limit"] = wip_limit
        data["jira_project_key"] = jira_project_key
        if "teams" not in data or not data["teams"]:
            data["teams"] = [{
                "name": "FRONTEND",
                "slack_channel": "",
                "team_lead_slack_id": team_lead_slack_id,
                "engineers": []
            }]
        data["teams"][0]["engineers"] = engineers
        data["teams"][0]["team_lead_slack_id"] = team_lead_slack_id

    with open(config_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)

# Request Models
class CreateTaskRequest(BaseModel):
    title: str
    description: str
    team: str
    moscow: str
    assigneeName: str
    assigneeJiraId: Optional[str] = ""
    assigneeGithubId: Optional[str] = ""

class AssignTaskRequest(BaseModel):
    jiraKey: str
    assigneeJiraId: str

class CreateIssueRequest(BaseModel):
    title: str
    description: str
    assigneeGithubId: Optional[str] = ""
    assigneeJiraId: Optional[str] = ""
    assigneeName: Optional[str] = ""

class RaisePRRequest(BaseModel):
    jiraKey: str
    jiraTitle: str
    assigneeName: str
    team: str
    codeTemplate: str

class AuditPRRequest(BaseModel):
    prNumber: int
    prTitle: str
    teamName: str
    taskDescription: Optional[str] = ""

class ResolvePRRequest(BaseModel):
    prNumber: int
    action: str  # "approve" or "reject"
    jiraKey: str

class SettingsEngineer(BaseModel):
    name: str
    jira_account_id: str
    slack_user_id: str
    github_username: str
    is_team_lead: bool = False

class SettingsUpdateRequest(BaseModel):
    github_repo: str
    slack_bot_token: str
    slack_manager_channel: str
    jira_api_token: str
    jira_email: str
    jira_base_url: str
    github_token: str
    github_owner: str
    groq_api_key: str
    wip_limit: int
    jira_project_key: str
    team_lead_slack_id: Optional[str] = ""
    engineers: List[SettingsEngineer]

# Endpoints
@app.get("/api/config")
def get_app_config():
    """
    Returns registered teams, engineers, and environment status.
    """
    teams_data = []
    for team in config.teams:
        engineers = [{
            "name": eng.name,
            "github_username": eng.github_username,
            "jira_account_id": eng.jira_account_id,
            "slack_user_id": getattr(eng, "slack_user_id", ""),
            "is_team_lead": getattr(eng, "is_team_lead", False)
        } for eng in team.engineers]
        teams_data.append({
            "name": team.name,
            "team_lead_slack_id": getattr(team, "team_lead_slack_id", ""),
            "engineers": engineers
        })
    return {
        "jiraProjectKey": config.jira_project_key,
        "wipLimit": config.wip_limit,
        "jiraMock": jira.mock_mode,
        "githubMock": github.mock_mode,
        "slackMock": slack.mock_mode,
        "teams": teams_data
    }

@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    """
    Aggregates metrics for the manager dashboard.
    """
    try:
        debt_state = review_agent._load_debt_state()
        prs = github.get_prs()
        active_prs = [p for p in prs if p.get("state") == "open"]
        merged_prs = [p for p in prs if p.get("state") == "merged"]
        
        # Determine stale count (open and number % 2 == 1 in simulation)
        stale_prs = [p for p in active_prs if p.get("number", 0) % 2 == 1]
        
        # Extract bottleneck paths
        bottlenecks = [{"path": k, "count": v} for k, v in debt_state.get("bottlenecks", {}).items()]
        bottlenecks.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "activePrsCount": len(active_prs),
            "mergedPrsCount": len(merged_prs),
            "stalePrsCount": len(stale_prs),
            "bottlenecks": bottlenecks,
            "activePrs": active_prs,
            "mergedPrs": merged_prs,
            "stalePrsList": stale_prs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/workloads")
def get_dashboard_workloads():
    """
    Computes reviewers pending/completed tasks and Jira active workloads.
    """
    try:
        debt_state = review_agent._load_debt_state()
        reviewer_stats = []
        for eng_name, stats in debt_state.get("reviewer_stats", {}).items():
            reviewer_stats.append({
                "name": eng_name,
                "pending": stats.get("pending", 0),
                "completed": stats.get("completed", 0),
                "avgResponseHours": stats.get("avg_response_hours", 2.0)
            })
            
        # Jira Active Workloads
        wip = review_agent.wip_monitor.get_active_wip_counts(config.jira_project_key)
        jira_workloads = []
        for team in config.teams:
            for eng in team.engineers:
                jira_workloads.append({
                    "name": eng.name,
                    "activeTasks": wip.get(eng.jira_account_id, 0),
                    "team": team.name
                })
                
        return {
            "reviewerStats": reviewer_stats,
            "jiraWorkloads": jira_workloads
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/create")
def create_task(req: CreateTaskRequest):
    """
    Creates a Jira task ticket AND a linked GitHub issue for the same task.
    """
    try:
        # 1. Create Jira ticket
        jira_key = jira.create_ticket(
            title=req.title,
            description=req.description,
            team=req.team,
            moscow=req.moscow,
            assignee_id=req.assigneeJiraId or None
        )
        
        # 2. Create linked GitHub issue
        github_issue = github.create_issue(
            title=f"[{jira_key}] {req.title}",
            body=f"**Jira Issue:** [{jira_key}]({jira.base_url}/browse/{jira_key})\n\n**Task Description:**\n{req.description}\n\n**Team:** {req.team}\n**MoSCoW Priority:** {req.moscow}\n**Assigned To:** {req.assigneeName}",
            assignee=req.assigneeGithubId or None
        )
        
        # 3. Log cross-agent communication
        review_agent.log_agent_communication(
            sender="Execution Agent",
            receiver="GitHub",
            topic="Issue Created",
            content=f"Task '{req.title}' created as Jira issue {jira_key} and GitHub issue #{github_issue.get('number') if github_issue else 'N/A'}. Assigned to {req.assigneeName}."
        )
        
        return {
            "success": True,
            "jiraKey": jira_key,
            "jiraUrl": f"{jira.base_url}/browse/{jira_key}",
            "githubIssue": github_issue,
            "message": f"Task created! Jira: {jira_key}, GitHub Issue: #{github_issue.get('number') if github_issue else 'N/A'}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/list")
def list_active_tasks():
    """
    Fetches all active (non-done) Jira issues for the configured project.
    """
    try:
        issues = jira.get_active_issues(config.jira_project_key)
        github_issues = github.get_issues()
        
        # Enrich Jira issues with GitHub issue links
        enriched = []
        for issue in issues:
            gh_match = next(
                (g for g in github_issues if f"[{issue['key']}]" in (g.get("title") or "")),
                None
            )
            enriched.append({
                **issue,
                "github_issue": gh_match
            })
        
        return {"issues": enriched, "total": len(enriched)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/assign")
def assign_task(req: AssignTaskRequest):
    """
    Assigns a Jira issue to a team member.
    """
    try:
        url = f"{jira.base_url}/rest/api/3/issue/{req.jiraKey}/assignee"
        payload = {"accountId": req.assigneeJiraId}
        resp = __import__('requests').put(url, json=payload, auth=jira.auth, headers=jira.headers)
        if resp.status_code in [204, 200, 201]:
            review_agent.log_agent_communication(
                sender="Execution Agent",
                receiver="Jira",
                topic="Issue Assigned",
                content=f"Jira issue {req.jiraKey} assigned to account ID {req.assigneeJiraId}."
            )
            return {"success": True, "message": f"Issue {req.jiraKey} assigned successfully."}
        else:
            raise HTTPException(status_code=400, detail=f"Failed to assign: {resp.text}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/config/settings")
def get_settings():
    load_dotenv(override=True)
    
    engineers_data = []
    team_lead_slack_id = ""
    if config.teams:
        team = config.teams[0]
        team_lead_slack_id = getattr(team, "team_lead_slack_id", "")
        for eng in team.engineers:
            engineers_data.append({
                "name": eng.name,
                "jira_account_id": eng.jira_account_id,
                "slack_user_id": eng.slack_user_id,
                "github_username": eng.github_username,
                "is_team_lead": getattr(eng, "is_team_lead", False)
            })
            
    return {
        "github_repo": os.getenv("GITHUB_REPO", ""),
        "slack_bot_token": os.getenv("SLACK_BOT_TOKEN", ""),
        "slack_manager_channel": os.getenv("SLACK_MANAGER_CHANNEL", ""),
        "jira_api_token": os.getenv("JIRA_API_TOKEN", ""),
        "jira_email": os.getenv("JIRA_EMAIL", ""),
        "jira_base_url": os.getenv("JIRA_BASE_URL", ""),
        "github_token": os.getenv("GITHUB_TOKEN", ""),
        "github_owner": os.getenv("GITHUB_OWNER", ""),
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "wip_limit": config.wip_limit,
        "jira_project_key": config.jira_project_key,
        "team_lead_slack_id": team_lead_slack_id,
        "engineers": engineers_data
    }

@app.post("/api/config/settings")
def update_settings(req: SettingsUpdateRequest):
    try:
        updates = {
            "GITHUB_REPO": req.github_repo.strip(),
            "SLACK_BOT_TOKEN": req.slack_bot_token.strip(),
            "SLACK_MANAGER_CHANNEL": req.slack_manager_channel.strip(),
            "JIRA_API_TOKEN": req.jira_api_token.strip(),
            "JIRA_EMAIL": req.jira_email.strip(),
            "JIRA_BASE_URL": req.jira_base_url.strip(),
            "GITHUB_TOKEN": req.github_token.strip(),
            "GITHUB_OWNER": req.github_owner.strip(),
            "GROQ_API_KEY": req.groq_api_key.strip(),
            "JIRA_MOCK": "false",
            "SLACK_MOCK": "false",
            "GITHUB_MOCK": "false"
        }
        update_env_file(updates)
        
        engineers_list = []
        for eng in req.engineers:
            engineers_list.append({
                "name": eng.name.strip(),
                "jira_account_id": eng.jira_account_id.strip(),
                "slack_user_id": eng.slack_user_id.strip(),
                "github_username": eng.github_username.strip(),
                "is_team_lead": eng.is_team_lead
            })
            
        update_team_config(
            wip_limit=req.wip_limit,
            jira_project_key=req.jira_project_key.strip(),
            engineers=engineers_list,
            team_lead_slack_id=(req.team_lead_slack_id or "").strip()
        )
        
        reload_components()
        
        return {
            "success": True,
            "message": "Configuration settings saved and components successfully reloaded."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")

@app.post("/api/sprint/audit-pr")
def audit_pull_request(req: AuditPRRequest):
    """
    Executes the Review Agent code audit.
    - Auto-fetches task description from Jira using the Jira key in the PR title.
    - If APPROVE: auto-merges PR and transitions Jira to Done, DMs author.
    - If MANUAL_REVIEW: pings the team lead on Slack with full scorecard + reasons.
    - If REJECT: notifies author with detailed rejection reasons.
    """
    try:
        # 1. Determine PR author from GitHub
        all_prs = github.get_prs()
        matching_pr = next((p for p in all_prs if p.get("number") == req.prNumber), None)
        pr_author_github = matching_pr.get("assignee") if matching_pr else None

        # 2. Look up author's Slack ID from team config
        author_slack_id = None
        if pr_author_github:
            for team in config.teams:
                for eng in team.engineers:
                    if eng.github_username and eng.github_username.lower() == pr_author_github.lower():
                        author_slack_id = getattr(eng, "slack_user_id", None) or None
                        break

        # 3. Auto-fetch task description from Jira by extracting Jira key from PR title
        task_description = req.taskDescription or ""
        jira_key_from_pr = ""
        match_key = re.search(r"\b([a-zA-Z]+-\d+)\b", req.prTitle)
        if match_key:
            jira_key_from_pr = match_key.group(1).upper()
        elif matching_pr and matching_pr.get("head"):
            match_branch = re.search(r"\b([a-zA-Z]+-\d+)\b", matching_pr["head"])
            if match_branch:
                jira_key_from_pr = match_branch.group(1).upper()

        if jira_key_from_pr and not task_description:
            # Fetch from Jira
            issue_details = jira.get_issue_details(jira_key_from_pr)
            if issue_details:
                desc = issue_details.get("description", "") or ""
                summary = issue_details.get("summary", "") or ""
                task_description = desc if desc else summary
                print(f"✅ Auto-fetched task description from Jira {jira_key_from_pr}: '{task_description[:80]}...'")

        # 4. Trigger Review Agent pipeline with auto-fetched requirements
        result = review_agent.process_pull_request(
            pr_number=req.prNumber,
            pr_title=req.prTitle,
            team_name=req.teamName,
            task_description=task_description
        )
        
        scorecard = result.get("scorecard", {})
        auto_merged = False
        auto_merge_message = ""

        # 5. Get team lead Slack ID for MANUAL_REVIEW escalations
        team_lead_slack_id = ""
        for team in config.teams:
            lead_id = getattr(team, "team_lead_slack_id", "") or ""
            if lead_id:
                team_lead_slack_id = lead_id
                break
        # Fallback: find engineer marked as team lead
        if not team_lead_slack_id:
            for team in config.teams:
                for eng in team.engineers:
                    if getattr(eng, "is_team_lead", False) and eng.slack_user_id:
                        team_lead_slack_id = eng.slack_user_id
                        break

        # Build rejection reasons list (used for MANUAL_REVIEW and REJECT)
        reasons = []
        if scorecard.get("security_risk") in ["HIGH", "MEDIUM"]:
            reasons.append(f"*Security Risk ({scorecard['security_risk']}):* {scorecard.get('security_reasoning', '')}")
        if scorecard.get("adherence_to_team_conventions") == "FAIL":
            reasons.append(f"*Convention Violations:* {scorecard.get('conventions_reasoning', '')}")
        if scorecard.get("requirements_fulfilled") == "NO":
            reasons.append(f"*Requirements Not Met:* {scorecard.get('requirements_reasoning', '')}")
        try:
            if int(scorecard.get("complexity", 0)) >= 7:
                reasons.append(f"*High Complexity ({scorecard.get('complexity')}/10):* {scorecard.get('complexity_reasoning', '')}")
        except Exception:
            pass

        # 6. Act on recommendation
        if scorecard.get("overall_recommendation") == "APPROVE":
            # Auto-Merge via GitHub
            github.merge_pr(req.prNumber)

            # Transition Jira Issue to Done via Execution Agent
            if jira_key_from_pr:
                jira.transition_issue(jira_key_from_pr, "Done")
                review_agent.log_agent_communication(
                    sender="Execution Agent",
                    receiver="Jira",
                    topic="Status Transition: Done",
                    content=f"PR #{req.prNumber} auto-merged. Execution Agent transitioned Jira issue '{jira_key_from_pr}' to DONE."
                )
                auto_merge_message = f"🎉 Auto-Merge Complete! PR #{req.prNumber} merged, Jira '{jira_key_from_pr}' → Done!"
            else:
                auto_merge_message = f"🎉 Auto-Merge Complete! PR #{req.prNumber} merged."
            auto_merged = True

            # Clear from pending reviews if it exists there
            debt_state = review_agent._load_debt_state()
            pending = debt_state.setdefault("pending_reviews", {})
            if str(req.prNumber) in pending:
                del pending[str(req.prNumber)]
            if jira_key_from_pr:
                keys_to_delete = [k for k, v in pending.items() if v.get("jira_key") == jira_key_from_pr]
                for k in keys_to_delete:
                    if k in pending:
                        del pending[k]
            review_agent._save_debt_state(debt_state)

            # Notify PR author (merged)
            review_agent.notify_pr_outcome(
                pr_number=req.prNumber,
                pr_title=req.prTitle,
                action="MERGED",
                author_slack_id=author_slack_id
            )
            review_agent.log_agent_communication(
                sender="Review Agent",
                receiver="Communication Agent",
                topic="PR Merged",
                content=f"PR #{req.prNumber} merged. Author (Slack: {author_slack_id or 'N/A'}) notified."
            )

        elif scorecard.get("overall_recommendation") == "MANUAL_REVIEW":
            # ── Notify the author ──────────────────────────────────────────────
            review_agent.notify_pr_outcome(
                pr_number=req.prNumber,
                pr_title=req.prTitle,
                action="MANUAL_REVIEW",
                author_slack_id=author_slack_id,
                rejection_reasons=reasons if reasons else None
            )

            # ── Escalate to Team Lead ──────────────────────────────────────────
            pr_url = matching_pr.get("html_url", "") if matching_pr else ""
            reasons_text = "\n".join([f"• {r}" for r in reasons]) if reasons else "• General quality concerns flagged by the AI agent."
            lead_text = (
                f"🔍 *Manual Code Review Requested* — PR #{req.prNumber}\n"
                f"Title: *{req.prTitle}*"
            )
            lead_blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": "🔍 Human Code Review Required", "emoji": True}},
                {"type": "section", "text": {"type": "mrkdwn", "text": (
                    f"The AI Review Agent has flagged *PR #{req.prNumber}* for mandatory human review.\n"
                    f"*PR:* <{pr_url}|{req.prTitle}>\n"
                    f"*Jira Issue:* `{jira_key_from_pr or 'N/A'}`\n"
                    f"*PR Author:* @{pr_author_github or 'unknown'}"
                )}},
                {"type": "section", "text": {"type": "mrkdwn", "text": (
                    f"*📊 Scorecard Summary:*\n"
                    f"• Complexity: `{scorecard.get('complexity', 'N/A')}/10`\n"
                    f"• Security Risk: `{scorecard.get('security_risk', 'N/A')}`\n"
                    f"• Conventions: `{scorecard.get('adherence_to_team_conventions', 'N/A')}`\n"
                    f"• Requirements Met: `{scorecard.get('requirements_fulfilled', 'N/A')}`"
                )}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*⚠️ Issues Found:*\n{reasons_text}"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": (
                    f"_Please review the code, give feedback to the developer, and ask them to raise a new PR "
                    f"once the issues are resolved. The Review Agent will automatically re-audit the next PR._"
                )}},
                {"type": "divider"}
            ]
            if pr_url:
                lead_blocks.append({"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "📂 View PR on GitHub"}, "url": pr_url}]})

            # Send to team lead channel/DM
            if team_lead_slack_id and not slack.mock_mode:
                import requests as req_mod
                r = req_mod.post(
                    "https://slack.com/api/chat.postMessage",
                    json={"channel": team_lead_slack_id, "text": lead_text, "blocks": lead_blocks},
                    headers={"Authorization": f"Bearer {slack.token}", "Content-Type": "application/json"}
                )
                rd = r.json()
                if rd.get("ok"):
                    print(f"✅ Team lead ({team_lead_slack_id}) notified for manual review of PR #{req.prNumber}")
                else:
                    print(f"⚠️ Failed to DM team lead: {rd.get('error')}. Posting to manager channel.")
                    slack.send_notification(text=lead_text, blocks=lead_blocks)
            else:
                # Also log to mock state if mock mode is on
                if slack.mock_mode and team_lead_slack_id:
                    slack._save_mock_state(slack._load_mock_state() + [{
                        "channel": team_lead_slack_id,
                        "text": lead_text,
                        "blocks": lead_blocks,
                        "timestamp": __import__('time').time()
                    }])
                    print(f"\n📢 [MOCK SLACK ALERT] To: {team_lead_slack_id}\nMessage: {lead_text}\n")
                else:
                    slack.send_notification(text=lead_text, blocks=lead_blocks)

            review_agent.log_agent_communication(
                sender="Review Agent",
                receiver="Team Lead",
                topic="Manual Review Escalation",
                content=f"PR #{req.prNumber} ('{req.prTitle}') escalated to team lead (Slack: {team_lead_slack_id or 'manager channel'}) for human review. {len(reasons)} issue(s) found."
            )

            # Track this PR in pending reviews state
            debt_state = review_agent._load_debt_state()
            pending = debt_state.setdefault("pending_reviews", {})
            
            # Clear other pending reviews with the same Jira key to avoid duplicates
            if jira_key_from_pr:
                keys_to_delete = [k for k, v in pending.items() if v.get("jira_key") == jira_key_from_pr and k != str(req.prNumber)]
                for k in keys_to_delete:
                    if k in pending:
                        del pending[k]

            pending[str(req.prNumber)] = {
                "pr_number": req.prNumber,
                "pr_title": req.prTitle,
                "jira_key": jira_key_from_pr,
                "task_description": task_description,
                "scorecard": scorecard,
                "reasons": reasons,
                "escalated_to": team_lead_slack_id or "manager channel",
                "pr_author": pr_author_github or "unknown"
            }
            review_agent._save_debt_state(debt_state)

        else:  # REJECT
            github.close_pr(req.prNumber)

            # Clear from pending reviews
            debt_state = review_agent._load_debt_state()
            pending = debt_state.setdefault("pending_reviews", {})
            if str(req.prNumber) in pending:
                del pending[str(req.prNumber)]
            if jira_key_from_pr:
                keys_to_delete = [k for k, v in pending.items() if v.get("jira_key") == jira_key_from_pr]
                for k in keys_to_delete:
                    if k in pending:
                        del pending[k]
            review_agent._save_debt_state(debt_state)

            review_agent.notify_pr_outcome(
                pr_number=req.prNumber,
                pr_title=req.prTitle,
                action="REJECTED",
                author_slack_id=author_slack_id,
                rejection_reasons=reasons if reasons else None
            )
            review_agent.log_agent_communication(
                sender="Review Agent",
                receiver="Communication Agent",
                topic="PR Rejected",
                content=f"PR #{req.prNumber} rejected and closed on GitHub. Author (Slack: {author_slack_id or 'N/A'}) notified with {len(reasons)} reason(s)."
            )

        return {
            "success": True,
            "audit": result,
            "autoMerged": auto_merged,
            "autoMergeMessage": auto_merge_message,
            "jiraKey": jira_key_from_pr,
            "taskDescriptionUsed": task_description[:200] if task_description else ""
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pr/resolve")
def resolve_pull_request(req: ResolvePRRequest):
    """
    Manual override resolution for blocked PRs (Approve & Merge, or Reject).
    """
    try:
        if req.action == "approve":
            gh_merge = github.merge_pr(req.prNumber)
            jira_done = jira.transition_issue(req.jiraKey, "Done")
            
            # Clear from pending reviews
            debt_state = review_agent._load_debt_state()
            pending = debt_state.setdefault("pending_reviews", {})
            if str(req.prNumber) in pending:
                del pending[str(req.prNumber)]
            if req.jiraKey:
                keys_to_delete = [k for k, v in pending.items() if v.get("jira_key") == req.jiraKey]
                for k in keys_to_delete:
                    if k in pending:
                        del pending[k]
            review_agent._save_debt_state(debt_state)

            review_agent.log_agent_communication(
                sender="Manager Human",
                receiver="Review Agent",
                topic="Manual Approval",
                content=f"PR #{req.prNumber} manually approved and merged by EM."
            )
            review_agent.log_agent_communication(
                sender="Review Agent",
                receiver="Execution Agent",
                topic="Jira Sync Completion",
                content=f"PR #{req.prNumber} manual merge completed. Transitioned Jira Issue '{req.jiraKey}' to status: DONE."
            )
            return {
                "success": True,
                "message": f"PR #{req.prNumber} manually merged, and Jira Issue {req.jiraKey} marked Completed!"
            }
        else:
            # Reject
            github.close_pr(req.prNumber)
            
            # Clear from pending reviews
            debt_state = review_agent._load_debt_state()
            pending = debt_state.setdefault("pending_reviews", {})
            if str(req.prNumber) in pending:
                del pending[str(req.prNumber)]
            if req.jiraKey:
                keys_to_delete = [k for k, v in pending.items() if v.get("jira_key") == req.jiraKey]
                for k in keys_to_delete:
                    if k in pending:
                        del pending[k]
            review_agent._save_debt_state(debt_state)

            review_agent.log_agent_communication(
                sender="Review Agent",
                receiver="Risk Agent",
                topic="PR Rejected",
                content=f"PR #{req.prNumber} rejected and closed due to quality audit failure."
            )
            return {
                "success": True,
                "message": f"PR #{req.prNumber} rejected and closed successfully."
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/slack/feed")
def get_slack_feed():
    """
    Fetches the manager Slack alerts.
    """
    return slack.get_messages()

@app.get("/api/agents/logs")
def get_agent_logs():
    """
    Fetches agent communication logs.
    """
    debt_state = review_agent._load_debt_state()
    return debt_state.get("cross_agent_logs", [])

@app.post("/api/slack/escalate")
def trigger_stale_escalation():
    """
    Scans PRs and triggers escalations to Slack.
    """
    stale_count = review_agent.detect_and_escalate_stale_prs()
    return {
        "success": True,
        "staleCountEscalated": stale_count
    }

@app.get("/api/reviews/pending")
def get_pending_reviews():
    """
    Returns PRs that the Review Agent flagged for MANUAL_REVIEW and are awaiting team lead action.
    """
    debt_state = review_agent._load_debt_state()
    pending = debt_state.get("pending_reviews", {})
    return {"pending": list(pending.values()), "count": len(pending)}

@app.delete("/api/reviews/pending/{pr_number}")
def clear_pending_review(pr_number: int):
    """
    Removes a PR from the pending reviews list (e.g., once the team lead has reviewed it).
    """
    debt_state = review_agent._load_debt_state()
    pending = debt_state.get("pending_reviews", {})
    key = str(pr_number)
    if key in pending:
        del pending[key]
        review_agent._save_debt_state(debt_state)
    return {"success": True, "message": f"PR #{pr_number} cleared from pending reviews."}

@app.get("/api/prs/open")
def get_open_prs():
    """
    Returns only OPEN (not merged, not closed) pull requests from GitHub.
    Enriches each PR with linked Jira task description for auto-review context.
    """
    try:
        all_prs = github.get_prs()
        open_prs = [p for p in all_prs if p.get("state") == "open"]
        
        enriched = []
        for pr in open_prs:
            jira_key = ""
            match = re.search(r"\b([a-zA-Z]+-\d+)\b", pr.get("title", ""))
            if match:
                jira_key = match.group(1).upper()
            elif pr.get("head"):
                match = re.search(r"\b([a-zA-Z]+-\d+)\b", pr["head"])
                if match:
                    jira_key = match.group(1).upper()
            
            # Fetch Jira task description for context display (without blocking)
            jira_task_summary = ""
            if jira_key:
                try:
                    details = jira.get_issue_details(jira_key)
                    if details:
                        jira_task_summary = details.get("description") or details.get("summary") or ""
                except Exception:
                    pass
            
            enriched.append({
                **pr,
                "jira_key": jira_key,
                "jira_task_summary": jira_task_summary[:200] if jira_task_summary else ""
            })
        
        return {"openPRs": enriched, "count": len(enriched)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
