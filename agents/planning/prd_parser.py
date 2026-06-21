import json
from typing import List
from .schemas import PRDParsedPayload, EnrichedSubTask
from .classifier import rule_based_team_classify, llm_fallback_classify, classify_moscow
from groq import Groq

client = Groq()

def parse_prd_to_raw_json(prd_text: str) -> PRDParsedPayload:
    prompt = f"""You are an advanced technical architect. Break down the following Product Requirement Document (PRD) into architectural features and granular engineering subtasks.
For each subtask, estimate the Three-Point PERT times in days (Optimistic, Most Likely, Pessimistic). Ensure Optimistic <= Most Likely <= Pessimistic.
Identify internal dependencies using subtask titles.

[EXTERNAL_START]
{prd_text}
[EXTERNAL_END]

You must output valid JSON matching this schema:
{{
  "features": [
    {{
      "feature_name": "string",
      "subtasks": [
        {{
          "title": "string",
          "description": "string",
          "acceptance_criteria": ["string"],
          "optimistic_days": float,
          "most_likely_days": float,
          "pessimistic_days": float,
          "depends_on_titles": ["string"]
        }}
      ]
    }}
  ]
}}"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1
    )
    
    raw_data = json.loads(completion.choices[0].message.content)
    return PRDParsedPayload(**raw_data)

def process_and_enrich_prd(prd_text: str) -> List[EnrichedSubTask]:
    parsed = parse_prd_to_raw_json(prd_text)
    enriched_tasks: List[EnrichedSubTask] = []
    
    # 1. First flat pass to generate deterministic IDs matching titles
    title_to_id_map = {}
    counter = 1
    
    all_raw_tasks = []
    for feature in parsed.features:
        for subtask in feature.subtasks:
            task_id = f"TASK-{str(counter).zfill(3)}"
            title_to_id_map[subtask.title.strip().lower()] = task_id
            all_raw_tasks.append((task_id, feature.feature_name, subtask))
            counter += 1
            
    # 2. Stage-Two Hybrid Enrichment Pass
    for task_id, feat_name, subtask in all_raw_tasks:
        # Team Assignment Hook
        team = rule_based_team_classify(subtask.title + " " + subtask.description)
        if not team:
            team = llm_fallback_classify(subtask.title, subtask.description)
            
        # MoSCoW Assignment Hook
        moscow = classify_moscow(subtask.title, subtask.description)
        
        # Dependency Mapping matching string references
        dependencies = []
        for dep_title in subtask.depends_on_titles:
            dep_key = dep_title.strip().lower()
            if dep_key in title_to_id_map:
                dependencies.append(title_to_id_map[dep_key])
                
        enriched_tasks.append(EnrichedSubTask(
            id=task_id,
            feature_name=feat_name,
            title=subtask.title,
            description=subtask.description,
            acceptance_criteria=subtask.acceptance_criteria,
            team_label=team,
            moscow_tier=moscow,
            o=subtask.optimistic_days,
            m=subtask.most_likely_days,
            p=subtask.pessimistic_days,
            depends_on_ids=dependencies
        ))
        
    return enriched_tasks