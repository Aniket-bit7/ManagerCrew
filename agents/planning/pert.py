import math
from typing import List, Dict
from .schemas import EnrichedSubTask

def calculate_pert_metrics(task: EnrichedSubTask) -> tuple[float, float]:
    """Returns (Expected Duration E, Variance Var) for a subtask."""
    # E = (O + 4M + P) / 6
    expected = (task.o + (4 * task.m) + task.p) / 6.0
    # Variance = ((P - O) / 6)^2
    variance = ((task.p - task.o) / 6.0) ** 2
    return expected, variance

def run_critical_path_method(tasks: List[EnrichedSubTask], topo_tasks: List[EnrichedSubTask]) -> tuple[Dict[str, dict], List[str], float, float]:
    """
    Executes Forward and Backward passes across the DAG layout.
    Returns:
       - dict of calculated times (es, ef, ls, lf, float_days, expected, variance)
       - critical_path_ids list
       - critical_path_duration
       - critical_path_variance
    """
    task_map = {task.id: task for task in tasks}
    metrics = {}
    
    # Precompute individual task metrics
    for task in tasks:
        e, var = calculate_pert_metrics(task)
        metrics[task.id] = {
            "expected": e,
            "variance": var,
            "es": 0.0,
            "ef": 0.0,
            "ls": 0.0,
            "lf": 0.0,
            "float_days": 0.0
        }

    # 1. Forward Pass (Calculate Early Start & Early Finish)
    for task in topo_tasks:
        if task.depends_on_ids:
            # ES = max(EF of predecessors)
            metrics[task.id]["es"] = max(metrics[dep_id]["ef"] for dep_id in task.depends_on_ids if dep_id in metrics)
        else:
            metrics[task.id]["es"] = 0.0
            
        metrics[task.id]["ef"] = metrics[task.id]["es"] + metrics[task.id]["expected"]

    # Total project duration is the max early finish
    max_ef = max(m["ef"] for m in metrics.values()) if metrics else 0.0

    # 2. Backward Pass (Calculate Late Start & Late Finish)
    # Build a reverse lookup for successors
    successors: Dict[str, List[str]] = {task.id: [] for task in tasks}
    for task in tasks:
        for dep_id in task.depends_on_ids:
            if dep_id in successors:
                successors[dep_id].append(task.id)

    for task in reversed(topo_tasks):
        if successors[task.id]:
            # LF = min(LS of successors)
            metrics[task.id]["lf"] = min(metrics[succ_id]["ls"] for succ_id in successors[task.id])
        else:
            metrics[task.id]["lf"] = max_ef
            
        metrics[task.id]["ls"] = metrics[task.id]["lf"] - metrics[task.id]["expected"]
        # Float = LS - ES
        metrics[task.id]["float_days"] = metrics[task.id]["ls"] - metrics[task.id]["es"]

    # 3. Extract Critical Path Components
    critical_path_ids = []
    cp_duration = 0.0
    cp_variance = 0.0
    
    for tid, m in metrics.items():
        # Float close to zero indicates critical path
        if abs(m["float_days"]) < 1e-5:
            critical_path_ids.append(tid)
            cp_duration += m["expected"]
            cp_variance += m["variance"]

    return metrics, critical_path_ids, cp_duration, cp_variance

def calculate_sprint_confidence(expected_days: float, variance: float, target_days: int) -> float:
    """
    Computes statistical confidence using the Standard Normal CDF Approximation.
    """
    if variance <= 0:
        return 1.0 if expected_days <= target_days else 0.0
        
    std_dev = math.sqrt(variance)
    z = (target_days - expected_days) / std_dev
    
    # Error function based Standard Normal Cumulative Distribution Function (CDF)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))