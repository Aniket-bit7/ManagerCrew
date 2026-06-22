# 🚀 ManagerCrew

**AI-Powered Engineering Management System**

ManagerCrew is an intelligent engineering management platform that automates project planning, task scheduling, code review workflows, and team coordination.

By combining Large Language Models (LLMs), graph theory algorithms, project scheduling techniques, and integrations with Jira, GitHub, and Slack, ManagerCrew transforms raw Product Requirement Documents (PRDs) into actionable engineering plans and automatically manages their execution lifecycle.

---

# 📖 Overview

Engineering teams often spend significant time manually:

* Breaking down requirements
* Creating tickets
* Managing dependencies
* Tracking workloads
* Reviewing pull requests
* Coordinating communication

ManagerCrew automates these processes through specialized AI agents and mathematical scheduling algorithms, allowing teams to focus on building products rather than managing workflows.

---

# 🏗️ System Architecture

```text
                ┌─────────────────────┐
                │      PRD Input      │
                └──────────┬──────────┘
                           │
                           ▼
              ┌──────────────────────────┐
              │ Groq PRD Parser & NLP    │
              └──────────┬───────────────┘
                         │
                         ▼
             ┌───────────────────────────┐
             │ Dependency Graph Builder  │
             └──────────┬────────────────┘
                        │
                        ▼
            ┌────────────────────────────┐
            │ Cycle Detection (DFS)      │
            └──────────┬─────────────────┘
                       │
                       ▼
            ┌────────────────────────────┐
            │ Topological Scheduling     │
            │ (Kahn's Algorithm)         │
            └──────────┬─────────────────┘
                       │
                       ▼
            ┌────────────────────────────┐
            │ CPM / PERT Analysis        │
            └──────────┬─────────────────┘
                       │
                       ▼
            ┌────────────────────────────┐
            │ Capacity Scheduler         │
            └──────────┬─────────────────┘
                       │
                       ▼
      ┌─────────────────────────────────────┐
      │ Jira • GitHub • Slack Dispatching   │
      └─────────────────────────────────────┘
```

---

# ⚙️ Tech Stack

## Backend

* FastAPI
* Python
* Groq API
* Jira API
* GitHub API
* Slack API

## Manager Dashboard

* Streamlit

## Frontend

* React
* Vite

## Data & Configuration

* YAML Configuration
* JSON Storage
* Graph Algorithms
* Scheduling Models

---

# 🔄 Core Workflow

ManagerCrew converts raw requirements into scheduled engineering work through the following pipeline:

### 1. PRD Parsing

Raw product requirements are analyzed using Groq-powered NLP.

Outputs:

* User stories
* Engineering tasks
* Priority classifications
* Dependency relationships

### 2. Dependency Analysis

Tasks are converted into a Directed Acyclic Graph (DAG).

ManagerCrew automatically:

* Detects cycles
* Prevents deadlocks
* Validates dependency chains

### 3. Topological Scheduling

Uses **Kahn's Algorithm** to determine a dependency-safe execution order.

### 4. Critical Path Planning

Uses:

* CPM (Critical Path Method)
* PERT (Program Evaluation and Review Technique)

to calculate:

* Expected completion time
* Schedule variance
* Sprint confidence

### 5. Capacity Scheduling

Tasks are distributed across teams based on:

* Team ownership
* Current workload
* WIP limits
* Capacity availability

### 6. Task Dispatching

Tasks are automatically synchronized to:

* Jira
* GitHub
* Slack

---

# 🤖 Intelligent Agent System

## Planning Agent

Responsible for project planning and scheduling.

### Features

* PRD interpretation
* Task extraction
* Dependency graph creation
* Cycle detection
* Topological sorting
* Sprint simulation
* Capacity planning

---

## Execution Agent

Responsible for interacting with external development tools.

### Features

* Jira ticket creation
* GitHub issue creation
* Cross-platform synchronization
* Task assignment automation

---

## Review Agent

AI-powered code review automation.

### Features

