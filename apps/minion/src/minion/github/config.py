from pydantic import BaseModel


class GitHubConfig(BaseModel):
    repo: str = ""
    poll_interval: int = 60
    labels: dict[str, str] = {
        "plan": "minion:plan",
        "planning": "minion:planning",
        "planned": "minion:planned",
        "implement": "minion:implement",
        "implementing": "minion:implementing",
        "done": "minion:done",
    }
