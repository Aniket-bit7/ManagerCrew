import os
import sys
from dotenv import load_dotenv

# Ensure Python can instantly resolve modules in your project root folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environmental configurations from your .env file
load_dotenv()

# --- YOUR ORIGINAL BACKEND ARCHITECTURE IMPORTS ---
from agents.planning.prd_parser import process_and_enrich_prd
from agents.planning.dag import detect_cycles_dfs, topological_sort_kahn
from agents.planning.pert import run_critical_path_method, calculate_sprint_confidence
from agents.shared.config_loader import load_config

# --- STEP 5: EXECUTION DISPATCHER IMPORTS ---
from agents.execution.scheduler import CapacityScheduler

def main():
    print("🚀 Loading System Configuration from team_config.yaml...")
    try:
        config = load_config()
        print(f"✅ Loaded. Target Project Key: '{config.jira_project_key}' | Capacity Limit: {config.wip_limit}")
    except Exception as e:
        print(f"❌ Configuration error: {str(e)}")
        return

    # High-fidelity real-world test prompt text block
    sample_prd = """
    # MVP Requirement: Payment Processing System
    We need to build an online stripe-based payments flow. 

    Feature 1: Secure API Endpoint (Team: BACKEND)
    - Subtask: Build POST /payments/charge endpoint. This sets up the structural handling core for transaction processing.

    Feature 2: Client UI Portal (Team: FRONTEND)
    - Subtask: Build real-time react payment gateway screen components. This manages visual user interfaces and depends on the endpoint being built first.
    """

    print("\n🚀 Step 1: Querying Groq and Running Multi-Stage Classification...")
    try:
        enriched_tasks = process_and_enrich_prd(sample_prd)
        print(f"✅ Extracted {len(enriched_tasks)} engineering subtasks.")
        
        for task in enriched_tasks:
            print(f"   [{task.id}] {task.title} -> Team: {task.team_label} | Tier: {task.moscow_tier} | Blocks: {task.depends_on_ids}")

        print("\n🚀 Step 2: Testing Cycle Detection Engine...")
        if detect_cycles_dfs(enriched_tasks):
            print("❌ CRITICAL DEADLOCK: Graph loop cycle caught.")
            return
        print("✅ Graph passes cycle validations cleanly.")

        print("\n🚀 Step 3: Running Topological Scheduling Compiler...")
        sorted_tasks = topological_sort_kahn(enriched_tasks)
        print("✅ Topological sequence fully established.")
        
        print("\n🚀 Step 4: Running CPM and Mathematical PERT Matrix Mapping...")
        metrics, cp_ids, duration, variance = run_critical_path_method(enriched_tasks, sorted_tasks)
        
        # Calculate score against sprint duration bounds in configuration file
        confidence = calculate_sprint_confidence(duration, variance, config.sprint_duration_days)
        
        print(f"📊 Project Calculation Summary Metrics:")
        print(f"   - Expected critical duration: {duration:.2f} working days")
        print(f"   - Critical path task items: {cp_ids}")
        print(f"   - Computed Sprint Completion Confidence Rate: {confidence * 100:.1f}%")

        # --- NEW INTEGRATION EXECUTION DISPATCH STEP ---
        print("\n🚀 Step 5: Executing Real-Time Capacity Scheduling & Jira Dispatches...")
        scheduler = CapacityScheduler(config=config)
        scheduler.allocate_sprint(sorted_tasks)

        print("\n=== 🎉 ALL PIPELINE STAGES EXECUTED SUCCESSFULLY ===")

    except Exception as e:
        print(f"❌ Execution failure occurred: {str(e)}")

if __name__ == "__main__":
    main()