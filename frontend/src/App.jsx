import React, { useState, useEffect } from 'react';

const API_BASE = "http://localhost:8000";

function App() {
  const [activeTab, setActiveTab] = useState("overview"); // "overview", "tasks", "pipeline", "settings"
  const [appConfig, setAppConfig] = useState(null);
  const [stats, setStats] = useState({
    activePrsCount: 0,
    mergedPrsCount: 0,
    stalePrsCount: 0,
    bottlenecks: [],
    activePrs: [],
    mergedPrs: [],
    stalePrsList: []
  });
  const [workloads, setWorkloads] = useState({
    reviewerStats: [],
    jiraWorkloads: []
  });
  const [slackFeed, setSlackFeed] = useState([]);
  const [agentLogs, setAgentLogs] = useState([]);

  // Live PR audit states
  const [selectedPR, setSelectedPR] = useState(null);
  const [reviewResult, setReviewResult] = useState(null);
  const [autoMergeSuccess, setAutoMergeSuccess] = useState(false);
  const [autoMergeMsg, setAutoMergeMsg] = useState("");
  const [manuallyResolved, setManuallyResolved] = useState(false);
  const [resolutionMsg, setResolutionMsg] = useState("");
  const [taskDescription, setTaskDescription] = useState("");

  const [loading, setLoading] = useState(false);

  // Task Management tab states
  const [tasks, setTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [taskSuccess, setTaskSuccess] = useState("");
  const [taskError, setTaskError] = useState("");
  const [newTask, setNewTask] = useState({
    title: "",
    description: "",
    team: "FRONTEND",
    moscow: "Must Have",
    assigneeName: "",
    assigneeJiraId: "",
    assigneeGithubId: ""
  });
  const [assigningTask, setAssigningTask] = useState(null); // jiraKey being reassigned
  const [assignTarget, setAssignTarget] = useState({ jiraId: "", name: "" });

  // Settings tab states
  const [settings, setSettings] = useState({
    github_repo: "",
    slack_bot_token: "",
    slack_manager_channel: "",
    jira_api_token: "",
    jira_email: "",
    jira_base_url: "",
    github_token: "",
    github_owner: "",
    groq_api_key: "",
    wip_limit: 1,
    jira_project_key: "KAN",
    team_lead_slack_id: "",
    engineers: []
  });
  const [newEng, setNewEng] = useState({
    name: "",
    github_username: "",
    jira_account_id: "",
    slack_user_id: "",
    is_team_lead: false
  });
  const [settingsSuccess, setSettingsSuccess] = useState("");
  const [settingsError, setSettingsError] = useState("");

  // Pipeline-specific state
  const [openPRs, setOpenPRs] = useState([]);
  const [openPRsLoading, setOpenPRsLoading] = useState(false);
  const [pendingReviews, setPendingReviews] = useState([]);
  const [pendingLoading, setPendingLoading] = useState(false);

  // Load app configs
  useEffect(() => {
    fetch(`${API_BASE}/api/config`)
      .then(res => res.json())
      .then(data => setAppConfig(data))
      .catch(err => console.error("Error fetching config:", err));
    
    fetchSettings();
    refreshData();
    fetchTasks();
    fetchOpenPRs();
    fetchPendingReviews();
    const interval = setInterval(() => {
      refreshData();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchOpenPRs = async () => {
    setOpenPRsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/prs/open`);
      const data = await res.json();
      if (data.openPRs) setOpenPRs(data.openPRs);
    } catch (err) {
      console.error("Error fetching open PRs:", err);
    } finally {
      setOpenPRsLoading(false);
    }
  };

  const fetchPendingReviews = async () => {
    setPendingLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/reviews/pending`);
      const data = await res.json();
      if (data.pending) setPendingReviews(data.pending);
    } catch (err) {
      console.error("Error fetching pending reviews:", err);
    } finally {
      setPendingLoading(false);
    }
  };

  const clearPendingReview = async (prNumber) => {
    try {
      await fetch(`${API_BASE}/api/reviews/pending/${prNumber}`, { method: "DELETE" });
      fetchPendingReviews();
    } catch (err) {
      console.error("Error clearing pending review:", err);
    }
  };


  const fetchTasks = async () => {
    setTasksLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/tasks/list`);
      const data = await res.json();
      if (data.issues) setTasks(data.issues);
    } catch (err) {
      console.error("Error fetching tasks:", err);
    } finally {
      setTasksLoading(false);
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    setTaskSuccess("");
    setTaskError("");
    if (!newTask.title || !newTask.description) {
      setTaskError("Title and description are required.");
      return;
    }
    setTasksLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/tasks/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newTask)
      });
      const data = await res.json();
      if (data.success) {
        setTaskSuccess(`✅ ${data.message}`);
        setNewTask({ title: "", description: "", team: "FRONTEND", moscow: "Must Have", assigneeName: "", assigneeJiraId: "", assigneeGithubId: "" });
        fetchTasks();
        refreshData();
      } else {
        setTaskError(data.detail || "Failed to create task.");
      }
    } catch (err) {
      setTaskError(err.message);
    } finally {
      setTasksLoading(false);
    }
  };

  const handleAssignTask = async (jiraKey) => {
    if (!assignTarget.jiraId) {
      alert("Please select an engineer to assign.");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/tasks/assign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jiraKey, assigneeJiraId: assignTarget.jiraId })
      });
      const data = await res.json();
      if (data.success) {
        alert(`✅ ${data.message}`);
        setAssigningTask(null);
        setAssignTarget({ jiraId: "", name: "" });
        fetchTasks();
      } else {
        alert(`❌ ${data.detail || "Failed to assign."}`);
      }
    } catch (err) {
      alert(`❌ ${err.message}`);
    }
  };


  const refreshData = () => {
    fetch(`${API_BASE}/api/dashboard/stats`)
      .then(res => res.json())
      .then(data => setStats(data))
      .catch(err => console.error(err));

    fetch(`${API_BASE}/api/dashboard/workloads`)
      .then(res => res.json())
      .then(data => setWorkloads(data))
      .catch(err => console.error(err));

    fetch(`${API_BASE}/api/slack/feed`)
      .then(res => res.json())
      .then(data => setSlackFeed(data))
      .catch(err => console.error(err));

    fetch(`${API_BASE}/api/agents/logs`)
      .then(res => res.json())
      .then(data => setAgentLogs(data))
      .catch(err => console.error(err));
  };

  // Step 3: Run Audit on Live PR — no task description needed, server fetches from Jira
  const handleAuditPR = async (pr) => {
    setSelectedPR(pr);
    setReviewResult(null);
    setAutoMergeSuccess(false);
    setAutoMergeMsg("");
    setManuallyResolved(false);
    setResolutionMsg("");
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/sprint/audit-pr`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prNumber: pr.number,
          prTitle: pr.title,
          teamName: "FRONTEND"
          // taskDescription intentionally omitted — server fetches from Jira using the PR's Jira key
        })
      });
      const data = await response.json();
      if (data.success) {
        setReviewResult(data.audit);
        setAutoMergeSuccess(data.autoMerged);
        setAutoMergeMsg(data.autoMergeMessage);
        refreshData();
        fetchOpenPRs();       // refresh open PRs (merged ones disappear)
        fetchPendingReviews(); // refresh pending if MANUAL_REVIEW
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchSettings = () => {
    fetch(`${API_BASE}/api/config/settings`)
      .then(res => res.json())
      .then(data => setSettings(data))
      .catch(err => console.error("Error fetching settings:", err));
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setSettingsSuccess("");
    setSettingsError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/config/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
      });
      const data = await response.json();
      if (response.ok && data.success) {
        setSettingsSuccess("Configuration saved and system successfully reloaded!");
        fetch(`${API_BASE}/api/config`)
          .then(res => res.json())
          .then(cfg => setAppConfig(cfg));
      } else {
        setSettingsError(data.detail || "Failed to save configuration settings.");
      }
    } catch (err) {
      setSettingsError(err.message || "Network error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleAddEngineer = () => {
    if (!newEng.name || !newEng.github_username || !newEng.jira_account_id) {
      alert("Name, GitHub Username, and Jira Account ID are required.");
      return;
    }
    setSettings({
      ...settings,
      engineers: [...settings.engineers, newEng]
    });
    setNewEng({
      name: "",
      github_username: "",
      jira_account_id: "",
      slack_user_id: ""
    });
  };

  const handleRemoveEngineer = (index) => {
    const updated = settings.engineers.filter((_, idx) => idx !== index);
    setSettings({
      ...settings,
      engineers: updated
    });
  };

  // Manual Override Approve or Reject
  const handleManualPR = async (action) => {
    if (!selectedPR) return;
    setLoading(true);
    let jiraKey = "";
    let match = selectedPR.title.match(/\b([a-zA-Z]+-\d+)\b/);
    if (match) {
      jiraKey = match[1].toUpperCase();
    } else if (selectedPR.head) {
      match = selectedPR.head.match(/\b([a-zA-Z]+-\d+)\b/);
      if (match) {
        jiraKey = match[1].toUpperCase();
      }
    }
    try {
      const response = await fetch(`${API_BASE}/api/pr/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prNumber: selectedPR.number,
          action: action,
          jiraKey: jiraKey
        })
      });
      const data = await response.json();
      if (data.success) {
        setManuallyResolved(true);
        setResolutionMsg(data.message);
        refreshData();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleEscalateSlack = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/slack/escalate`, { method: "POST" });
      const data = await response.json();
      if (data.success) {
        alert(`Escalated ${data.staleCountEscalated} stale PRs to Slack!`);
        refreshData();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const resetAudit = () => {
    setSelectedPR(null);
    setReviewResult(null);
    setAutoMergeSuccess(false);
    setAutoMergeMsg("");
    setManuallyResolved(false);
    setResolutionMsg("");
  };

  return (
    <div className="app-container">
      {/* Sidebar Controls */}
      <div className="sidebar">
        <div>
          <h2 style={{ color: "#38bdf8" }}>EM Crew Center</h2>
          <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Review Agent Integration</p>
        </div>
        
        <ul className="nav-list">
          <li 
            className={`nav-item ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab("overview")}
          >
            📊 Debt & Workloads
          </li>
          <li 
            className={`nav-item ${activeTab === 'tasks' ? 'active' : ''}`}
            onClick={() => { setActiveTab("tasks"); fetchTasks(); }}
          >
            📋 Task Management
          </li>
          <li 
            className={`nav-item ${activeTab === 'pipeline' ? 'active' : ''}`}
            onClick={() => setActiveTab("pipeline")}
          >
            🔄 Live PR Review Center
          </li>
          <li 
            className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab("settings")}
          >
            ⚙️ Settings & Teams
          </li>
        </ul>

        <div style={{ marginTop: "auto" }}>
          <h4 style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: 12 }}>System Status</h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: "0.85rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Jira:</span>
              <span className={appConfig?.jiraMock ? "badge badge-orange" : "badge badge-green"}>
                {appConfig?.jiraMock ? "Mock" : "Live"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>GitHub:</span>
              <span className={appConfig?.githubMock ? "badge badge-orange" : "badge badge-green"}>
                {appConfig?.githubMock ? "Mock" : "Live"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Slack:</span>
              <span className={appConfig?.slackMock ? "badge badge-orange" : "badge badge-green"}>
                {appConfig?.slackMock ? "Mock" : "Live"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Panel Content */}
      <div className="main-content">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 32 }}>
          <div>
            <h1 style={{ color: "#38bdf8", marginBottom: 4 }}>Manager dashboard</h1>
            <p>Orchestrate PR scorecards, workloads, and auto-completion transitions.</p>
          </div>
          {appConfig && (
            <div style={{ display: "flex", gap: 12 }}>
              <span className="badge badge-blue">Project Key: {appConfig.jiraProjectKey}</span>
              <span className="badge badge-blue">WIP Limit: {appConfig.wipLimit}</span>
            </div>
          )}
        </div>

        {activeTab === "overview" && (
          <div>

            <div className="dashboard-grid">
              <div className="glass-panel">
                <div style={{ fontSize: "0.85rem", color: "#9ca3af", textTransform: "uppercase" }}>Active Pull Requests</div>
                <div style={{ fontSize: "2.5rem", fontWeight: 700, color: "#38bdf8", marginTop: 8 }}>
                  {stats.activePrsCount}
                </div>
              </div>
              <div className="glass-panel">
                <div style={{ fontSize: "0.85rem", color: "#9ca3af", textTransform: "uppercase" }}>Merged PRs</div>
                <div style={{ fontSize: "2.5rem", fontWeight: 700, color: "#34d399", marginTop: 8 }}>
                  {stats.mergedPrsCount}
                </div>
              </div>
              <div className="glass-panel">
                <div style={{ fontSize: "0.85rem", color: "#9ca3af", textTransform: "uppercase" }}>Stale PRs (&gt;48 hrs)</div>
                <div style={{ fontSize: "2.5rem", fontWeight: 700, color: stats.stalePrsCount > 0 ? "#f87171" : "#38bdf8", marginTop: 8 }}>
                  {stats.stalePrsCount}
                </div>
              </div>
              <div className="glass-panel">
                <div style={{ fontSize: "0.85rem", color: "#9ca3af", textTransform: "uppercase" }}>Bottleneck Area</div>
                <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "#fbbf24", marginTop: 18, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {stats.bottlenecks[0]?.path || "None"}
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, marginTop: 32 }}>
              <div className="glass-panel">
                <h3 style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 16 }}>
                  👥 Developer Review Workloads
                </h3>
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Engineer</th>
                      <th>Pending</th>
                      <th>Completed</th>
                      <th>Avg Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workloads.reviewerStats.map((r, i) => (
                      <tr key={i}>
                        <td><strong>{r.name}</strong></td>
                        <td style={{ color: r.pending > 0 ? "#fbbf24" : "inherit" }}>{r.pending} ⏳</td>
                        <td>{r.completed} ✅</td>
                        <td>{r.avgResponseHours.toFixed(1)} hrs</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <h3 style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginTop: 32, marginBottom: 16 }}>
                  📊 Active Jira Capacity
                </h3>
                {workloads.jiraWorkloads.map((jw, i) => (
                  <div key={i} style={{ marginBottom: 16 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem", marginBottom: 6 }}>
                      <span>{jw.name} ({jw.team})</span>
                      <span>{jw.activeTasks} / {appConfig?.wipLimit || 1} Tasks</span>
                    </div>
                    <div style={{ height: 8, background: "rgba(255,255,255,0.05)", borderRadius: 4, overflow: "hidden" }}>
                      <div 
                        style={{ 
                          height: "100%", 
                          width: `${Math.min(100, (jw.activeTasks / (appConfig?.wipLimit || 1)) * 100)}%`,
                          background: jw.activeTasks >= (appConfig?.wipLimit || 1) ? "var(--color-red)" : "var(--color-blue)"
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="glass-panel">
                <h3 style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 16 }}>
                  🗂️ Module Review Bottlenecks
                </h3>
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Module Path</th>
                      <th>Review Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.bottlenecks.map((b, i) => (
                      <tr key={i}>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}>{b.path}</td>
                        <td><span className="badge badge-orange">{b.count} times</span></td>
                      </tr>
                    ))}
                    {stats.bottlenecks.length === 0 && (
                      <tr>
                        <td colSpan="2" style={{ textAlign: "center", color: "var(--text-muted)" }}>No code review bottlenecks found.</td>
                      </tr>
                    )}
                  </tbody>
                </table>

                <div style={{ marginTop: 32 }}>
                  <h3 style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 16 }}>
                    ⏳ Stale PR Actions
                  </h3>
                  {stats.stalePrsList.map((spr, i) => (
                    <div 
                      key={i} 
                      style={{ 
                        display: "flex", 
                        justifyContent: "space-between", 
                        alignItems: "center", 
                        padding: 12, 
                        background: "rgba(255,255,255,0.02)", 
                        borderRadius: 8,
                        marginBottom: 10,
                        border: "1px solid rgba(248, 113, 113, 0.15)"
                      }}
                    >
                      <div style={{ fontSize: "0.9rem" }}>
                        <strong>PR #{spr.number}</strong>: {spr.title} <br/>
                        <span style={{ color: "var(--text-muted)" }}>Reviewer: @{spr.reviewer || "unassigned"}</span>
                      </div>
                      <button 
                        onClick={handleEscalateSlack} 
                        className="btn btn-secondary"
                        style={{ width: "auto", padding: "6px 12px", fontSize: "0.8rem" }}
                      >
                        Ping Reviewer
                      </button>
                    </div>
                  ))}
                  {stats.stalePrsList.length === 0 && (
                    <div style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>🟢 No stale PRs currently blocking development.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "tasks" && (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32 }}>
              {/* Create Task Form */}
              <div className="glass-panel">
                <h3 style={{ color: "#38bdf8", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 20 }}>
                  ➕ Create New Task
                </h3>

                {taskSuccess && (
                  <div style={{ background: "rgba(52,211,153,0.1)", color: "var(--color-green)", padding: 12, borderRadius: 8, marginBottom: 16, fontSize: "0.9rem" }}>{taskSuccess}</div>
                )}
                {taskError && (
                  <div style={{ background: "rgba(248,113,113,0.1)", color: "var(--color-red)", padding: 12, borderRadius: 8, marginBottom: 16, fontSize: "0.9rem" }}>{taskError}</div>
                )}

                <form onSubmit={handleCreateTask} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div className="form-group">
                    <label className="form-label">Task Title *</label>
                    <input type="text" className="form-input" value={newTask.title}
                      onChange={e => setNewTask({...newTask, title: e.target.value})}
                      placeholder="e.g. Add user authentication flow" required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Task Description (Requirement) *</label>
                    <textarea className="form-textarea" style={{ height: 90, resize: "none" }}
                      value={newTask.description}
                      onChange={e => setNewTask({...newTask, description: e.target.value})}
                      placeholder="Describe what needs to be implemented. This will be used by the Review Agent to verify the PR." required />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div className="form-group">
                      <label className="form-label">Team</label>
                      <select className="form-input" value={newTask.team}
                        onChange={e => setNewTask({...newTask, team: e.target.value})}>
                        {(appConfig?.teams || []).map(t => (
                          <option key={t.name} value={t.name}>{t.name}</option>
                        ))}
                        {(!appConfig?.teams || appConfig.teams.length === 0) && <option value="FRONTEND">FRONTEND</option>}
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">MoSCoW Priority</label>
                      <select className="form-input" value={newTask.moscow}
                        onChange={e => setNewTask({...newTask, moscow: e.target.value})}>
                        <option value="Must Have">Must Have</option>
                        <option value="Should Have">Should Have</option>
                        <option value="Could Have">Could Have</option>
                        <option value="Won't Have">Won&apos;t Have</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Assign To (Engineer)</label>
                    <select className="form-input" value={newTask.assigneeJiraId}
                      onChange={e => {
                        const eng = (appConfig?.teams || []).flatMap(t => t.engineers).find(en => en.jira_account_id === e.target.value);
                        setNewTask({...newTask, assigneeJiraId: e.target.value, assigneeName: eng?.name || "", assigneeGithubId: eng?.github_username || ""});
                      }}>
                      <option value="">— Unassigned —</option>
                      {(appConfig?.teams || []).flatMap(t => t.engineers).map(eng => (
                        <option key={eng.jira_account_id} value={eng.jira_account_id}>
                          {eng.name} (@{eng.github_username})
                        </option>
                      ))}
                    </select>
                  </div>

                  <button type="submit" className="btn btn-primary" style={{ marginTop: 8 }} disabled={tasksLoading}>
                    {tasksLoading ? <div className="spinner" /> : "🚀 Create Task on Jira + GitHub"}
                  </button>
                </form>
              </div>

              {/* Active Tasks List */}
              <div className="glass-panel">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12 }}>
                  <h3 style={{ color: "#38bdf8", margin: 0 }}>📋 Active Tasks (Jira + GitHub)</h3>
                  <button onClick={fetchTasks} className="btn btn-secondary" style={{ padding: "6px 12px", fontSize: "0.8rem", width: "auto" }} disabled={tasksLoading}>
                    {tasksLoading ? <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> : "↻ Refresh"}
                  </button>
                </div>

                {tasks.length === 0 && !tasksLoading && (
                  <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-muted)" }}>
                    <div style={{ fontSize: "2.5rem", marginBottom: 12 }}>📭</div>
                    <p>No active tasks found. Create one to get started!</p>
                  </div>
                )}
                {tasksLoading && tasks.length === 0 && (
                  <div style={{ textAlign: "center", padding: 40 }}><div className="spinner" style={{ margin: "0 auto" }} /></div>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: 12, maxHeight: 520, overflowY: "auto" }}>
                  {tasks.map(task => (
                    <div key={task.key} style={{ padding: 14, background: "rgba(255,255,255,0.03)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.07)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                        <span style={{ fontFamily: "var(--font-mono)", color: "#38bdf8", fontSize: "0.85rem", fontWeight: 700 }}>{task.key}</span>
                        <div style={{ display: "flex", gap: 6 }}>
                          <span className="badge badge-blue" style={{ fontSize: "0.7rem" }}>{task.status}</span>
                          {task.github_issue && (
                            <a href={task.github_issue.html_url} target="_blank" rel="noopener noreferrer"
                              className="badge badge-green" style={{ fontSize: "0.7rem", textDecoration: "none" }}>
                              GH #{task.github_issue.number}
                            </a>
                          )}
                        </div>
                      </div>
                      <div style={{ fontWeight: 600, marginBottom: 6, color: "#e2e8f0", lineHeight: 1.4 }}>{task.summary}</div>
                      <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: 10 }}>
                        Assignee: <strong style={{ color: "#9ca3af" }}>{task.assignee_name || "Unassigned"}</strong>
                        {task.description && <span> · {task.description.slice(0, 60)}{task.description.length > 60 ? "..." : ""}</span>}
                      </div>

                      {assigningTask === task.key ? (
                        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
                          <select className="form-input" style={{ flex: 1, padding: "6px 8px", fontSize: "0.82rem" }}
                            value={assignTarget.jiraId}
                            onChange={e => {
                              const eng = (appConfig?.teams || []).flatMap(t => t.engineers).find(en => en.jira_account_id === e.target.value);
                              setAssignTarget({ jiraId: e.target.value, name: eng?.name || "" });
                            }}>
                            <option value="">— Pick engineer —</option>
                            {(appConfig?.teams || []).flatMap(t => t.engineers).map(eng => (
                              <option key={eng.jira_account_id} value={eng.jira_account_id}>{eng.name}</option>
                            ))}
                          </select>
                          <button onClick={() => handleAssignTask(task.key)} className="btn btn-primary" style={{ padding: "6px 12px", fontSize: "0.8rem", width: "auto" }}>Assign</button>
                          <button onClick={() => setAssigningTask(null)} className="btn btn-secondary" style={{ padding: "6px 10px", fontSize: "0.8rem", width: "auto" }}>✕</button>
                        </div>
                      ) : (
                        <button onClick={() => { setAssigningTask(task.key); setAssignTarget({ jiraId: "", name: "" }); }}
                          className="btn btn-secondary" style={{ padding: "5px 10px", fontSize: "0.78rem", width: "auto" }}>
                          👤 Reassign
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Pending Team Lead Reviews Panel */}
            {pendingReviews.length > 0 && (
              <div className="glass-panel" style={{ marginTop: 32, borderColor: "rgba(251,191,36,0.3)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(251,191,36,0.2)", paddingBottom: 12, marginBottom: 20 }}>
                  <h3 style={{ color: "#fbbf24", margin: 0 }}>👤 Pending Human Review ({pendingReviews.length})</h3>
                  <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", maxWidth: 480, textAlign: "right", lineHeight: 1.4 }}>
                    Team lead notified via Slack. Once the dev raises a new PR after fixing the issues, the Review Agent will auto re-audit it.
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 16 }}>
                  {pendingReviews.map(item => (
                    <div key={item.pr_number} style={{ padding: 16, background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.15)", borderRadius: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <span style={{ fontWeight: 700, color: "#e2e8f0" }}>PR #{item.pr_number}</span>
                          {item.jira_key && <span className="badge badge-blue" style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>{item.jira_key}</span>}
                        </div>
                        <span className="badge badge-orange" style={{ fontSize: "0.7rem" }}>AWAITING REVIEW</span>
                      </div>
                      <div style={{ fontWeight: 600, marginBottom: 8, color: "#e2e8f0", lineHeight: 1.4, fontSize: "0.9rem" }}>{item.pr_title}</div>
                      <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: 10 }}>
                        Author: <strong style={{ color: "#9ca3af" }}>@{item.pr_author}</strong>
                        {" · "}Escalated to: <strong style={{ color: "#9ca3af" }}>{item.escalated_to}</strong>
                      </div>
                      {item.scorecard && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                          <span className={`badge ${item.scorecard.security_risk === "HIGH" ? "badge-red" : "badge-green"}`} style={{ fontSize: "0.68rem" }}>
                            {item.scorecard.security_risk} Risk
                          </span>
                          <span className={`badge ${item.scorecard.requirements_fulfilled === "YES" ? "badge-green" : "badge-red"}`} style={{ fontSize: "0.68rem" }}>
                            Req: {item.scorecard.requirements_fulfilled}
                          </span>
                          <span className="badge badge-blue" style={{ fontSize: "0.68rem" }}>Complexity: {item.scorecard.complexity}/10</span>
                        </div>
                      )}
                      {item.reasons && item.reasons.length > 0 && (
                        <div style={{ fontSize: "0.78rem", color: "#f87171", marginBottom: 12, lineHeight: 1.5 }}>
                          {item.reasons.slice(0, 2).map((r, i) => (
                            <div key={i} style={{ marginBottom: 2 }}>• {r.replace(/\*/g, "")}</div>
                          ))}
                          {item.reasons.length > 2 && <div style={{ color: "var(--text-muted)" }}>+{item.reasons.length - 2} more issue(s)</div>}
                        </div>
                      )}
                      <button onClick={() => clearPendingReview(item.pr_number)}
                        className="btn btn-secondary"
                        style={{ padding: "6px 12px", fontSize: "0.78rem", width: "auto", borderColor: "rgba(251,191,36,0.3)", color: "#fbbf24" }}>
                        ✓ Mark as Reviewed
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "pipeline" && (
          <div>
            {/* Tab: Live GitHub PR Queue & AI Audit */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32 }}>
              <div>
                <div className="glass-panel" style={{ minHeight: 400 }}>
                  <h3 style={{ color: "#38bdf8", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 20 }}>
                    📥 Open Pull Requests
                  </h3>

                  <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", marginBottom: 16 }}>
                    <button onClick={() => { fetchOpenPRs(); fetchPendingReviews(); }} className="btn btn-secondary"
                      style={{ padding: "6px 12px", fontSize: "0.78rem", width: "auto" }} disabled={openPRsLoading}>
                      {openPRsLoading ? <div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : "↻ Refresh"}
                    </button>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {openPRs.map((pr) => (
                      <div 
                        key={pr.number}
                        style={{
                          padding: 18,
                          background: selectedPR?.number === pr.number ? "rgba(56, 189, 248, 0.08)" : "rgba(255, 255, 255, 0.02)",
                          border: selectedPR?.number === pr.number ? "1px solid #38bdf8" : "1px solid rgba(255, 255, 255, 0.06)",
                          borderRadius: 12,
                          transition: "all 0.2s ease"
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <span style={{ fontWeight: 600, color: "#e2e8f0" }}>PR #{pr.number}</span>
                            {pr.jira_key && (
                              <span className="badge badge-blue" style={{ fontSize: "0.7rem", fontFamily: "var(--font-mono)" }}>{pr.jira_key}</span>
                            )}
                          </div>
                          <span className="badge badge-green" style={{ fontSize: "0.72rem" }}>OPEN</span>
                        </div>
                        
                        <h4 style={{ marginBottom: 8, lineHeight: 1.4 }}>
                          <a href={pr.html_url} target="_blank" rel="noopener noreferrer" style={{ color: "#38bdf8", textDecoration: "none" }} className="pr-link">
                            {pr.title}
                          </a>
                        </h4>
                        
                        <div style={{ fontSize: "0.82rem", color: "#9ca3af", marginBottom: 8 }}>
                          <span>Branch: </span>
                          <span style={{ fontFamily: "var(--font-mono)", color: "#fbbf24" }}>{pr.head}</span>
                          <span> ➡️ </span>
                          <span style={{ fontFamily: "var(--font-mono)", color: "#9ca3af" }}>{pr.base}</span>
                          <br />
                          <span style={{ display: "inline-block", marginTop: 4 }}>Author: <strong>@{pr.assignee || "unknown"}</strong></span>
                        </div>
                        
                        <button 
                          onClick={() => handleAuditPR(pr)}
                          className="btn btn-primary"
                          style={{ padding: "8px 16px", fontSize: "0.85rem" }}
                          disabled={loading}
                        >
                          {loading && selectedPR?.number === pr.number ? <div className="spinner" /> : "⚡ Run AI Review"}
                        </button>
                      </div>
                    ))}
                    
                    {openPRs.length === 0 && !openPRsLoading && (
                      <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-muted)" }}>
                        <div style={{ fontSize: "3rem", marginBottom: 16 }}>📥</div>
                        <p style={{ fontWeight: 600, marginBottom: 8, color: "#e2e8f0" }}>No open Pull Requests found</p>
                        <p style={{ fontSize: "0.9rem", lineHeight: 1.5 }}>
                          Push a branch and raise a PR on GitHub. The Review Agent auto-fetches task requirements from the linked Jira issue.
                        </p>
                      </div>
                    )}
                    {openPRsLoading && openPRs.length === 0 && (
                      <div style={{ textAlign: "center", padding: 40 }}><div className="spinner" style={{ margin: "0 auto" }} /></div>
                    )}
                  </div>
                </div>
              </div>

              {/* Scorecard Results Panel */}
              <div>
                <div className="glass-panel" style={{ minHeight: 400 }}>
                  <h3 style={{ color: "#38bdf8", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 20 }}>
                    ⚡ Audit Report & Scorecard
                  </h3>

                  {!selectedPR ? (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 300, color: "var(--text-muted)", textAlign: "center" }}>
                      <div style={{ fontSize: "3rem", marginBottom: 16 }}>🔎</div>
                      <p>Select an active Pull Request from the queue to run the AI Code Review.</p>
                    </div>
                  ) : loading && !reviewResult ? (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 300 }}>
                      <div className="spinner" style={{ width: 40, height: 40, borderWidth: 4, marginBottom: 20 }} />
                      <p style={{ color: "#9ca3af" }}>Review Agent is analyzing PR #{selectedPR.number} git diff...</p>
                    </div>
                  ) : reviewResult ? (
                    <div>
                      {/* Scorecard visualization */}
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
                        <span className={`badge ${reviewResult.scorecard.security_risk === 'HIGH' ? 'badge-red' : (reviewResult.scorecard.security_risk === 'MEDIUM' ? 'badge-orange' : 'badge-green')}`}>
                          {reviewResult.scorecard.security_risk} RISK
                        </span>
                        <span className={`badge ${reviewResult.scorecard.adherence_to_team_conventions === 'PASS' ? 'badge-green' : 'badge-red'}`}>
                          Conventions: {reviewResult.scorecard.adherence_to_team_conventions}
                        </span>
                        <span className={`badge ${reviewResult.scorecard.requirements_fulfilled === 'YES' ? 'badge-green' : 'badge-red'}`}>
                          Fulfilled: {reviewResult.scorecard.requirements_fulfilled}
                        </span>
                        <span className={`badge ${reviewResult.scorecard.overall_recommendation === 'APPROVE' ? 'badge-green' : 'badge-orange'}`}>
                          REC: {reviewResult.scorecard.overall_recommendation}
                        </span>
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 16, fontSize: "0.9rem", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 20 }}>
                        <div>
                          <strong>Complexity Score:</strong> {reviewResult.scorecard.complexity}/10 <br/>
                          <span style={{ color: "var(--text-secondary)", display: "inline-block", marginTop: 4 }}>{reviewResult.scorecard.complexity_reasoning}</span>
                        </div>
                        <div>
                          <strong>Coverage Delta:</strong> {reviewResult.scorecard.test_coverage_delta > 0 ? `+${reviewResult.scorecard.test_coverage_delta}` : reviewResult.scorecard.test_coverage_delta}% <br/>
                          <span style={{ color: "var(--text-secondary)", display: "inline-block", marginTop: 4 }}>{reviewResult.scorecard.coverage_reasoning}</span>
                        </div>
                        <div>
                          <strong>Security Analysis:</strong> <br/>
                          <span style={{ color: "var(--text-secondary)", display: "inline-block", marginTop: 4 }}>{reviewResult.scorecard.security_reasoning}</span>
                        </div>
                        <div>
                          <strong>Task Requirements Fulfillment:</strong> <br/>
                          <span style={{ color: "var(--text-secondary)", display: "inline-block", marginTop: 4, lineHeight: 1.4 }}>{reviewResult.scorecard.requirements_reasoning}</span>
                        </div>
                      </div>

                      <div style={{ marginTop: 20, fontSize: "0.9rem" }}>
                        <h4 style={{ color: "#38bdf8", marginBottom: 8 }}>👤 Smart Reviewer Selection</h4>
                        <div>Assigned to: <strong>{reviewResult.reviewer.name}</strong> (Git: `@{reviewResult.reviewer.github_username}`)</div>
                        <div style={{ color: "var(--text-secondary)", fontStyle: "italic", marginTop: 6, lineHeight: 1.4 }}>Reason: {reviewResult.assignment_reason}</div>
                      </div>

                      {/* Resolution & Auto-merge */}
                      <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", marginTop: 24, paddingTop: 24 }}>
                        <h4 style={{ color: "#38bdf8", marginBottom: 12 }}>⚙️ Completion & Actions</h4>
                        
                        {reviewResult.scorecard.overall_recommendation === "APPROVE" ? (
                          <div>
                            <div style={{ background: "rgba(52, 211, 153, 0.1)", color: "var(--color-green)", padding: 14, borderRadius: 8, fontSize: "0.9rem", marginBottom: 20, lineHeight: 1.4 }}>
                              {autoMergeMsg || "🎉 PR Auto-merged successfully and Jira task transitioned to Done!"}
                            </div>
                            <button onClick={resetAudit} className="btn btn-secondary">Close Report</button>
                          </div>
                        ) : (
                          <div>
                            <div style={{ background: "rgba(251, 191, 36, 0.1)", color: "var(--color-orange)", padding: 14, borderRadius: 8, fontSize: "0.9rem", marginBottom: 20, lineHeight: 1.4 }}>
                              ⚠️ Bypassed auto-merge due to risk, conventions, or unfulfilled requirements. Requires manual human override.
                            </div>
                            
                            {!manuallyResolved ? (
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                                <button onClick={() => handleManualPR("approve")} className="btn btn-primary" style={{ background: "linear-gradient(135deg, #10b981 0%, #059669 100%)" }} disabled={loading}>
                                  Approve & Merge
                                </button>
                                <button onClick={() => handleManualPR("reject")} className="btn btn-secondary" style={{ border: "1px solid var(--color-red)", color: "var(--color-red)" }} disabled={loading}>
                                  Reject PR
                                </button>
                              </div>
                            ) : (
                              <div>
                                <div style={{ background: "rgba(52, 211, 153, 0.1)", color: "var(--color-green)", padding: 14, borderRadius: 8, fontSize: "0.9rem", marginBottom: 20, lineHeight: 1.4 }}>
                                  {resolutionMsg}
                                </div>
                                <button onClick={resetAudit} className="btn btn-secondary">Close Report</button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "settings" && (
          <div className="glass-panel" style={{ maxWidth: 800, margin: "0 auto" }}>
            <h2 style={{ color: "#38bdf8", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 24 }}>
              ⚙️ Integrations & Team Config
            </h2>
            
            {settingsSuccess && (
              <div style={{ background: "rgba(52, 211, 153, 0.1)", color: "var(--color-green)", padding: 14, borderRadius: 8, fontSize: "0.9rem", marginBottom: 20 }}>
                {settingsSuccess}
              </div>
            )}
            
            {settingsError && (
              <div style={{ background: "rgba(248, 113, 113, 0.1)", color: "var(--color-red)", padding: 14, borderRadius: 8, fontSize: "0.9rem", marginBottom: 20 }}>
                {settingsError}
              </div>
            )}
            
            <form onSubmit={handleSaveSettings}>
              <h3 style={{ color: "#e2e8f0", fontSize: "1.1rem", marginBottom: 16 }}>🔑 API Keys & URLs</h3>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
                <div className="form-group">
                  <label className="form-label">Jira Base URL</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    value={settings.jira_base_url} 
                    onChange={e => setSettings({...settings, jira_base_url: e.target.value})} 
                    placeholder="https://your-domain.atlassian.net"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Jira Email</label>
                  <input 
                    type="email" 
                    className="form-input" 
                    value={settings.jira_email} 
                    onChange={e => setSettings({...settings, jira_email: e.target.value})} 
                    placeholder="email@atlassian.com"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Jira API Token</label>
                  <input 
                    type="password" 
                    className="form-input" 
                    value={settings.jira_api_token} 
                    onChange={e => setSettings({...settings, jira_api_token: e.target.value})} 
                    placeholder="ATATT..."
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Jira Project Key</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    value={settings.jira_project_key} 
                    onChange={e => setSettings({...settings, jira_project_key: e.target.value})} 
                    placeholder="KAN"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">GitHub Token</label>
                  <input 
                    type="password" 
                    className="form-input" 
                    value={settings.github_token} 
                    onChange={e => setSettings({...settings, github_token: e.target.value})} 
                    placeholder="ghp_..."
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">GitHub Owner</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    value={settings.github_owner} 
                    onChange={e => setSettings({...settings, github_owner: e.target.value})} 
                    placeholder="GitHub username or Org"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">GitHub Repository</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    value={settings.github_repo} 
                    onChange={e => setSettings({...settings, github_repo: e.target.value})} 
                    placeholder="todo-app"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Groq API Key</label>
                  <input 
                    type="password" 
                    className="form-input" 
                    value={settings.groq_api_key} 
                    onChange={e => setSettings({...settings, groq_api_key: e.target.value})} 
                    placeholder="gsk_..."
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Slack Bot Token</label>
                  <input 
                    type="password" 
                    className="form-input" 
                    value={settings.slack_bot_token} 
                    onChange={e => setSettings({...settings, slack_bot_token: e.target.value})} 
                    placeholder="xoxb-..."
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Slack Manager Channel</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    value={settings.slack_manager_channel} 
                    onChange={e => setSettings({...settings, slack_manager_channel: e.target.value})} 
                    placeholder="#engineering-manager"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Team Lead Slack ID (for manual reviews)</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    value={settings.team_lead_slack_id || ""} 
                    onChange={e => setSettings({...settings, team_lead_slack_id: e.target.value})} 
                    placeholder="U12345678"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">WIP Capacity Limit (per engineer)</label>
                  <input 
                    type="number" 
                    className="form-input" 
                    value={settings.wip_limit} 
                    onChange={e => setSettings({...settings, wip_limit: parseInt(e.target.value) || 1})} 
                    min="1"
                  />
                </div>
              </div>
              
              <h3 style={{ color: "#e2e8f0", fontSize: "1.1rem", marginBottom: 16, borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: 20 }}>
                👥 Team Engineers
              </h3>
              
              <div style={{ marginBottom: 20 }}>
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>GitHub ID</th>
                      <th>Jira Account ID</th>
                      <th>Slack User ID</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {settings.engineers.map((eng, idx) => (
                      <tr key={idx}>
                        <td><strong>{eng.name}</strong></td>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}>{eng.github_username}</td>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}>{eng.jira_account_id}</td>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}>{eng.slack_user_id || "N/A"}</td>
                        <td>
                          <button 
                            type="button" 
                            onClick={() => handleRemoveEngineer(idx)}
                            className="btn btn-secondary"
                            style={{ padding: "4px 8px", fontSize: "0.75rem", color: "var(--color-red)", borderColor: "rgba(239, 68, 68, 0.2)", width: "auto" }}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {settings.engineers.length === 0 && (
                      <tr>
                        <td colSpan="5" style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.9rem" }}>No team members configured.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr auto", gap: 10, alignItems: "end", marginBottom: 30, background: "rgba(255,255,255,0.01)", padding: 16, borderRadius: 8, border: "1px solid rgba(255,255,255,0.05)" }}>
                <div>
                  <label className="form-label" style={{ fontSize: "0.75rem" }}>Name</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    style={{ padding: 8, fontSize: "0.85rem" }}
                    value={newEng.name} 
                    onChange={e => setNewEng({...newEng, name: e.target.value})}
                    placeholder="e.g. John Doe"
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: "0.75rem" }}>GitHub username</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    style={{ padding: 8, fontSize: "0.85rem" }}
                    value={newEng.github_username} 
                    onChange={e => setNewEng({...newEng, github_username: e.target.value})}
                    placeholder="johndoe"
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: "0.75rem" }}>Jira ID</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    style={{ padding: 8, fontSize: "0.85rem" }}
                    value={newEng.jira_account_id} 
                    onChange={e => setNewEng({...newEng, jira_account_id: e.target.value})}
                    placeholder="557058:abc..."
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: "0.75rem" }}>Slack ID (Optional)</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    style={{ padding: 8, fontSize: "0.85rem" }}
                    value={newEng.slack_user_id} 
                    onChange={e => setNewEng({...newEng, slack_user_id: e.target.value})}
                    placeholder="U12345"
                  />
                </div>
                <button 
                  type="button" 
                  onClick={handleAddEngineer}
                  className="btn btn-secondary" 
                  style={{ padding: "8px 16px", height: 38, width: "auto", fontSize: "0.85rem" }}
                >
                  ➕ Add
                </button>
              </div>
              
              <button 
                type="submit" 
                className="btn btn-primary" 
                style={{ width: "100%", padding: 14 }}
                disabled={loading}
              >
                {loading ? <div className="spinner" /> : "💾 Save & Reload Configuration"}
              </button>
            </form>
          </div>
        )}

        {/* Console / Slack Alert Logs bottom section */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, marginTop: 40 }}>
          <div className="glass-panel">
            <h3 style={{ color: "#38bdf8", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 16 }}>
              💬 Slack Alert Feed
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 12, maxHeight: 280, overflowY: "auto" }}>
              {slackFeed.map((msg, i) => (
                <div key={i} style={{ padding: 14, background: "rgba(255,255,255,0.03)", borderRadius: 8, borderLeft: "4px solid #38bdf8" }}>
                  <div style={{ fontWeight: 600, color: "var(--color-blue)", fontSize: "0.85rem", marginBottom: 4 }}>
                    📢 Channel: {msg.channel}
                  </div>
                  <div style={{ fontSize: "0.9rem" }}>{msg.text}</div>
                </div>
              ))}
              {slackFeed.length === 0 && (
                <div style={{ color: "var(--text-muted)", fontSize: "0.9rem", textAlign: "center", padding: 20 }}>No Slack alerts fired yet.</div>
              )}
            </div>
          </div>

          <div className="glass-panel">
            <h3 style={{ color: "#38bdf8", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12, marginBottom: 16 }}>
              🔗 Inter-Agent Communication Logs
            </h3>
            <div className="console-container">
              {agentLogs.map((log, i) => (
                <div key={i} className="console-line">
                  <span style={{ color: "#6b7280" }}>[{log.timestamp}]</span> <strong>{log.sender}</strong> ➡️ <strong>{log.receiver}</strong> <br/>
                  &nbsp;&nbsp;Topic: <span style={{ color: "var(--color-blue)" }}>{log.topic}</span><br/>
                  &nbsp;&nbsp;Payload: <span style={{ color: "#e2e8f0" }}>{log.content}</span>
                </div>
              ))}
              {agentLogs.length === 0 && (
                <div style={{ color: "var(--text-muted)", textAlign: "center", padding: 20 }}>Waiting for agent communication...</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
