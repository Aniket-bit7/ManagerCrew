import os
import json
from dotenv import load_dotenv
load_dotenv()

from agents.planning.prd_parser import process_and_enrich_prd
from agents.planning.dag import detect_cycles_dfs, topological_sort_kahn
from agents.planning.pert import run_critical_path_method, calculate_sprint_confidence
from agents.shared.config_loader import load_config
config = load_config()
# Load credentials and configuration


# High-fidelity real-world test prompt text block
sample_prd = """
# MVP Requirement: Payment Processing System
We need to build an online stripe-based payments flow. 

Feature 1: Database Setup
- Subtask: Design database schema for user ledger and wallet balances. Needs backend attention. 

Feature 2: Core Processing API
- Subtask: Build POST /payments/charge endpoint. This requires the DB schema to be complete before implementation.

Feature 3: UI Implementation
- Subtask: Build real-time react payment gateway screen components. This handles the UI views and depends on the API endpoints being built first.
"""

print("🚀 Step 1: Querying Groq and Running Multi-Stage Classification...")
try:
    enriched_tasks = process_and_enrich_prd(sample_prd)
    print(f"✅ Extracted {len(enriched_tasks)} engineering subtasks.")
    
    for task in enriched_tasks:
        print(f"   [{task.id}] {task.title} -> Team: {task.team_label} | Tier: {task.moscow_tier} | Blocks: {task.depends_on_ids}")

    print("\n🚀 Step 2: Testing Cycle Detection Engine...")
    if detect_cycles_dfs(enriched_tasks):
        print("❌ CRITICAL DEADLOCK: Graph loop cycle caught.")
        exit(1)
    print("✅ Graph passes cycle validations cleanly.")

    print("\n🚀 Step 3: Running Topological Scheduling Compiler...")
    sorted_tasks = topological_sort_kahn(enriched_tasks)
    
    print("\n🚀 Step 4: Running CPM and Mathematical PERT Matrix Mapping...")
    metrics, cp_ids, duration, variance = run_critical_path_method(enriched_tasks, sorted_tasks)
    
    # Calculate score against sprint duration bounds in configuration file
    confidence = calculate_sprint_confidence(duration, variance, config.sprint_duration_days)
    
    print(f"📊 Project Calculation Summary Metrics:")
    print(f"   - Expected critical duration: {duration:.2f} working days")
    print(f"   - Critical path task items: {cp_ids}")
    print(f"   - Computed Sprint Completion Confidence Rate: {confidence * 100:.1f}%")

except Exception as e:
    print(f"❌ Execution failure occurred: {str(e)}")