from typing import Optional

from agents.execution.tools.slack_notify import SlackNotifier


class CommunicationAgent:
    """
    Formats stakeholder-facing messages and sends them through SlackNotifier.
    Existing planning, execution, review, and scheduling algorithms remain the
    source of truth for decisions; this agent only communicates outcomes.
    """

    def __init__(self, slack: Optional[SlackNotifier] = None):
        self.slack = slack or SlackNotifier()

    def _send_to_channel(self, channel: Optional[str], text: str, blocks: list[dict]) -> bool:
        original_channel = self.slack.channel
        if channel:
            self.slack.channel = channel
        try:
            return self.slack.send_notification(text=text, blocks=blocks)
        finally:
            self.slack.channel = original_channel

    def notify_task_assigned(
        self,
        *,
        assignee_slack_id: str,
        assignee_name: str,
        jira_key: str,
        title: str,
        description: str = "",
        team: str = "",
        moscow: str = "",
        github_issue_number: Optional[int] = None,
        action: str = "assigned",
    ) -> bool:
        """
        Sends one direct task assignment message to the assignee.
        Falls back to the manager channel when no assignee Slack ID is available.
        """
        target = assignee_slack_id or None
        action_label = "assigned to you" if action == "assigned" else "reassigned to you"
        github_line = f"\nGitHub Issue: #{github_issue_number}" if github_issue_number else ""
        priority_line = f"\nPriority: {moscow}" if moscow else ""
        team_line = f"\nTeam: {team}" if team else ""
        description_line = f"\n\n{description}" if description else ""

        text = f"Task {jira_key} was {action_label}: {title}"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "Task Assignment"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Hi {assignee_name or 'there'}, *{jira_key}* was {action_label}.\n"
                        f"*Task:* {title}"
                        f"{team_line}"
                        f"{priority_line}"
                        f"{github_line}"
                        f"{description_line}"
                    ),
                },
            },
        ]
        return self._send_to_channel(target, text=text, blocks=blocks)

    def notify_pr_assigned(
        self,
        *,
        assignee_slack_id: str,
        assignee_name: str,
        pr_number: int,
        pr_title: str,
        repo: str = "",
        reason: str = "",
    ) -> bool:
        """
        Sends one direct PR assignment/review request message.
        This is available for future PR-review routing without changing the
        Review Agent's scoring or merge algorithms.
        """
        repo_line = f"\nRepo: {repo}" if repo else ""
        reason_line = f"\nReason: {reason}" if reason else ""
        text = f"PR #{pr_number} was assigned to you for review: {pr_title}"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "PR Review Assignment"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Hi {assignee_name or 'there'}, *PR #{pr_number}* was assigned to you for review.\n"
                        f"*PR:* {pr_title}"
                        f"{repo_line}"
                        f"{reason_line}"
                    ),
                },
            },
        ]
        return self._send_to_channel(assignee_slack_id or None, text=text, blocks=blocks)

    def build_manager_digest(
        self,
        *,
        stats: dict,
        workloads: dict,
        pending_reviews: list[dict],
        recent_logs: list[dict],
    ) -> dict:
        """
        Builds one manager-level digest. This intentionally summarizes current
        system state instead of sending event-level manager spam.
        """
        active_prs = stats.get("activePrsCount", 0)
        merged_prs = stats.get("mergedPrsCount", 0)
        stale_prs = stats.get("stalePrsCount", 0)
        pending_count = len(pending_reviews)
        jira_workloads = workloads.get("jiraWorkloads", [])
        reviewer_stats = workloads.get("reviewerStats", [])

        total_active_tasks = sum(int(w.get("activeTasks", 0) or 0) for w in jira_workloads)
        overloaded = [w for w in jira_workloads if int(w.get("activeTasks", 0) or 0) >= 3]
        busy_reviewers = [r for r in reviewer_stats if int(r.get("pending", 0) or 0) > 0]

        attention_items = []
        if stale_prs:
            attention_items.append(f"{stale_prs} stale PR(s) need attention.")
        if pending_count:
            attention_items.append(f"{pending_count} PR(s) are waiting for manual review.")
        if overloaded:
            names = ", ".join(w.get("name", "Unknown") for w in overloaded[:3])
            attention_items.append(f"High task load detected for: {names}.")
        if busy_reviewers:
            names = ", ".join(r.get("name", "Unknown") for r in busy_reviewers[:3])
            attention_items.append(f"Review queue is active for: {names}.")
        if not attention_items:
            attention_items.append("No urgent review or workload issues detected.")

        workload_lines = []
        for item in jira_workloads[:8]:
            workload_lines.append(
                f"• {item.get('name', 'Unknown')} ({item.get('team', 'N/A')}): "
                f"{item.get('activeTasks', 0)} active task(s)"
            )
        if not workload_lines:
            workload_lines.append("• No active Jira workload data available.")

        recent_lines = []
        for log in recent_logs[:5]:
            recent_lines.append(
                f"• {log.get('sender', 'Agent')} → {log.get('receiver', 'System')}: "
                f"{log.get('topic', 'Update')}"
            )
        if not recent_lines:
            recent_lines.append("• No recent cross-agent updates.")

        text = (
            "Engineering Manager Digest: "
            f"{active_prs} open PR(s), {merged_prs} merged PR(s), "
            f"{stale_prs} stale PR(s), {pending_count} manual review(s), "
            f"{total_active_tasks} active task(s)."
        )

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "Engineering Manager Digest"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*PR Health*\n"
                        f"• Open: `{active_prs}`\n"
                        f"• Merged: `{merged_prs}`\n"
                        f"• Stale: `{stale_prs}`\n"
                        f"• Manual review pending: `{pending_count}`"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Task Load*\n"
                        f"• Active Jira tasks: `{total_active_tasks}`\n"
                        + "\n".join(workload_lines)
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Attention*\n" + "\n".join(f"• {item}" for item in attention_items),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Recent Agent Updates*\n" + "\n".join(recent_lines),
                },
            },
        ]

        return {
            "text": text,
            "blocks": blocks,
            "summary": {
                "activePrs": active_prs,
                "mergedPrs": merged_prs,
                "stalePrs": stale_prs,
                "pendingManualReviews": pending_count,
                "activeTasks": total_active_tasks,
                "attentionItems": attention_items,
            },
        }

    def send_manager_digest(
        self,
        *,
        stats: dict,
        workloads: dict,
        pending_reviews: list[dict],
        recent_logs: list[dict],
    ) -> dict:
        digest = self.build_manager_digest(
            stats=stats,
            workloads=workloads,
            pending_reviews=pending_reviews,
            recent_logs=recent_logs,
        )
        sent = self.slack.send_notification(text=digest["text"], blocks=digest["blocks"])
        return {
            "success": sent,
            "message": "Manager digest sent." if sent else "Manager digest failed to send.",
            "digest": digest,
        }
