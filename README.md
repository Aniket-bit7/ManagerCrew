# ManagerCrew

ManagerCrew is an intelligent, automated engineering management system designed to ingest Product Requirements Documents (PRDs), break them down into structured engineering subtasks, detect dependencies, calculate critical paths, and automatically dispatch tasks to teams based on capacity scheduling. 

It leverages advanced natural language processing via Groq for initial parsing and mathematical graph analysis algorithms to ensure project schedules are robust and free of cyclical deadlocks.

## Key Features

- **PRD Ingestion & Multi-Stage Classification**: Uses Groq-powered AI parsing to convert free-text PRDs into structured, categorized engineering subtasks.
- **Dependency Cycle Detection**: Implements Depth-First Search (DFS) to catch potential graph loop cycles and prevent task deadlocks before they happen.
- **Topological Scheduling Compiler**: Uses Kahn's algorithm to establish a clean, dependency-respecting sequence of tasks.
- **Critical Path Method (CPM) & PERT Matrix**: Calculates expected task durations, project variance, and overall sprint completion confidence using mathematical models.
- **Real-Time Capacity Scheduling & Jira Dispatch**: Automatically allocates scheduled tasks to engineering teams (e.g., Frontend, Backend) based on predefined Work-In-Progress (WIP) limits and system configuration.

## System Architecture

The core pipeline processes a raw PRD into assigned, scheduled subtasks through the following flow:

```mermaid
graph TD
    A[Raw PRD Document] --> B[Groq PRD Parser & Classifier]
    B --> C{Cycle Detection Engine - DFS}
    C -- Deadlock Detected --> D[Error / Halt]
    C -- Clean Graph --> E[Topological Scheduling - Kahn's]
    E --> F[CPM & PERT Analysis Matrix]
    F --> G[Sprint Confidence Calculator]
    G --> H[Capacity Scheduler & Execution Dispatcher]
    
    I[team_config.yaml] --> B
    I --> H
    
    H --> J[Jira / Task Management System]
