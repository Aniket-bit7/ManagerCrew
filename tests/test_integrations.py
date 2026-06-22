import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api import main as api_main
from agents.execution.tools.slack_notify import SlackNotifier


class FakeJira:
    def __init__(self):
        self.base_url = "https://jira.example.test"
        self.mock_mode = True
        self.auth = None
        self.headers = {}
        self.created = []
        self.report_issues = [
            {"key": "KAN-200", "status": "Done", "statusCategory": "done", "assignee_id": "jira-1"},
        ]

    def create_ticket(self, title, description, team, moscow, assignee_id=None):
        self.created.append(
            {
                "title": title,
                "description": description,
                "team": team,
                "moscow": moscow,
                "assignee_id": assignee_id,
            }
        )
        self.report_issues.append(
            {
                "key": "KAN-123",
                "summary": title,
                "status": "To Do",
                "statusCategory": "new",
                "assignee_id": assignee_id,
            }
        )
        return "KAN-123"

    def get_project_issues_for_report(self, project_key):
        return self.report_issues


class FakeGitHub:
    def __init__(self):
        self.last_error = None
        self.created_issues = []
        self.assigned_issues = []
        self.issues = [
            {
                "number": 101,
                "title": "[KAN-123] Build alerts",
                "assignee": None,
                "state": "open",
            }
        ]

    def create_issue(self, title, body, assignee=None):
        issue = {
            "number": 101,
            "title": title,
            "body": body,
            "assignee": assignee,
            "state": "open",
            "html_url": "https://github.example.test/issues/101",
        }
        self.created_issues.append(issue)
        self.issues = [issue]
        return issue

    def get_issues(self):
        return self.issues

    def assign_issue(self, issue_number, assignee):
        self.assigned_issues.append((issue_number, assignee))
        for issue in self.issues:
            if issue["number"] == issue_number:
                issue["assignee"] = assignee
        return True

    def get_prs(self):
        return [
            {"number": 201, "state": "open", "assignee": "roboayushh"},
            {"number": 202, "state": "merged", "assignee": "roboayushh"},
        ]


class FakeReviewAgent:
    def __init__(self):
        self.logs = []

    def log_agent_communication(self, **kwargs):
        self.logs.append(kwargs)

    def _load_debt_state(self):
        return {
            "pending_reviews": {
                "201": {"pr_author": "roboayushh"},
            },
            "cross_agent_logs": self.logs,
        }


