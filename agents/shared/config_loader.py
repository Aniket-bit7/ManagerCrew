import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict

class Engineer(BaseModel):
    name: str
    jira_account_id: str
    slack_user_id: str

class Team(BaseModel):
    name: str
    slack_channel: str
    engineers: List[Engineer]

class AppConfig(BaseModel):
    wip_limit: int = Field(default=2)
    sprint_duration_days: int = Field(default=14)
    jira_project_key: str
    confidence_threshold: float = Field(default=0.60)
    teams: List[Team]

    def get_team_mapping(self) -> Dict[str, Team]:
        return {team.name.upper(): team for team in self.teams}

def load_config(config_path: str = "config/team_config.yaml") -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file missing at {config_path}")
    
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        return AppConfig(**data)