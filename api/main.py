import os
import re
import sys
import yaml
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, UploadFile, File
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
from agents.planning.prd_parser import process_and_enrich_prd
from agents.planning.dag import detect_cycles_dfs, topological_sort_kahn
from agents.planning.pert import run_critical_path_method, calculate_sprint_confidence

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
    
    # Group engineers by team_name
    grouped_teams = {}
    for eng in engineers:
        team_name = eng.get("team_name", "FRONTEND").strip().upper()
        if team_name not in grouped_teams:
            grouped_teams[team_name] = []
        
        # Clean engineer fields to serialize
        eng_data = {
            "name": eng["name"],
            "jira_account_id": eng["jira_account_id"],
            "slack_user_id": eng["slack_user_id"],
            "github_username": eng.get("github_username", ""),
            "is_team_lead": eng.get("is_team_lead", False)
        }
        grouped_teams[team_name].append(eng_data)
        
    teams_list = []
    # If no engineers configured, default to a FRONTEND team
    if not grouped_teams:
        grouped_teams["FRONTEND"] = []

    for team_name, engs in grouped_teams.items():
        teams_list.append({
            "name": team_name,
            "slack_channel": f"{team_name.lower()}-alerts" if team_name in ["BACKEND", "FRONTEND"] else "",
            "team_lead_slack_id": team_lead_slack_id,
            "engineers": engs
        })
        
    if config_path.exists():
        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
        
    data["wip_limit"] = wip_limit
    data["sprint_duration_days"] = data.get("sprint_duration_days", 20)
    data["jira_project_key"] = jira_project_key
    data["confidence_threshold"] = data.get("confidence_threshold", 0.60)
    data["teams"] = teams_list

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
    team_name: Optional[str] = "FRONTEND"

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
        
        github_status = f"#{github_issue.get('number')}" if github_issue else f"N/A (Error: {github.last_error})" if github.last_error else "N/A"
        
        # 3. Log cross-agent communication
        review_agent.log_agent_communication(
            sender="Execution Agent",
            receiver="GitHub",
            topic="Issue Created",
            content=f"Task '{req.title}' created as Jira issue {jira_key} and GitHub issue {github_status}. Assigned to {req.assigneeName}."
        )
        
        return {
            "success": True,
            "jiraKey": jira_key,
            "jiraUrl": f"{jira.base_url}/browse/{jira_key}",
            "githubIssue": github_issue,
            "message": f"Task created! Jira: {jira_key}, GitHub Issue: {github_status}"
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
        
        # Build mapping of jira_account_id -> github_username
        jira_to_gh = {}
        for team in config.teams:
            for eng in team.engineers:
                if eng.jira_account_id and eng.github_username:
                    jira_to_gh[eng.jira_account_id] = eng.github_username
        
        # Enrich Jira issues with GitHub issue links
        enriched = []
        for issue in issues:
            gh_match = next(
                (g for g in github_issues if f"[{issue['key']}]" in (g.get("title") or "")),
                None
            )
            
            # Auto-assign GitHub issue if it was previously created as unassigned (e.g. pending invite acceptance)
            target_gh_user = jira_to_gh.get(issue.get("assignee_id"))
            if gh_match and target_gh_user and not gh_match.get("assignee"):
                print(f"🔄 Attempting to assign GitHub Issue #{gh_match['number']} to accepted collaborator '{target_gh_user}'...")
                success = github.assign_issue(gh_match["number"], target_gh_user, invite_collaborator=False)
                if success:
                    # Update local match representation so it's returned correctly to the frontend
                    gh_match["assignee"] = target_gh_user
            
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
    Assigns a Jira issue to a team member and attempts to sync the assignment to GitHub.
    """
    try:
        # 1. Assign in Jira
        url = f"{jira.base_url}/rest/api/3/issue/{req.jiraKey}/assignee"
        payload = {"accountId": req.assigneeJiraId}
        resp = __import__('requests').put(url, json=payload, auth=jira.auth, headers=jira.headers)
        if resp.status_code not in [204, 200, 201]:
            raise HTTPException(status_code=400, detail=f"Failed to assign in Jira: {resp.text}")

        # 2. Try to sync to GitHub
        target_gh_user = None
        for team in config.teams:
            for eng in team.engineers:
                if eng.jira_account_id == req.assigneeJiraId:
                    target_gh_user = eng.github_username
                    break
            if target_gh_user:
                break
        
        gh_message = ""
        if target_gh_user:
            github_issues = github.get_issues()
            gh_match = next(
                (g for g in github_issues if f"[{req.jiraKey}]" in (g.get("title") or "")),
                None
            )
            if gh_match:
                success = github.assign_issue(gh_match["number"], target_gh_user)
                if success:
                    gh_message = f" and GitHub issue #{gh_match['number']} assigned to @{target_gh_user}"
                else:
                    gh_message = f" (GitHub collaborator invite sent to @{target_gh_user}; issue will assign automatically once accepted)"

        review_agent.log_agent_communication(
            sender="Execution Agent",
            receiver="Jira/GitHub",
            topic="Issue Assigned",
            content=f"Jira issue {req.jiraKey} assigned to account ID {req.assigneeJiraId}{gh_message}."
        )
        return {"success": True, "message": f"Issue {req.jiraKey} assigned successfully{gh_message}."}
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
        team_lead_slack_id = getattr(config.teams[0], "team_lead_slack_id", "")
        for team in config.teams:
            for eng in team.engineers:
                engineers_data.append({
                    "name": eng.name,
                    "jira_account_id": eng.jira_account_id,
                    "slack_user_id": eng.slack_user_id,
                    "github_username": eng.github_username,
                    "is_team_lead": getattr(eng, "is_team_lead", False),
                    "team_name": team.name
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
                "is_team_lead": eng.is_team_lead,
                "team_name": (eng.team_name or "FRONTEND").strip().upper()
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

CURRENT_PLANNING_DRAFT = None

class ParsePRDRequest(BaseModel):
    prd: str

class TaskApprovalItem(BaseModel):
    id: str
    feature_name: str
    title: str
    description: str
    acceptance_criteria: List[str]
    team_label: str
    moscow_tier: str
    o: float
    m: float
    p: float
    depends_on_ids: List[str]
    assigned_engineer_name: str
    assigned_engineer_jira_id: str
    assigned_engineer_github_username: str

class ApprovePlanningRequest(BaseModel):
    tasks: List[TaskApprovalItem]

def simulate_planning(topo_tasks, config):
    wip_monitor = review_agent.wip_monitor
    current_wip = wip_monitor.get_active_wip_counts(config.jira_project_key)
    
    team_map = config.get_team_mapping()
    team_pointers = {team.name.upper(): 0 for team in config.teams}
    
    assigned_tasks = []
    for task in topo_tasks:
        target_team_name = task.team_label.upper()
        if target_team_name not in team_map:
            target_team_name = config.teams[0].name.upper() if config.teams else "FRONTEND"
        
        assigned_engineer = None
        if target_team_name in team_map:
            team_info = team_map[target_team_name]
            engineers = team_info.engineers
            
            if engineers:
                num_engineers = len(engineers)
                start_index = team_pointers[target_team_name]
                
                for i in range(num_engineers):
                    eval_idx = (start_index + i) % num_engineers
                    candidate = engineers[eval_idx]
                    candidate_wip = current_wip.get(candidate.jira_account_id, 0)
                    
                    if candidate_wip < config.wip_limit:
                        assigned_engineer = candidate
                        team_pointers[target_team_name] = (eval_idx + 1) % num_engineers
                        current_wip[candidate.jira_account_id] = candidate_wip + 1
                        break
                
                if not assigned_engineer:
                    assigned_engineer = engineers[start_index]
                    team_pointers[target_team_name] = (start_index + 1) % num_engineers
        
        assigned_tasks.append({
            "id": task.id,
            "feature_name": task.feature_name,
            "title": task.title,
            "description": task.description,
            "acceptance_criteria": task.acceptance_criteria,
            "team_label": target_team_name,
            "moscow_tier": task.moscow_tier,
            "o": task.o,
            "m": task.m,
            "p": task.p,
            "depends_on_ids": task.depends_on_ids,
            "assigned_engineer_name": assigned_engineer.name if assigned_engineer else "Unassigned",
            "assigned_engineer_jira_id": assigned_engineer.jira_account_id if assigned_engineer else "",
            "assigned_engineer_github_username": assigned_engineer.github_username if assigned_engineer else ""
        })
    return assigned_tasks

@app.post("/api/planning/upload-pdf")
async def upload_prd_pdf(file: UploadFile = File(...)):
    try:
        from pypdf import PdfReader
        import io

        contents = await file.read()
        reader = PdfReader(io.BytesIO(contents))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        return {
            "success": True,
            "text": text.strip()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")

@app.post("/api/planning/draft")
def compile_planning_draft(req: ParsePRDRequest):
    global CURRENT_PLANNING_DRAFT
    try:
        # Load latest config
        load_dotenv(override=True)
        current_cfg = load_config()

        # 1. Parse and enrich
        enriched_tasks = process_and_enrich_prd(req.prd)
        
        # 2. Cycle detection
        has_cycles = detect_cycles_dfs(enriched_tasks)
        if has_cycles:
            return {
                "success": False,
                "error": "Cyclic dependencies detected in PRD! Please resolve cycle paths.",
                "hasCycles": True,
                "tasks": []
            }
            
        # 3. Topological sorting
        sorted_tasks = topological_sort_kahn(enriched_tasks)
        
        # 4. Critical Path Method & PERT math
        metrics, cp_ids, duration, variance = run_critical_path_method(enriched_tasks, sorted_tasks)
        confidence = calculate_sprint_confidence(duration, variance, current_cfg.sprint_duration_days)
        
        # 5. Round-Robin simulated allocation
        simulated_tasks = simulate_planning(sorted_tasks, current_cfg)
        
        # Cache draft
        CURRENT_PLANNING_DRAFT = simulated_tasks
        
        return {
            "success": True,
            "duration": round(duration, 2),
            "confidence": round(confidence * 100, 1),
            "criticalPathTaskIds": cp_ids,
            "hasCycles": False,
            "tasks": simulated_tasks
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/planning/approve")
def approve_planning_dispatch(req: ApprovePlanningRequest):
    try:
        planning_id_to_jira_key = {}
        dispatched_details = []
        github_warnings = []
        
        # Process sequentially following their dependency orders
        for task in req.tasks:
            assignee_id = task.assigned_engineer_jira_id if task.assigned_engineer_jira_id else None
            assignee_name = task.assigned_engineer_name if task.assigned_engineer_name else "Unassigned"
            
            # Create Jira issue
            jira_key = jira.create_ticket(
                title=task.title,
                description=task.description,
                team=task.team_label,
                moscow=task.moscow_tier,
                assignee_id=assignee_id
            )
            
            planning_id_to_jira_key[task.id] = jira_key
            
            # Create GitHub issue
            github_issue = github.create_issue(
                title=f"[{jira_key}] {task.title}",
                body=f"**Jira Issue:** [{jira_key}]({jira.base_url}/browse/{jira_key})\n\n**Description:**\n{task.description}\n\n**Team:** {task.team_label}\n**MoSCoW Priority:** {task.moscow_tier}\n**Assigned To:** {assignee_name}",
                assignee=task.assigned_engineer_github_username if task.assigned_engineer_github_username else None
            )
            
            if not github_issue and github.last_error:
                github_warnings.append(f"Task '{task.title}': {github.last_error}")
            
            dispatched_details.append({
                "id": task.id,
                "jiraKey": jira_key,
                "githubIssueNumber": github_issue.get("number") if github_issue else None
            })
            
            # Link dependencies inside Jira
            for dep_id in task.depends_on_ids:
                if dep_id in planning_id_to_jira_key:
                    parent_jira_key = planning_id_to_jira_key[dep_id]
                    try:
                        jira.create_dependency_link(outward_key=parent_jira_key, inward_key=jira_key)
                    except Exception as le:
                        print(f"⚠️ Dependency link failed: {parent_jira_key} -> {jira_key}: {str(le)}")
                        
            # Log cross-agent communication
            review_agent.log_agent_communication(
                sender="Planning Agent",
                receiver="Jira/GitHub",
                topic="Sprint Dispatch",
                content=f"Task '{task.title}' created as Jira issue {jira_key} and assigned to {assignee_name}."
            )
            
        success_msg = f"Successfully created {len(req.tasks)} Jira issues!"
        if github_warnings:
            success_msg += " WARNING: GitHub issues could not be created: " + " | ".join(github_warnings)
        else:
            success_msg += " GitHub issues successfully synced."

        return {
            "success": True,
            "message": success_msg,
            "dispatched": dispatched_details
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