class FakeCommunicationAgent:
    def __init__(self):
        self.task_notifications = []
        self.manager_digests = []

    def notify_task_assigned(self, **kwargs):
        self.task_notifications.append(kwargs)
        return True

    def build_manager_digest(self, **kwargs):
        return {"text": "preview", "blocks": [], "summary": {"activePrs": 1}}

    def send_manager_digest(self, **kwargs):
        self.manager_digests.append(kwargs)
        return {
            "success": True,
            "message": "Manager digest sent.",
            "digest": self.build_manager_digest(**kwargs),
        }


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            "jira": api_main.jira,
            "github": api_main.github,
            "review_agent": api_main.review_agent,
            "communication_agent": api_main.communication_agent,
            "config": api_main.config,
        }
        self.fake_jira = FakeJira()
        self.fake_github = FakeGitHub()
        self.fake_review_agent = FakeReviewAgent()
        self.fake_communication_agent = FakeCommunicationAgent()
        api_main.jira = self.fake_jira
        api_main.github = self.fake_github
        api_main.review_agent = self.fake_review_agent
        api_main.communication_agent = self.fake_communication_agent
        api_main.config = SimpleNamespace(
            jira_project_key="KAN",
            teams=[
                SimpleNamespace(
                    name="BACKEND",
                    engineers=[
                        SimpleNamespace(
                            name="Ayush Mittal",
                            jira_account_id="jira-1",
                            github_username="roboayushh",
                            slack_user_id="U123",
                        )
                    ],
                )
            ]
        )

    def tearDown(self):
        api_main.jira = self.originals["jira"]
        api_main.github = self.originals["github"]
        api_main.review_agent = self.originals["review_agent"]
        api_main.communication_agent = self.originals["communication_agent"]
        api_main.config = self.originals["config"]

    def test_create_task_creates_jira_ticket_github_issue_and_agent_log(self):
        response = api_main.create_task(
            api_main.CreateTaskRequest(
                title="Build alerts",
                description="Send manager alerts for blocked work",
                team="BACKEND",
                moscow="MUST",
                assigneeName="Ayush Mittal",
                assigneeJiraId="jira-1",
                assigneeGithubId="roboayushh",
            )
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["jiraKey"], "KAN-123")
        self.assertEqual(self.fake_jira.created[0]["assignee_id"], "jira-1")
        self.assertEqual(self.fake_github.created_issues[0]["assignee"], "roboayushh")
        self.assertIn("[KAN-123] Build alerts", self.fake_github.created_issues[0]["title"])
        self.assertEqual(self.fake_review_agent.logs[0]["topic"], "Issue Created")
        self.assertEqual(len(self.fake_communication_agent.task_notifications), 1)
        self.assertEqual(self.fake_communication_agent.task_notifications[0]["assignee_slack_id"], "U123")
        self.assertEqual(self.fake_communication_agent.task_notifications[0]["jira_key"], "KAN-123")

    def test_assign_task_in_mock_mode_syncs_matching_github_issue(self):
        with patch("requests.put", side_effect=AssertionError("mock Jira should not call requests.put")):
            response = api_main.assign_task(
                api_main.AssignTaskRequest(jiraKey="KAN-123", assigneeJiraId="jira-1")
            )

        self.assertTrue(response["success"])
        self.assertIn("GitHub issue #101 assigned to @roboayushh", response["message"])
        self.assertEqual(self.fake_github.assigned_issues, [(101, "roboayushh")])
        self.assertEqual(len(self.fake_communication_agent.task_notifications), 1)
        self.assertEqual(self.fake_communication_agent.task_notifications[0]["action"], "reassigned")
        self.assertEqual(self.fake_review_agent.logs[-1]["topic"], "Issue Assigned")

    def test_send_manager_digest_uses_single_communication_agent_call(self):
        fake_inputs = {
            "stats": {"activePrsCount": 1, "mergedPrsCount": 2, "stalePrsCount": 0},
            "workloads": {"jiraWorkloads": [], "reviewerStats": []},
            "pending_reviews": [],
            "recent_logs": [],
        }
        with patch.object(api_main, "build_manager_digest_inputs", return_value=fake_inputs):
            response = api_main.send_manager_digest()

        self.assertTrue(response["success"])
        self.assertEqual(response["message"], "Manager digest sent.")
        self.assertEqual(self.fake_communication_agent.manager_digests, [fake_inputs])

    def test_team_performance_report_returns_task_and_pr_metrics(self):
        response = api_main.get_team_performance_report()

        self.assertEqual(response["teamSummary"]["assignedTasks"], 1)
        self.assertEqual(response["teamSummary"]["completedTasks"], 1)
        self.assertEqual(response["teamSummary"]["openPrs"], 1)
        self.assertEqual(response["teamSummary"]["mergedPrs"], 1)
        self.assertEqual(response["members"][0]["completionRate"], 100.0)
        self.assertEqual(response["members"][0]["manualReviews"], 1)

    def test_goal_pipeline_create_assign_digest_and_report(self):
        create_response = api_main.create_task(
            api_main.CreateTaskRequest(
                title="Pipeline task",
                description="Exercise communication and reporting together.",
                team="BACKEND",
                moscow="MUST",
                assigneeName="Ayush Mittal",
                assigneeJiraId="jira-1",
                assigneeGithubId="roboayushh",
            )
        )
        assign_response = api_main.assign_task(
            api_main.AssignTaskRequest(jiraKey=create_response["jiraKey"], assigneeJiraId="jira-1")
        )

        fake_inputs = {
            "stats": {"activePrsCount": 1, "mergedPrsCount": 1, "stalePrsCount": 1},
            "workloads": {
                "jiraWorkloads": [{"name": "Ayush Mittal", "team": "BACKEND", "activeTasks": 1}],
                "reviewerStats": [],
            },
            "pending_reviews": [],
            "recent_logs": [],
        }
        with patch.object(api_main, "build_manager_digest_inputs", return_value=fake_inputs):
            digest_response = api_main.send_manager_digest()

        report_response = api_main.get_team_performance_report()

        self.assertTrue(create_response["success"])
        self.assertTrue(assign_response["success"])
        self.assertTrue(digest_response["success"])
        self.assertEqual(len(self.fake_communication_agent.task_notifications), 2)
        self.assertEqual(len(self.fake_communication_agent.manager_digests), 1)
        self.assertEqual(report_response["teamSummary"]["assignedTasks"], 2)
        self.assertEqual(report_response["teamSummary"]["completedTasks"], 1)
        self.assertEqual(report_response["members"][0]["completionRate"], 50.0)


class SlackAndEnvTests(unittest.TestCase):
    def test_slack_mock_send_notification_writes_local_feed(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                with patch.dict(
                    os.environ,
                    {
                        "SLACK_MOCK": "true",
                        "SLACK_MANAGER_CHANNEL": "#manager-test",
                        "SLACK_BOT_TOKEN": "",
                    },
                    clear=False,
                ):
                    notifier = SlackNotifier()
                    sent = notifier.send_notification(
                        "Task KAN-123 needs review",
                        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "hello"}}],
                    )

                self.assertTrue(sent)
                messages = json.loads(Path("mock_slack_messages.json").read_text())
                self.assertEqual(messages[0]["channel"], "#manager-test")
                self.assertEqual(messages[0]["text"], "Task KAN-123 needs review")
                self.assertEqual(messages[0]["blocks"][0]["type"], "section")
            finally:
                os.chdir(original_cwd)

    def test_update_env_file_updates_existing_values_and_adds_new_keys(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                Path(".env").write_text("SLACK_MOCK=true\nOLD_VALUE=keep\n")

                api_main.update_env_file(
                    {
                        "SLACK_MOCK": "false",
                        "JIRA_BASE_URL": "https://jira.example.test",
                    }
                )

                env_text = Path(".env").read_text()
                self.assertIn("SLACK_MOCK=false", env_text)
                self.assertIn("OLD_VALUE=keep", env_text)
                self.assertIn("JIRA_BASE_URL=https://jira.example.test", env_text)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
