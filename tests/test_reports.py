import unittest
from types import SimpleNamespace

from agents.communication.reporting import (
    bucket_jira_status,
    bucket_jira_status_category,
    build_team_performance_report,
)


class TeamPerformanceReportTests(unittest.TestCase):
    def test_bucket_jira_status(self):
        self.assertEqual(bucket_jira_status("Done"), "done")
        self.assertEqual(bucket_jira_status("Code Review"), "in_progress")
        self.assertEqual(bucket_jira_status("To Do"), "to_do")
        self.assertEqual(bucket_jira_status("Backlog"), "to_do")

    def test_bucket_jira_status_category(self):
        self.assertEqual(bucket_jira_status_category("done", "Weird Custom Done"), "done")
        self.assertEqual(bucket_jira_status_category("indeterminate", "Custom Review"), "in_progress")
        self.assertEqual(bucket_jira_status_category("new", "Selected For Development"), "to_do")
        self.assertEqual(bucket_jira_status_category("", "Testing"), "in_progress")

    def test_build_team_performance_report_calculates_member_metrics(self):
        config = SimpleNamespace(
            teams=[
                SimpleNamespace(
                    name="BACKEND",
                    engineers=[
                        SimpleNamespace(
                            name="Ayush Mittal",
                            jira_account_id="jira-1",
                            github_username="roboayushh",
                        )
                    ],
                )
            ]
        )
        jira_issues = [
            {"status": "Resolved", "statusCategory": "done", "assignee_id": "jira-1"},
            {"status": "Custom Build", "statusCategory": "indeterminate", "assignee_id": "jira-1"},
            {"status": "Backlog", "statusCategory": "new", "assignee_id": "jira-1"},
        ]
        prs = [
            {"number": 201, "state": "open", "assignee": "roboayushh"},
            {"number": 202, "state": "merged", "assignee": "roboayushh"},
            {"number": 203, "state": "closed", "assignee": "roboayushh"},
        ]
        debt_state = {
            "pending_reviews": {
                "201": {"pr_author": "roboayushh"},
            }
        }

        report = build_team_performance_report(config, jira_issues, prs, debt_state)

        summary = report["teamSummary"]
        member = report["members"][0]
        self.assertEqual(summary["assignedTasks"], 3)
        self.assertEqual(summary["completedTasks"], 1)
        self.assertEqual(summary["completionRate"], 33.3)
        self.assertEqual(member["completionRate"], 33.3)
        self.assertEqual(member["openPrs"], 1)
        self.assertEqual(member["mergedPrs"], 1)
        self.assertEqual(member["closedPrs"], 1)
        self.assertEqual(member["stalePrs"], 1)
        self.assertEqual(member["manualReviews"], 1)
        self.assertEqual(member["wipLoad"], 2)


if __name__ == "__main__":
    unittest.main()
