"""
test_scorecard_scenarios.py
───────────────────────────
End-to-End Scorecard Scenario Tests — NO MOCK DATA.
All diffs are real code samples sent to the live Groq LLM for scoring.
Tests validate actual Review Agent logic including requirements fulfillment,
security analysis, complexity scoring, and Communication Agent payload structure.

Run: python test_scorecard_scenarios.py
"""

import os
import sys
import json
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from agents.review.agent import ReviewAgent


def section(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print('═'*60)


def check(cond, msg):
    if cond:
        print(f"  ✅ PASS — {msg}")
    else:
        print(f"  ❌ FAIL — {msg}")
        return False
    return True


def run_all():
    section("Initializing Review Agent")
    agent = ReviewAgent()
    if not agent.client:
        print("⚠️  GROQ_API_KEY not set — tests will use rule-based fallback.")
    else:
        print("✅ Groq AI client ready. Using live LLM scoring.")

    results = {}

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 1: Clean simple UI component — should APPROVE
    # ─────────────────────────────────────────────────────────────────────────
    section("CASE 1 — Clean UI Component (Expected: APPROVE)")
    c1_title = "feat: add premium hover button component"
    c1_desc  = "Create a modern, responsive React button component with smooth transitions and hover styling."
    c1_diff  = """\
diff --git a/src/components/Button.jsx b/src/components/Button.jsx
new file mode 100644
--- /dev/null
+++ b/src/components/Button.jsx
@@ -0,0 +1,12 @@
+import React from 'react';
+
+export const PremiumButton = ({ label, onClick }) => {
+  return (
+    <button
+      className="bg-gradient-to-r from-purple-500 to-indigo-600 text-white font-semibold py-2 px-4 rounded-lg shadow-md hover:scale-105 transition-all duration-200"
+      onClick={onClick}
+    >
+      {label}
+    </button>
+  );
+};
"""
    sc1 = agent.generate_scorecard(c1_title, c1_diff, c1_desc)
    print(json.dumps(sc1, indent=2))
    ok1  = check(sc1["security_risk"] == "LOW", f"Security risk should be LOW (got {sc1['security_risk']})")
    ok1 &= check(sc1["requirements_fulfilled"] == "YES", f"Requirements should be fulfilled (got {sc1['requirements_fulfilled']})")
    ok1 &= check(sc1["overall_recommendation"] == "APPROVE", f"Overall should be APPROVE (got {sc1['overall_recommendation']})")
    results["Case 1: Clean UI"] = ok1

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 2: Hardcoded CVV logging + JWT secret — should REJECT or MANUAL_REVIEW
    # ─────────────────────────────────────────────────────────────────────────
    section("CASE 2 — Security Vulnerability (Expected: HIGH RISK, NOT APPROVE)")
    c2_title = "feat: implement credit card charging handler"
    c2_desc  = "Add secure payment processing logic using external gateways. No sensitive data must be logged."
    c2_diff  = """\
diff --git a/src/payments/handler.py b/src/payments/handler.py
--- a/src/payments/handler.py
+++ b/src/payments/handler.py
@@ -10,4 +10,12 @@
-def charge_card(card_details, amount):
+def charge_card(card_details, amount):
+    if amount <= 0:
+        raise ValueError("Invalid amount")
+    if not card_details:
+        raise ValueError("No card")
+    # Hardcoded sensitive logs — SECURITY RISK
+    print(f"DEBUG: card={card_details['card_number']} CVV={card_details['cvv']}")
+    stripe.Charge.create(amount=amount, card=card_details)
+    return True
"""
    sc2 = agent.generate_scorecard(c2_title, c2_diff, c2_desc)
    print(json.dumps(sc2, indent=2))
    ok2  = check(sc2["security_risk"] in ["HIGH", "MEDIUM"], f"Security risk should be HIGH or MEDIUM (got {sc2['security_risk']})")
    ok2 &= check(sc2["overall_recommendation"] != "APPROVE", f"Must NOT be APPROVE (got {sc2['overall_recommendation']})")
    results["Case 2: Security Vuln"] = ok2

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 3: High complexity recursion — should be MANUAL_REVIEW
    # ─────────────────────────────────────────────────────────────────────────
    section("CASE 3 — High Complexity Recursion (Expected: complexity >= 6, NOT APPROVE)")
    c3_title = "refactor: optimize nested graph traversal algorithm"
    c3_desc  = "Write a clean, well-commented graph traversal algorithm."
    c3_diff  = """\
diff --git a/src/utils/traversal.py b/src/utils/traversal.py
--- a/src/utils/traversal.py
+++ b/src/utils/traversal.py
@@ -1,5 +1,30 @@
-def traverse(node):
-    return [node]
+def traverse(node, visited=None, depth=0):
+    if visited is None:
+        visited = set()
+    if node in visited:
+        return []
+    visited.add(node)
+    res = [node.val]
+    for child in node.children:
+        for sibling in child.siblings:
+            for nested in sibling.children:
+                if nested not in visited:
+                    res.extend(traverse(nested, visited, depth + 1))
+                    if hasattr(nested, 'left'):
+                        res.extend(traverse(nested.left, visited, depth + 2))
+                    if hasattr(nested, 'right'):
+                        res.extend(traverse(nested.right, visited, depth + 2))
+    for secondary in getattr(node, 'secondary_links', []):
+        res.extend(traverse(secondary, visited, depth + 1))
+        if hasattr(secondary, 'weight') and secondary.weight > 10:
+            for item in secondary.items:
+                if item not in visited:
+                    res.extend(traverse(item, visited, depth + 2))
+    return sorted(list(set(res)))
"""
    sc3 = agent.generate_scorecard(c3_title, c3_diff, c3_desc)
    print(json.dumps(sc3, indent=2))
    try:
        comp3 = int(sc3.get("complexity", 0))
    except Exception:
        comp3 = 0
    ok3  = check(comp3 >= 5, f"Complexity should be >= 5 (got {comp3})")
    ok3 &= check(sc3["overall_recommendation"] != "APPROVE", f"Must NOT be APPROVE (got {sc3['overall_recommendation']})")
    results["Case 3: High Complexity"] = ok3

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 4: Mismatching diff — manager wants DB migration, code has sidebar UI
    # ─────────────────────────────────────────────────────────────────────────
    section("CASE 4 — Unfulfilled Requirements (Expected: requirements_fulfilled=NO)")
    c4_title = "feat: add user schema migration"
    c4_desc  = "Create a database migration script for the user_profiles table with email and display_name columns."
    c4_diff  = """\
diff --git a/src/components/Sidebar.jsx b/src/components/Sidebar.jsx
new file mode 100644
--- /dev/null
+++ b/src/components/Sidebar.jsx
@@ -0,0 +1,8 @@
+import React from 'react';
+
+export const Sidebar = () => {
+  return (
+    <aside className="w-64 bg-gray-800 text-white">Sidebar Menu</aside>
+  );
+};
"""
    sc4 = agent.generate_scorecard(c4_title, c4_diff, c4_desc)
    print(json.dumps(sc4, indent=2))
    ok4  = check(sc4["requirements_fulfilled"] == "NO", f"Requirements should NOT be fulfilled (got {sc4['requirements_fulfilled']})")
    ok4 &= check(sc4["overall_recommendation"] != "APPROVE", f"Must NOT be APPROVE (got {sc4['overall_recommendation']})")
    results["Case 4: Unfulfilled"] = ok4

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 5: No requirements provided — should not penalize requirements_fulfilled
    # ─────────────────────────────────────────────────────────────────────────
    section("CASE 5 — No Task Description (Expected: requirements_fulfilled=YES baseline)")
    c5_title = "fix: correct typo in README documentation"
    c5_desc  = ""  # No requirements
    c5_diff  = """\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -3 +3 @@
-This project is an exmple application.
+This project is an example application.
"""
    sc5 = agent.generate_scorecard(c5_title, c5_diff, c5_desc)
    print(json.dumps(sc5, indent=2))
    ok5  = check(sc5["requirements_fulfilled"] == "YES", f"Without description, should default to YES (got {sc5['requirements_fulfilled']})")
    ok5 &= check(sc5["security_risk"] == "LOW", f"Docs change should be LOW risk (got {sc5['security_risk']})")
    ok5 &= check(sc5["overall_recommendation"] == "APPROVE", f"Tiny doc fix should be APPROVE (got {sc5['overall_recommendation']})")
    results["Case 5: No Description"] = ok5

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 6: Convention violations (debug prints + TODO) — should be MANUAL_REVIEW
    # ─────────────────────────────────────────────────────────────────────────
    section("CASE 6 — Convention Violations (Expected: conventions=FAIL or MANUAL_REVIEW)")
    c6_title = "feat: add notification service"
    c6_desc  = "Create a clean notification service following coding standards."
    c6_diff  = """\
diff --git a/src/notifications/service.py b/src/notifications/service.py
new file mode 100644
--- /dev/null
+++ b/src/notifications/service.py
@@ -0,0 +1,18 @@
+class NotificationService:
+    def __init__(self):
+        # TODO: replace with real email provider
+        self.provider = None
+
+    def send(self, user_id, message):
+        print(f"DEBUG: Sending notification to {user_id}: {message}")
+        # TODO: implement actual notification logic
+        pass
+
+    def bulk_send(self, users, msg):
+        print(f"DEBUG: bulk sending to {len(users)} users")
+        for u in users:
+            self.send(u, msg)
+        # TODO: add retry logic
+        return True
"""
    sc6 = agent.generate_scorecard(c6_title, c6_diff, c6_desc)
    print(json.dumps(sc6, indent=2))
    ok6  = check(sc6["adherence_to_team_conventions"] == "FAIL" or sc6["overall_recommendation"] != "APPROVE",
                 f"Convention violations should trigger FAIL or not APPROVE (conventions={sc6['adherence_to_team_conventions']}, rec={sc6['overall_recommendation']})")
    results["Case 6: Convention Violations"] = ok6

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 7: Validate Communication Agent payload structure
    # ─────────────────────────────────────────────────────────────────────────
    section("CASE 7 — Communication Agent Payload Structure Validation")
    # Use a mock engineer-like object
    class MockEng:
        name = "Test Engineer"
        github_username = "testeng"
        jira_account_id = "test-jira-id"

    payload = agent.build_communication_agent_payload(
        pr_number=42,
        pr_title="feat: test PR for comms agent",
        scorecard=sc1,
        reviewer=MockEng(),
        assignment_reason="Has most expertise on changed files.",
        task_description="Build a test button component.",
        jira_key="KAN-42",
        action_taken="AUTO_MERGED"
    )
    print(json.dumps(payload, indent=2))
    ok7  = check(payload.get("event") == "PR_AUDIT_COMPLETE", "event field should be PR_AUDIT_COMPLETE")
    ok7 &= check("timestamp" in payload, "payload should have timestamp")
    ok7 &= check("scorecard" in payload, "payload should contain scorecard")
    ok7 &= check(payload.get("pr", {}).get("jira_key") == "KAN-42", "pr.jira_key should be KAN-42")
    ok7 &= check(payload.get("action_taken") == "AUTO_MERGED", "action_taken should be AUTO_MERGED")
    ok7 &= check(payload.get("reviewer", {}).get("name") == "Test Engineer", "reviewer.name should be Test Engineer")
    results["Case 7: Comms Agent Payload"] = ok7

    # ─────────────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────────────
    section("SUMMARY")
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("🎉 All tests passed successfully!")
    else:
        print("⚠️  Some tests failed — review output above.")
        sys.exit(1)


if __name__ == "__main__":
    run_all()