* Pull request auditing
* Complexity scoring
* Security risk analysis
* Test coverage evaluation
* Auto-approval of low-risk PRs
* Escalation of risky changes

### Review Outcomes

| Score             | Action           |
| ----------------- | ---------------- |
| High Confidence   | Auto Merge       |
| Medium Confidence | Team Lead Review |
| Low Confidence    | Reject PR        |

---

## Communication Agent

Coordinates team communication.

### Features

* Assignment notifications
* Manager summaries
* Escalation alerts
* Cross-agent logging
* Slack integration

---

# 🖥️ Manager Control Center

The Streamlit dashboard serves as the operational hub for Engineering Managers.

---

## Tab 1: Review Debt & Workloads

### Metrics Dashboard

Displays:

* Active Pull Requests
* Total Merged PRs
* Stale PRs (>48 hours)
* Review Bottlenecks

### Workload Monitoring

Tracks:

* Pending reviews
* Completed reviews
* Average review response time
* Active Jira tasks

### Escalation Controls

Managers can:

* Ping reviewers
* Escalate stalled PRs
* Trigger Slack reminders

---

## Tab 2: Interactive End-to-End Simulation

### Create & Sync Ticket

Allows managers to:

* Create engineering tasks
* Assign engineers
* Set MoSCoW priorities
* Sync Jira and GitHub

### Raise Pull Request

Simulates:

* Branch creation
* Code updates
* PR generation

### Review Agent Audit

Runs automated PR analysis and returns:

* Complexity Score
* Risk Assessment
* Review Recommendation

Possible outcomes:

* Auto Merge
* Manual Review Required
* Reject Changes

---

# 👥 Team Configuration

All organizational rules are managed through:

```yaml
team_config.yaml
```

## Global Configuration

```yaml
sprint_duration_days: 14
confidence_threshold: 0.6
jira_project_key: TEAM
wip_limit: 5
```

## Team Structure

```yaml
teams:
  FRONTEND:
  BACKEND:
```

## Engineer Profile

```yaml
name:
github_username:
jira_account_id:
slack_user_id:
```

This ensures proper task assignment across all integrated platforms.

---

# 🔌 API Endpoints

## Planning APIs

### Upload PRD

```http
POST /api/planning/upload-pdf
```

Extracts text from uploaded PRD PDFs.

### Generate Draft Plan

```http
POST /api/planning/draft
```

Performs:

* Task extraction
* Dependency analysis
* Cycle detection
* Critical path calculations
* Dispatch simulation

---

## Task Management APIs

### Create Task

```http
POST /api/tasks/create
```

Creates:

* Jira Ticket
* GitHub Issue
* Slack Notification

---

## Review APIs

### Audit Pull Request

```http
POST /api/sprint/audit-pr
```

Runs AI review analysis and produces a scorecard.

### Resolve Pull Request

```http
POST /api/pr/resolve
```

Allows Engineering Managers to manually approve or reject PRs.

---

## Communication APIs

### Escalate Stale Reviews

```http
POST /api/slack/escalate
```

Automatically identifies stalled PRs and sends Slack reminders.

---

# 📊 Key Features

✅ AI-Powered PRD Parsing

✅ Automated Task Breakdown

✅ Dependency Graph Analysis

✅ Cycle Detection

✅ Topological Scheduling

✅ CPM & PERT Sprint Planning

✅ Capacity-Based Team Assignment

✅ Jira Integration

✅ GitHub Integration

✅ Slack Notifications

✅ Automated Code Reviews

✅ Auto-Merge Workflows

✅ Engineering Manager Dashboard

✅ End-to-End Workflow Simulation

---

# 🚀 Future Enhancements

* Real-time sprint analytics
* Predictive delivery forecasting
* Multi-project portfolio planning
* Team performance insights
* AI-generated sprint retrospectives
* Automatic dependency risk prediction
* Resource optimization recommendations

---

# 🎯 Mission

ManagerCrew aims to become the autonomous engineering manager for modern software teams by transforming product requirements into fully planned, scheduled, reviewed, and tracked development workflows with minimal manual intervention.
