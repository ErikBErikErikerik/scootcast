"""Claude Code hook: remind Claude when an edited Python file has no AI citation.

The course rules require every file with AI-generated code to cite the AI in
the source code. Claude Code runs this script after each Write or Edit and
passes the tool call as JSON on stdin. If the file is a Python file without
the words "AI citation", the printed JSON tells Claude to add the header.

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-26 and reviewed by the project team.
"""

import json
import sys
from pathlib import Path

call = json.load(sys.stdin)
path = Path(call.get("tool_input", {}).get("file_path", ""))

if path.suffix == ".py" and path.is_file() and "AI citation" not in path.read_text():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"{path.name} has no 'AI citation' header yet. The course rules require one: "
                "add it at the top with tool, model and date, like in collector/collect.py."
            ),
        }
    }))
