#!/usr/bin/env python3
"""
PreToolUse hook: blocks Bash commands that could expose API credentials.
Exit code 2 = hard block (Claude Code respects this 100% of the time).

Configured in .claude/settings.json under hooks.PreToolUse with matcher "Bash".
"""
import json
import sys

BLOCKED_PATTERNS = [
    "cat .env",
    "cat ./.env",
    "less .env",
    "more .env",
    "head .env",
    "tail .env",
    "echo $OPENAI_API_KEY",
    "echo $SERPER_API_KEY",
    "echo $GEMINI_API_KEY",
    "echo $DATAFORSEO_LOGIN",
    "echo $DATAFORSEO_PASSWORD",
    "printenv OPENAI",
    "printenv SERPER",
    "printenv GEMINI",
    "printenv DATAFORSEO",
    "git add .env",
    "git add -A",  # Could include .env if not gitignored
]

def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)  # Can't parse input — allow

    command = data.get("tool_input", {}).get("command", "")

    for pattern in BLOCKED_PATTERNS:
        if pattern in command:
            print(
                f"BLOCKED: Command contains '{pattern}' which could expose credentials. "
                f"Never expose API keys or .env contents.",
                file=sys.stderr
            )
            sys.exit(2)

    sys.exit(0)

if __name__ == "__main__":
    main()