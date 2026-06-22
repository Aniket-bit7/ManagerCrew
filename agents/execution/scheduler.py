import heapq
from typing import List, Dict, Optional
from agents.planning.schemas import EnrichedSubTask
from agents.shared.config_loader import AppConfig
from agents.execution.tools.jira_write import JiraConnector
from agents.execution.wip import WIPMonitor

class CapacityScheduler:
    def __init__(self, config: AppConfig):
        self.config = config
        self.jira = JiraConnector()
        self.wip_monitor = WIPMonitor()
        
        # Track our round-robin positional pointer indices for each team name
        self.team_pointers: Dict[str, int] = {team.name.upper(): 0 for team in config.teams}

    def allocate_sprint(self, topo_tasks: List[EnrichedSubTask]):
        """
        Processes tasks, creates them live in Jira, maps structural dependencies,
        and manages engineer balance constraints.
        """
        print("\n⚡ Initializing Real-Time Execution Scheduler...")
        
        # 1. Fetch live active workloads from Jira
        current_wip = self.wip_monitor.get_active_wip_counts(self.config.jira_project_key)
        
        # 2. Build our internal tracking map for our team entities
        team_map = self.config.get_team_mapping()
        
        # Map planning IDs (e.g. TASK-001) to real generated Jira Keys (e.g. ENG-12)
        planning_id_to_jira_key: Dict[str, str] = {}

        # 3. Iterate through tasks sequentially (Topological order guarantees dependencies are hit first)
        for task in topo_tasks:
            target_team_name = task.team_label.upper()
            
            # Fallback if a team isn't explicitly configured in your YAML
            if target_team_name not in team_map:
                print(f"⚠️ Team {target_team_name} missing from YAML config. Falling back to first available team.")
                if self.config.teams:
                    target_team_name = self.config.teams[0].name.upper()
                else:
                    print("⚠️ No teams configured in team_config.yaml! Cannot assign engineer.")
                    continue

            team_info = team_map.get(target_team_name)
            if not team_info:
                continue
            engineers = team_info.engineers
            
            assigned_engineer = None
            
            if engineers:
                # Round-Robin algorithm with WIP Limit verification checks
                num_engineers = len(engineers)
                start_index = self.team_pointers[target_team_name]
                
                for i in range(num_engineers):
                    eval_idx = (start_index + i) % num_engineers
                    candidate = engineers[eval_idx]
                    
                    # Read current candidate workload tally
                    candidate_wip = current_wip.get(candidate.jira_account_id, 0)
                    
                    if candidate_wip < self.config.wip_limit:
                        assigned_engineer = candidate
                        # Advance pointer immediately to the next engineer for the next task
                        self.team_pointers[target_team_name] = (eval_idx + 1) % num_engineers
                        # Update local WIP map cache state dynamically
                        current_wip[candidate.jira_account_id] = candidate_wip + 1
                        break
                
                # Overload fallback: if everyone is full, assign to the engineer pointed to originally
                if not assigned_engineer:
                    assigned_engineer = engineers[start_index]
                    self.team_pointers[target_team_name] = (start_index + 1) % num_engineers
                    print(f"🚨 Capacity Overload Alert: All engineers in {target_team_name} are at WIP Limit. Forcing assignment to {assigned_engineer.name}.")

            # 4. Generate the ticket directly inside your Jira instance
            assignee_id = assigned_engineer.jira_account_id if assigned_engineer else None
            assignee_name = assigned_engineer.name if assigned_engineer else "Unassigned"
            
            print(f"🏃 Dispatching task: [{task.id}] '{task.title}' -> {target_team_name} ({assignee_name})")
            
            jira_key = self.jira.create_ticket(
                title=task.title,
                description=task.description,
                team=target_team_name,
                moscow=task.moscow_tier,
                assignee_id=assignee_id
            )
            
            planning_id_to_jira_key[task.id] = jira_key

            # 5. Connect downstream dependency link blocks inside Jira
            for dep_id in task.depends_on_ids:
                if dep_id in planning_id_to_jira_key:
                    parent_jira_key = planning_id_to_jira_key[dep_id]
                    # Link them so that parent_jira_key BLOCKS jira_key
                    self.jira.create_dependency_link(outward_key=parent_jira_key, inward_key=jira_key)

        print("\n✅ Sprint Allocation Complete! All issues dispatched and linked successfully inside Jira.")