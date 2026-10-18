"""The verdict an agent leaves: a JSON object on the last line of its answer.

The agent's prompt asks for it; whoever runs the agent reads it to know what to record.
"""

import json


def verdict(text: str) -> dict | None:
    """The JSON object the flow leaves on its last line, or None if it did not."""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                return None
    return None
