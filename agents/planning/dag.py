from typing import List, Dict, Set
from .schemas import EnrichedSubTask

def build_adjacency_list(tasks: List[EnrichedSubTask]) -> Dict[str, List[str]]:
    """Builds an adjacency list where key is a task, and value is tasks that depend on it."""
    adj = {task.id: [] for task in tasks}
    for task in tasks:
        for dep_id in task.depends_on_ids:
            if dep_id in adj:
                adj[dep_id].append(task.id)
    return adj

def detect_cycles_dfs(tasks: List[EnrichedSubTask]) -> bool:
    """
    Implements White/Gray/Black node coloring algorithm O(V+E).
    Returns True if a cycle exists, False otherwise.
    """
    # 0 = White (Unvisited), 1 = Gray (Visiting), 2 = Black (Fully Processed)
    visited = {task.id: 0 for task in tasks}
    adj = build_adjacency_list(tasks)

    def dfs(node_id: str) -> bool:
        visited[node_id] = 1  # Gray
        for neighbor in adj.get(node_id, []):
            if visited.get(neighbor, 0) == 1:
                return True  # Gray -> Gray back-edge detected!
            if visited.get(neighbor, 0) == 0:
                if dfs(neighbor):
                    return True
        visited[node_id] = 2  # Black
        return False

    for task in tasks:
        if visited[task.id] == 0:
            if dfs(task.id):
                return True
    return False

def topological_sort_kahn(tasks: List[EnrichedSubTask]) -> List[EnrichedSubTask]:
    """
    Computes execution order that respects all structural dependencies.
    Ties within layers are naturally broken by MoSCoW tiers.
    """
    task_map = {task.id: task for task in tasks}
    adj = build_adjacency_list(tasks)
    
    # Calculate in-degrees
    in_degree = {task.id: 0 for task in tasks}
    for task in tasks:
        for dep_id in task.depends_on_ids:
            in_degree[task.id] += 1
            
    # Priority sorting dictionary for MoSCoW
    moscow_weight = {"MUST": 0, "SHOULD": 1, "COULD": 2, "WON'T": 3}
    
    # Track items with zero-in-degree
    queue = [task_map[tid] for tid, deg in in_degree.items() if deg == 0]
    # Sort initial queue by MoSCoW tier
    queue.sort(key=lambda t: moscow_weight.get(t.moscow_tier, 99))
    
    topo_order: List[EnrichedSubTask] = []
    
    while queue:
        # Pop the highest priority unblocked task
        current = queue.pop(0)
        topo_order.append(current)
        
        for neighbor_id in adj.get(current.id, []):
            in_degree[neighbor_id] -= 1
            if in_degree[neighbor_id] == 0:
                neighbor_task = task_map[neighbor_id]
                # Insert dynamically keeping MoSCoW prioritized order intact
                queue.append(neighbor_task)
                queue.sort(key=lambda t: moscow_weight.get(t.moscow_tier, 99))
                
    if len(topo_order) != len(tasks):
        raise ValueError("Cyclic dependency found during topological sort compilation.")
        
    return topo_order