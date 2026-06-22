import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.communication.agent import CommunicationAgent
from agents.execution.tools.slack_notify import SlackNotifier


class CommunicationAgentTests(unittest.TestCase):
    def test_notify_task_assigned_sends_direct_mock_slack_message(self):
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
                    slack = SlackNotifier()
                    agent = CommunicationAgent(slack=slack)

                    sent = agent.notify_task_assigned(
                        assignee_slack_id="U_ASSIGNEE_1",
                        assignee_name="Ayush Mittal",
                        jira_key="KAN-123",
                        title="Build task notifications",
                        description="Send Slack messages when tasks are assigned.",
                        team="BACKEND",
                        moscow="MUST",
                        github_issue_number=101,
                    )

                self.assertTrue(sent)
                messages = json.loads(Path("mock_slack_messages.json").read_text())
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["channel"], "U_ASSIGNEE_1")
                self.assertIn("KAN-123", messages[0]["text"])
                block_text = messages[0]["blocks"][1]["text"]["text"]
                self.assertIn("Build task notifications", block_text)
                self.assertIn("GitHub Issue: #101", block_text)
            finally:
                os.chdir(original_cwd)

    def test_notify_task_assigned_falls_back_to_manager_channel_without_slack_id(self):
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
                    slack = SlackNotifier()
                    agent = CommunicationAgent(slack=slack)

                    sent = agent.notify_task_assigned(
                        assignee_slack_id="",
                        assignee_name="Unassigned",
                        jira_key="KAN-124",
                        title="Fallback notification",
                    )

                self.assertTrue(sent)
                messages = json.loads(Path("mock_slack_messages.json").read_text())
                self.assertEqual(messages[0]["channel"], "#manager-test")
                self.assertIn("KAN-124", messages[0]["text"])
            finally:
                os.chdir(original_cwd)

    def test_send_manager_digest_writes_one_summary_message(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                with patch.dict(
                    os.environ,
                    {
                        "SLACK_MOCK": "true",
                        "SLACK_MANAGER_CHANNEL": "#engineering-manager",
                        "SLACK_BOT_TOKEN": "",
                    },
                    clear=False,
                ):
                    slack = SlackNotifier()
                    agent = CommunicationAgent(slack=slack)
                    result = agent.send_manager_digest(
                        stats={
                            "activePrsCount": 2,
                            "mergedPrsCount": 5,
                            "stalePrsCount": 1,
                        },
                        workloads={
                            "jiraWorkloads": [
                                {"name": "Ayush Mittal", "team": "BACKEND", "activeTasks": 3}
                            ],
                            "reviewerStats": [
                                {"name": "Ayush Mittal", "pending": 1, "completed": 4}
                            ],
                        },
                        pending_reviews=[{"pr_number": 42}],
                        recent_logs=[
                            {
                                "sender": "Review Agent",
                                "receiver": "Communication Agent",
                                "topic": "PR Flagged",
                            }
                        ],
                    )

                self.assertTrue(result["success"])
                self.assertEqual(result["digest"]["summary"]["activePrs"], 2)
                self.assertEqual(result["digest"]["summary"]["pendingManualReviews"], 1)
                messages = json.loads(Path("mock_slack_messages.json").read_text())
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["channel"], "#engineering-manager")
                self.assertIn("Engineering Manager Digest", messages[0]["text"])
                self.assertEqual(messages[0]["blocks"][0]["type"], "header")
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
