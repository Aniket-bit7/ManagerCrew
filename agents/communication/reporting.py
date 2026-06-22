def bucket_jira_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"done", "completed", "resolved", "closed"}:
        return "done"
    if normalized in {"in progress", "review", "code review", "testing", "qa"}:
        return "in_progress"
    return "to_do"


def bucket_jira_status_category(status_category: str, status: str = "") -> str:
    normalized = (status_category or "").strip().lower()
    if normalized == "done":
        return "done"
    if normalized == "indeterminate":
        return "in_progress"
    if normalized == "new":
        return "to_do"
    return bucket_jira_status(status)


def _percent(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round((part / whole) * 100, 1)


def build_team_performance_report(config, jira_issues: list[dict], prs: list[dict], debt_state: dict) -> dict:
    members = {}
    github_to_jira = {}

    for team in config.teams:
        for eng in team.engineers:
            members[eng.jira_account_id] = {
                "name": eng.name,
                "team": team.name,
                "jiraAccountId": eng.jira_account_id,
                "githubUsername": eng.github_username,
                "assignedTasks": 0,
                "completedTasks": 0,
                "inProgressTasks": 0,
                "todoTasks": 0,
                "completionRate": 0.0,
                "openPrs": 0,
                "mergedPrs": 0,
                "closedPrs": 0,
                "stalePrs": 0,
                "manualReviews": 0,
                "wipLoad": 0,
            }
            if eng.github_username:
                github_to_jira[eng.github_username.lower()] = eng.jira_account_id

    unassigned = {
        "name": "Unassigned",
        "team": "N/A",
        "jiraAccountId": "",
        "githubUsername": "",
        "assignedTasks": 0,
        "completedTasks": 0,
        "inProgressTasks": 0,
        "todoTasks": 0,
        "completionRate": 0.0,
        "openPrs": 0,
        "mergedPrs": 0,
        "closedPrs": 0,
        "stalePrs": 0,
        "manualReviews": 0,
        "wipLoad": 0,
    }

    def row_for_jira_id(jira_id: str):
        if jira_id and jira_id in members:
            return members[jira_id]
        return unassigned

    for issue in jira_issues:
        row = row_for_jira_id(issue.get("assignee_id") or issue.get("assigneeId") or "")
        bucket = bucket_jira_status_category(issue.get("statusCategory", ""), issue.get("status", ""))
        row["assignedTasks"] += 1
        if bucket == "done":
            row["completedTasks"] += 1
        elif bucket == "in_progress":
            row["inProgressTasks"] += 1
            row["wipLoad"] += 1
        else:
            row["todoTasks"] += 1
            row["wipLoad"] += 1

    for pr in prs:
        assignee = (pr.get("assignee") or "").lower()
        row = row_for_jira_id(github_to_jira.get(assignee, ""))
        state = (pr.get("state") or "").lower()
        if state == "merged":
            row["mergedPrs"] += 1
        elif state == "closed":
            row["closedPrs"] += 1
        else:
            row["openPrs"] += 1
            if int(pr.get("number", 0) or 0) % 2 == 1:
                row["stalePrs"] += 1

    pending_reviews = debt_state.get("pending_reviews", {}) or {}
    for pending in pending_reviews.values():
        author = (pending.get("pr_author") or "").lower()
        row = row_for_jira_id(github_to_jira.get(author, ""))
        row["manualReviews"] += 1

    rows = list(members.values())
    if unassigned["assignedTasks"] or unassigned["openPrs"] or unassigned["mergedPrs"] or unassigned["manualReviews"]:
        rows.append(unassigned)

    for row in rows:
        row["completionRate"] = _percent(row["completedTasks"], row["assignedTasks"])

    team_summary = {
        "assignedTasks": sum(row["assignedTasks"] for row in rows),
        "completedTasks": sum(row["completedTasks"] for row in rows),
        "inProgressTasks": sum(row["inProgressTasks"] for row in rows),
        "todoTasks": sum(row["todoTasks"] for row in rows),
        "completionRate": 0.0,
        "openPrs": sum(row["openPrs"] for row in rows),
        "mergedPrs": sum(row["mergedPrs"] for row in rows),
        "closedPrs": sum(row["closedPrs"] for row in rows),
        "stalePrs": sum(row["stalePrs"] for row in rows),
        "pendingManualReviews": sum(row["manualReviews"] for row in rows),
        "wipLoad": sum(row["wipLoad"] for row in rows),
    }
    team_summary["completionRate"] = _percent(team_summary["completedTasks"], team_summary["assignedTasks"])

    return {
        "teamSummary": team_summary,
        "members": rows,
    }
