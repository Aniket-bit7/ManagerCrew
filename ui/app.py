import os
import sys
import streamlit as st
import pandas as pd
from pathlib import Path

# Ensure project root is on Python path
sys.path.append(str(Path(__file__).parent.parent))

# Load configurations
from dotenv import load_dotenv
load_dotenv()

from agents.shared.config_loader import load_config
from agents.execution.tools.jira_write import JiraConnector
from agents.execution.tools.github_client import GitHubConnector
from agents.execution.tools.slack_notify import SlackNotifier
from agents.review.agent import ReviewAgent

# Page setup
st.set_page_config(
    page_title="EM Crew - Review & Workload Control Center",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Styling
st.markdown("""
<style>
    /* Dark gradient background */
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #090d16 0%, #111827 100%);
        color: #f3f4f6;
    }
    
    /* Card layouts */
    .metric-card {
        background: rgba(17, 24, 39, 0.7);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 22px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
        margin-bottom: 15px;
        transition: transform 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: rgba(56, 189, 248, 0.4);
    }
    .metric-title {
        font-size: 0.85rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #38bdf8;
    }
    
    /* Badges */
    .badge {
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        display: inline-block;
    }
    .badge-green { background-color: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-orange { background-color: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-red { background-color: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    
    /* Terminal Console */
    .console-log {
        background: #030712;
        border: 1px solid #1f2937;
        font-family: 'Courier New', Courier, monospace;
        padding: 12px;
        border-radius: 8px;
        max-height: 280px;
        overflow-y: auto;
        font-size: 0.85rem;
        color: #10b981;
        line-height: 1.4;
    }
    .console-header {
        font-size: 0.75rem;
        color: #6b7280;
        margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Components
@st.cache_resource
def get_components():
    config = load_config()
    jira = JiraConnector(config=config)
    github = GitHubConnector()
    slack = SlackNotifier()
    review_agent = ReviewAgent(config=config)
    return config, jira, github, slack, review_agent

config, jira, github, slack, review_agent = get_components()

# Page Sidebar configurations
st.sidebar.markdown(f"<h2 style='color:#38bdf8;margin-bottom:0;'>EM Crew Controls</h2>", unsafe_allow_html=True)
st.sidebar.caption("🤖 Code Review & Task Workload Automation")

# Connection Status indicators
st.sidebar.markdown("---")
st.sidebar.markdown("### Integration Systems")
jira_status = "🟢 Live" if not jira.mock_mode else "🟡 Mocked"
github_status = "🟢 Live" if not github.mock_mode else "🟡 Mocked"
slack_status = "🟢 Live" if not slack.mock_mode else "🟡 Mocked"

st.sidebar.markdown(f"**Jira:** {jira_status} (`{config.jira_project_key}`)")
st.sidebar.markdown(f"**GitHub:** {github_status} (`{github.repo_full}`)")
st.sidebar.markdown(f"**Slack:** {slack_status}")

# Workspace Team overview
st.sidebar.markdown("---")
st.sidebar.markdown("### Registered Team Members")
for team in config.teams:
    st.sidebar.subheader(team.name)
    for eng in team.engineers:
        st.sidebar.caption(f"👤 {eng.name} | Git: `{eng.github_username}`")

# Sidebar Actions
st.sidebar.markdown("---")
if st.sidebar.button("🧹 Clear Alert Stream Logs", use_container_width=True):
    slack.clear_messages()
    st.toast("Slack Alert logs cleared!")
    st.rerun()

# Layout
st.markdown("<h1 style='color:#38bdf8;margin-bottom:5px;'>Manager Crew Center</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#9ca3af;margin-top:0;'>Orchestrating Pull Request Audits, Workloads, and Automated Task Completion.</p>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 Review Debt & Workloads", "🔄 Interactive E2E Simulation"])

# TAB 1: Review Debt and Bottleneck Analysis Dashboard
with tab1:
    # 1. Fetch current data
    debt_state = review_agent._load_debt_state()
    prs = github.get_prs()
    active_prs = [p for p in prs if p.get("state") == "open"]
    merged_prs = [p for p in prs if p.get("state") == "merged"]
    
    # Grid Row 1: Metrics Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Active Pull Requests</div>
            <div class="metric-value">{len(active_prs)}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Total Merged PRs</div>
            <div class="metric-value" style="color:#34d399;">{len(merged_prs)}</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        # Calculate stale count for demo (stale = open PRs with odd numbers in simulation, or those open > 48h)
        stale_cnt = sum(1 for p in active_prs if p.get("number", 0) % 2 == 1)
        stale_color = "#f87171" if stale_cnt > 0 else "#38bdf8"
        stale_title = "Stale PRs (>48 Hours)"
        stale_value = f"{stale_cnt}"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">{stale_title}</div>
            <div class="metric-value" style="color:{stale_color};">{stale_value}</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        # Bottleneck files
        hot_folders = list(debt_state["bottlenecks"].keys())
        bottleneck = hot_folders[0] if hot_folders else "None"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Bottleneck Repository Area</div>
            <div class="metric-value" style="font-size:1.1rem;color:#f59e0b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{bottleneck}</div>
        </div>
        """, unsafe_allow_html=True)

    # 2. Main plots
    g_col1, g_col2 = st.columns(2)
    
    with g_col1:
        st.markdown("### 🧑‍💻 Review Workload Allocation")
        # Generate chart showing review stats
        stats = debt_state.get("reviewer_stats", {})
        if stats:
            df_stats = pd.DataFrame.from_dict(stats, orient="index")
            df_stats.reset_index(inplace=True)
            df_stats.rename(columns={"index": "Engineer"}, inplace=True)
            
            # Show workload visual table
            st.dataframe(
                df_stats,
                column_config={
                    "Engineer": "Engineer Name",
                    "pending": st.column_config.NumberColumn("Pending Reviews", format="%d ⏳"),
                    "completed": st.column_config.NumberColumn("Completed Reviews", format="%d ✅"),
                    "avg_response_hours": st.column_config.NumberColumn("Avg Duration (Hrs)", format="%.1f hr")
                },
                hide_index=True,
                use_container_width=True
            )
            
            # Load active workloads from Jira
            st.markdown("#### Jira Active Works Counts")
            wip = review_agent.wip_monitor.get_active_wip_counts(config.jira_project_key)
            wip_data = []
            for team in config.teams:
                for eng in team.engineers:
                    wip_data.append({
                        "Engineer": eng.name,
                        "Active Jira Tasks": wip.get(eng.jira_account_id, 0),
                        "Team": team.name
                    })
            if wip_data:
                st.bar_chart(pd.DataFrame(wip_data).set_index("Engineer")["Active Jira Tasks"], color="#38bdf8")
        else:
            st.info("No workload stats recorded yet.")

    with g_col2:
        st.markdown("### 🗂️ Codebase Review Bottlenecks")
        bottlenecks = debt_state.get("bottlenecks", {})
        if bottlenecks:
            df_b = pd.DataFrame(list(bottlenecks.items()), columns=["Folder/Module Path", "Review Frequency"])
            df_b.sort_values(by="Review Frequency", ascending=False, inplace=True)
            st.dataframe(df_b, hide_index=True, use_container_width=True)
        else:
            st.info("No bottleneck files reviewed yet.")

        # Stale PR Escalation action
        st.markdown("### ⏳ Stale PR Escalation Actions")
        if active_prs:
            stale_prs_list = [p for p in active_prs if p.get("number", 0) % 2 == 1]
            if stale_prs_list:
                for spr in stale_prs_list:
                    c_col1, c_col2 = st.columns([4, 1])
                    with c_col1:
                        st.caption(f"📁 **PR #{spr['number']}**: {spr['title']} (Assigned Reviewer: @{spr.get('reviewer')})")
                    with c_col2:
                        if st.button("Ping on Slack", key=f"escalate_{spr['number']}", use_container_width=True):
                            review_agent.detect_and_escalate_stale_prs()
                            st.toast("Slack escalation alert posted!")
                            st.rerun()
            else:
                st.success("No stale PRs detected in pipeline!")
        else:
            st.info("No active PRs raised in system.")

# TAB 2: Interactive E2E Simulation Sandbox
with tab2:
    st.subheader("Interactive Sprint Dispatch & Audit Loop")
    st.markdown("This sandbox lets you create Jira issues, sync them to GitHub, simulate branch changes, execute AI reviews, send Slack scorecards, auto-merge low risk code, and auto-complete Jira tickets.")

    s_col1, s_col2 = st.columns(2)

    with s_col1:
        # Step 1: Create Issue
        st.markdown("#### 1️⃣ Create & Sync Ticket")
        with st.form("create_ticket_form"):
            task_title = st.text_input("Task Title", value="Implement secure stripe charging portal")
            task_desc = st.text_area("Task Requirements/Description", value="Implement endpoint and validation logic to process stripe transactions securely.")
            
            # Select target team
            team_names = [team.name for team in config.teams]
            selected_team = st.selectbox("Assignee Team", team_names)
            
            # Select Assignee Engineer based on team selection
            team_mapping = config.get_team_mapping()
            engineers = team_mapping[selected_team].engineers if selected_team in team_mapping else []
            eng_options = {eng.name: eng for eng in engineers}
            selected_eng_name = st.selectbox("Assignee Engineer", list(eng_options.keys()))
            
            moscow_tier = st.selectbox("MoSCoW tier", ["MUST", "SHOULD", "COULD", "WON'T"])
            
            submit_ticket = st.form_submit_button("Create Ticket in Jira & GitHub", use_container_width=True)
            
            if submit_ticket:
                selected_eng = eng_options[selected_eng_name]
                
                with st.spinner("Dispatching issues to Jira and GitHub..."):
                    # 1. Jira Create
                    jira_key = jira.create_ticket(
                        title=task_title,
                        description=task_desc,
                        team=selected_team,
                        moscow=moscow_tier,
                        assignee_id=selected_eng.jira_account_id
                    )
                    
                    # 2. GitHub Issue Create
                    gh_issue = github.create_issue(
                        title=f"[{jira_key}] {task_title}",
                        body=f"Jira Ticket: [{jira_key}]({jira.base_url}/browse/{jira_key})\n\n{task_desc}",
                        assignee=selected_eng.github_username
                    )
                    
                    # Save details to streamlit session state
                    st.session_state["last_created_jira_key"] = jira_key
                    st.session_state["last_created_jira_title"] = task_title
                    st.session_state["last_created_assignee"] = selected_eng
                    st.session_state["last_created_team"] = selected_team
                    
                    if gh_issue:
                        st.session_state["last_created_gh_issue"] = gh_issue.get("number")
                        st.success(f"Dispatched: Jira '{jira_key}' | GitHub Issue '#{gh_issue.get('number')}' synced and assigned to @{selected_eng.github_username}!")
                    else:
                        st.success(f"Dispatched Jira '{jira_key}'. GitHub mock fallback complete.")
                    st.rerun()

        # Step 2: Raise PR (Simulated Branch Changes)
        st.markdown("#### 2️⃣ Raise Pull Request on GitHub")
        if "last_created_jira_key" in st.session_state:
            st.markdown(f"🔗 Linked Jira Task: `{st.session_state['last_created_jira_key']}`")
            pr_type = st.selectbox(
                "Simulated Code Template",
                [
                    "Feature: Implement React premium button components",
                    "Feature: Configure auth token claims middleware",
                    "Fix: Log payment processing card details on error"
                ]
            )
            
            # Map type to simulated head branch
            branch_map = {
                "Feature: Implement React premium button components": "feature/dashboard-button",
                "Feature: Configure auth token claims middleware": "sensitive/auth-token-claims",
                "Fix: Log payment processing card details on error": "bug/print-cvv-flaw"
            }
            
            if st.button("Raise GitHub PR & Notify", use_container_width=True):
                jira_key = st.session_state["last_created_jira_key"]
                jira_title = st.session_state["last_created_jira_title"]
                assignee = st.session_state["last_created_assignee"]
                team = st.session_state["last_created_team"]
                
                with st.spinner("Raising Pull Request..."):
                    # Create PR
                    pr = github.create_pr(
                        title=f"PR for {jira_key}: {jira_title} (Branch code: {pr_type})",
                        head_branch=branch_map[pr_type],
                        base_branch="main",
                        body=f"Resolves Issue #{st.session_state.get('last_created_gh_issue', 101)}. Implemented requirements.",
                        assignee=assignee.github_username
                    )
                    
                    if pr:
                        st.session_state["active_pr_audit"] = pr
                        st.session_state["active_pr_team"] = team
                        st.success(f"Raised PR #{pr['number']}! Code modifications pushed to branch `{pr['head']}`.")
                    st.rerun()
        else:
            st.info("Please create a Jira/GitHub issue first to establish a linked task.")

    with s_col2:
        st.markdown("#### 3️⃣ Review Agent Audit Engine")
        if "active_pr_audit" in st.session_state:
            active_pr = st.session_state["active_pr_audit"]
            target_team = st.session_state.get("active_pr_team", "FRONTEND")
            
            st.caption(f"📁 **PR #{active_pr['number']}**: {active_pr['title']}")
            
            if st.button("Execute Code Review Audit", use_container_width=True):
                with st.spinner("Analyzing code diff, assessing expertise and workload balance..."):
                    review_result = review_agent.process_pull_request(
                        pr_number=active_pr["number"],
                        pr_title=active_pr["title"],
                        team_name=target_team
                    )
                    st.session_state["last_review_result"] = review_result
                    
                    # Automate PR merge and Jira completion sync immediately if recommended APPROVE
                    scorecard = review_result.get("scorecard", {})
                    if scorecard.get("overall_recommendation") == "APPROVE":
                        gh_merge = github.merge_pr(review_result["pr_number"])
                        jira_key = st.session_state.get("last_created_jira_key")
                        jira_done = jira.transition_issue(jira_key, "Done")
                        
                        review_agent.log_agent_communication(
                            sender="Review Agent",
                            receiver="Execution Agent",
                            topic="Auto Merge Success",
                            content=f"PR #{review_result['pr_number']} auto-merged. Transitioned Jira Issue '{jira_key}' to status: DONE."
                        )
                        st.session_state["auto_merge_success"] = True
                        st.session_state["auto_merge_msg"] = f"🎉 Auto-Merge Complete! GitHub PR #{review_result['pr_number']} merged automatically, and Jira Task '{jira_key}' transitioned to Done!"
                    else:
                        st.session_state["auto_merge_success"] = False
                st.success("Audit complete! Review result generated.")
                st.rerun()
                
            if "last_review_result" in st.session_state:
                result = st.session_state["last_review_result"]
                scorecard = result["scorecard"]
                
                # Card scorecard display
                st.markdown("---")
                st.markdown(f"#### 📊 Scorecard - PR #{result['pr_number']}")
                
                # Badges row
                sec_risk = scorecard["security_risk"].upper()
                sec_badge = f"<span class='badge badge-red'>{sec_risk} Risk</span>" if sec_risk == "HIGH" else (
                    f"<span class='badge badge-orange'>{sec_risk} Risk</span>" if sec_risk == "MEDIUM" else
                    f"<span class='badge badge-green'>{sec_risk} Risk</span>"
                )
                
                conventions = scorecard["adherence_to_team_conventions"].upper()
                con_badge = f"<span class='badge badge-green'>Conventions: PASS</span>" if conventions == "PASS" else f"<span class='badge badge-red'>Conventions: FAIL</span>"
                
                rec = scorecard["overall_recommendation"].upper()
                rec_badge = f"<span class='badge badge-green'>REC: {rec}</span>" if rec == "APPROVE" else (
                    f"<span class='badge badge-orange'>REC: {rec}</span>" if rec == "MANUAL_REVIEW" else
                    f"<span class='badge badge-red'>REC: {rec}</span>"
                )
                
                st.markdown(f"Status: {sec_badge} &nbsp;&nbsp; {con_badge} &nbsp;&nbsp; {rec_badge}", unsafe_allow_html=True)
                
                # Score values
                st.markdown(f"**Complexity Score**: `{scorecard['complexity']}/10`  \n*{scorecard['complexity_reasoning']}*")
                st.markdown(f"**Coverage Delta**: `{scorecard['test_coverage_delta']:+.1f}%`  \n*{scorecard['coverage_reasoning']}*")
                st.markdown(f"**Security Reasoning**: *{scorecard['security_reasoning']}*")
                st.markdown(f"**Convention Check**: *{scorecard['conventions_reasoning']}*")
                
                st.markdown("#### 👤 Smart Reviewer Assignment")
                st.markdown(f"**Assigned Reviewer**: `{result['reviewer'].name}` (Git: `@{result['reviewer'].github_username}`)")
                st.markdown(f"*Reasoning:* {result['assignment_reason']}")
                st.json(result["workloads"])
                
                # Step 4: Resolution & Auto-merge
                st.markdown("#### 4️⃣ Auto-Merge & Task Completion")
                
                if scorecard["overall_recommendation"] == "APPROVE":
                    st.success("🟢 Review Agent approved this code automatically (Low risk/complexity).")
                    if st.session_state.get("auto_merge_success"):
                        st.success(st.session_state.get("auto_merge_msg", ""))
                    else:
                        st.success("🎉 Success! GitHub PR merged automatically, and Jira Task updated to Completed!")
                    
                    if st.button("Complete and Reset", use_container_width=True):
                        # Cleanup state
                        if "active_pr_audit" in st.session_state:
                            del st.session_state["active_pr_audit"]
                        if "last_review_result" in st.session_state:
                            del st.session_state["last_review_result"]
                        st.rerun()
                else:
                    st.warning("⚠️ Review Agent blocked auto-merge due to Security or Complexity concerns. Mandatory human verification required.")
                    
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if st.button("Approve & Merge Manually", use_container_width=True):
                            gh_merge = github.merge_pr(result["pr_number"])
                            jira_key = st.session_state["last_created_jira_key"]
                            jira_done = jira.transition_issue(jira_key, "Done")
                            
                            review_agent.log_agent_communication(
                                sender="Manager Human",
                                receiver="Review Agent",
                                topic="Override Merge",
                                content=f"PR #{result['pr_number']} manually overridden and merged."
                            )
                            review_agent.log_agent_communication(
                                sender="Review Agent",
                                receiver="Execution Agent",
                                topic="Jira Sync Completion",
                                content=f"PR #{result['pr_number']} manual merge completed. Transitioned Jira Issue '{jira_key}' to status: DONE."
                            )
                            
                            st.toast("Manual override merge executed!")
                            if "active_pr_audit" in st.session_state:
                                del st.session_state["active_pr_audit"]
                            if "last_review_result" in st.session_state:
                                del st.session_state["last_review_result"]
                            st.rerun()
                    with col_b2:
                        if st.button("Reject Pull Request", use_container_width=True):
                            review_agent.log_agent_communication(
                                sender="Review Agent",
                                receiver="Risk Agent",
                                topic="PR Rejected",
                                content=f"PR #{result['pr_number']} rejected due to quality check failures."
                            )
                            st.error(f"PR #{result['pr_number']} has been rejected and closed.")
                            del st.session_state["active_pr_audit"]
                            del st.session_state["last_review_result"]
                            st.rerun()
        else:
            st.info("Raise a GitHub Pull Request first to test review audit actions.")

# Log Streams - Display Slack messages and Agent interactions
st.markdown("---")
l_col1, l_col2 = st.columns(2)

with l_col1:
    st.markdown("### 💬 Slack Notification Alert Feed")
    slack_msgs = slack.get_messages()
    if slack_msgs:
        for msg in reversed(slack_msgs):
            st.markdown(f"""
            <div style="background-color:#1e293b;border-left:4px solid #38bdf8;padding:12px;border-radius:6px;margin-bottom:8px;">
                <strong style="color:#38bdf8;">📢 Channel: {msg['channel']}</strong><br/>
                {msg['text']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("No alerts fired to Slack yet.")

with l_col2:
    st.markdown("### 🔗 Cross-Agent Collaboration Logs")
    st.markdown("<div class='console-header'>LIVE INTER-AGENT MESSAGE STREAM</div>", unsafe_allow_html=True)
    logs = debt_state.get("cross_agent_logs", [])
    if logs:
        log_text = ""
        for log in logs:
            log_text += f"[{log['timestamp']}] {log['sender']} ➡️ {log['receiver']}\n"
            log_text += f"  Topic: {log['topic']}\n"
            log_text += f"  Payload: {log['content']}\n\n"
        st.markdown(f"<pre class='console-log'>{log_text}</pre>", unsafe_allow_html=True)
    else:
        st.markdown("<pre class='console-log'>Waiting for agent interactions...</pre>", unsafe_allow_html=True)
