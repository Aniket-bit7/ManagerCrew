from typing import List, Dict, Set
from collections import deque
from schemas import TaskNode

class DependencyGraph:
    def __init__(self, tasks: Dict[str, TaskNode]):
        self.tasks = tasks  # Map of ticket_id -> TaskNode
        self.adj_list: Dict[str, List[str]] = {tid: [] for tid in tasks}
        self.in_degree: Dict[str, int] = {tid: 0 for tid in tasks}
        
        self._build_graph()

    def _build_graph(self):
        """Builds adjacency list and calculates in-degrees from 'depends_on' links."""
        for tid, node in self.tasks.items():
            for parent in node.depends_on:
                if parent in self.adj_list:  # Only link if parent wasn't filtered out
                    self.adj_list[parent].append(tid)
                    self.in_degree[tid] += 1

    def detect_cycle(self) -> bool:
        """
        Detects cycles using White(0), Gray(1), Black(2) coloring scheme.
        Returns True if a cycle is found.
        """
        visited = {tid: 0 for tid in self.tasks}  # 0: Unvisited, 1: Visiting, 2: Fully Processed

        def dfs(u: str) -> bool:
            visited[u] = 1  # Gray
            for v in self.adj_list[u]:
                if visited[v] == 1:  # Gray to Gray back-edge found
                    return True
                if visited[v] == 0:
                    if dfs(v):
                        return True
            visited[u] = 2  # Black
            return False

        for tid in self.tasks:
            if visited[tid] == 0:
                if dfs(tid):
                    return True
        return False

    def kahn_topological_sort(self) -> List[str]:
        """
        Returns a topologically sorted list of ticket IDs using Kahn's algorithm.
        Throws an exception if a cycle is found during processing.
        """
        in_deg = self.in_degree.copy()
        queue = deque([tid for tid, deg in in_deg.items() if deg == 0])
        topo_order = []

        while queue:
            u = queue.popleft()
            topo_order.append(u)

            for v in self.adj_list[u]:
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    queue.append(v)

        if len(topo_order) != len(self.tasks):
            raise ValueError("PolicyViolation: Graph contains cycles. Aborting topological sort.")
        
        return topo_order

    def compute_critical_path(self, topo_order: List[str]) -> List[str]:
        """
        Computes ES, EF, LS, LF, and Float using Forward and Backward passes.
        Returns a list of ticket IDs on the critical path (float == 0).
        """
        # --- 1. Forward Pass (Compute ES and EF) ---
        for tid in topo_order:
            node = self.tasks[tid]
            # ES is the max EF of all dependency parents
            parents = [self.tasks[p] for p in node.depends_on if p in self.tasks]
            node.es = max([p.ef for p in parents], default=0.0)
            node.ef = node.es + node.expected_duration

        # --- 2. Backward Pass (Compute LF and LS) ---
        # Find max EF to establish the project end deadline
        max_ef = max([node.ef for node in self.tasks.values()], default=0.0)

        for tid in reversed(topo_order):
            node = self.tasks[tid]
            children = self.adj_list[tid]
            if not children:
                node.lf = max_ef
            else:
                node.lf = min([self.tasks[c].ls for c in children])
            node.ls = node.lf - node.expected_duration
            node.float_time = round(node.lf - node.ef, 4)

        # --- 3. Extract Critical Path ---
        critical_path = [tid for tid, node in self.tasks.items() if node.float_time == 0.0]
        return critical_path