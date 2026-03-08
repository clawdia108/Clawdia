#!/usr/bin/env python3
"""
NLP Task Creation — Natural language to structured task via Ollama
===================================================================
Parse plain language task descriptions into structured tasks with:
- Priority (P0-P3)
- Target agent
- Required capabilities
- Extracted keywords
- Deadline estimation

Usage:
  python3 scripts/nlp_task.py "research Keboola's new product launch"
  python3 scripts/nlp_task.py "draft follow-up emails for stale deals" --auto
  python3 scripts/nlp_task.py --interactive
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")

# Keyword → capability mapping
CAPABILITY_KEYWORDS = {
    "email": "email", "draft": "email", "write": "writing", "compose": "email",
    "score": "scoring", "pipeline": "crm", "deal": "crm", "pipedrive": "crm",
    "research": "research", "intel": "research", "competitor": "research",
    "calendar": "calendar", "meeting": "calendar", "schedule": "scheduling",
    "review": "review", "check": "review", "audit": "review",
    "focus": "planning", "plan": "planning", "prioritize": "planning",
    "knowledge": "knowledge", "sync": "knowledge", "archive": "knowledge",
    "code": "code", "analyze": "analysis", "fix": "code",
    "track": "tracking", "gamif": "gamification",
}

# Priority keywords
PRIORITY_KEYWORDS = {
    "urgent": "P0", "critical": "P0", "asap": "P0", "immediately": "P0",
    "important": "P1", "high": "P1", "soon": "P1", "today": "P1",
    "when possible": "P2", "normal": "P2",
    "low": "P3", "whenever": "P3", "nice to have": "P3", "someday": "P3",
}

# Agent capability map (from agent_lifecycle.py)
AGENT_CAPABILITIES = {
    "spojka": ["briefing", "synthesis"],
    "obchodak": ["crm", "scoring"],
    "postak": ["email", "drafting"],
    "strateg": ["research", "intel"],
    "kalendar": ["calendar", "scheduling"],
    "kontrolor": ["review", "quality"],
    "archivar": ["knowledge", "archive"],
    "udrzbar": ["crm", "priorities"],
    "textar": ["writing", "email"],
    "hlidac": ["tracking", "gamification"],
    "planovac": ["planning", "focus"],
    "vyvojar": ["code", "analysis"],
}


def ollama_parse(text, timeout=30):
    """Use Ollama to parse task description into structured data."""
    prompt = f"""Parse this task description into structured data. Return ONLY valid JSON, no other text.

Task: "{text}"

Return JSON with these fields:
- "title": short imperative task title (max 60 chars)
- "priority": one of "P0" (critical/urgent), "P1" (high/today), "P2" (normal), "P3" (low)
- "capabilities": list of required capabilities from: crm, scoring, email, writing, research, intel, calendar, scheduling, review, quality, knowledge, archive, planning, focus, code, analysis, tracking, gamification
- "keywords": list of 3-5 key terms extracted
- "deadline_days": estimated days to complete (1-30)
- "description": one-sentence description of what needs to be done

JSON:"""

    try:
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "http://localhost:11434/api/generate",
             "-d", json.dumps({
                 "model": "llama3.1:8b",
                 "prompt": prompt,
                 "stream": False,
                 "options": {"temperature": 0.1, "num_predict": 300},
             })],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0:
            response = json.loads(result.stdout)
            text_response = response.get("response", "")
            # Extract JSON from response
            start = text_response.find("{")
            end = text_response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text_response[start:end])
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def rule_based_parse(text):
    """Fallback: parse task using rule-based heuristics."""
    text_lower = text.lower()

    # Extract priority
    priority = "P2"  # default
    for keyword, prio in PRIORITY_KEYWORDS.items():
        if keyword in text_lower:
            priority = prio
            break

    # Extract capabilities
    capabilities = []
    for keyword, cap in CAPABILITY_KEYWORDS.items():
        if keyword in text_lower and cap not in capabilities:
            capabilities.append(cap)

    if not capabilities:
        capabilities = ["research"]  # default

    # Extract keywords
    stop_words = {"the", "a", "an", "to", "for", "of", "in", "on", "at", "and", "or", "is", "it", "be"}
    words = [w.strip(".,!?\"'") for w in text.split() if len(w) > 2]
    keywords = [w for w in words if w.lower() not in stop_words][:5]

    # Generate title
    title = text[:60].strip()
    if len(text) > 60:
        title = title[:57] + "..."

    return {
        "title": title,
        "priority": priority,
        "capabilities": capabilities,
        "keywords": keywords,
        "deadline_days": 3,
        "description": text,
    }


def find_best_agent(capabilities):
    """Find the best agent for given capabilities."""
    scores = {}
    for agent, caps in AGENT_CAPABILITIES.items():
        overlap = len(set(capabilities) & set(caps))
        if overlap > 0:
            scores[agent] = overlap

    if not scores:
        return None
    return max(scores, key=scores.get)


def create_structured_task(text, auto=False):
    """Parse natural language and create structured task."""
    # Try Ollama first, fall back to rules
    parsed = ollama_parse(text)
    method = "ollama"
    if not parsed:
        parsed = rule_based_parse(text)
        method = "rules"

    # Find best agent
    capabilities = parsed.get("capabilities", [])
    best_agent = find_best_agent(capabilities)

    # Build structured task
    deadline = datetime.now() + timedelta(days=parsed.get("deadline_days", 3))
    task = {
        "title": parsed.get("title", text[:60]),
        "description": parsed.get("description", text),
        "priority": parsed.get("priority", "P2"),
        "required_capabilities": capabilities,
        "keywords": parsed.get("keywords", []),
        "recommended_agent": best_agent,
        "deadline": deadline.isoformat(),
        "parse_method": method,
        "original_text": text,
        "created_at": datetime.now().isoformat(),
    }

    # Show task for confirmation
    print(f"\n{'='*50}")
    print(f"  Parsed Task ({method})")
    print(f"{'='*50}")
    print(f"  Title:    {task['title']}")
    print(f"  Priority: {task['priority']}")
    print(f"  Agent:    {task['recommended_agent'] or 'unassigned'}")
    print(f"  Caps:     {', '.join(task['required_capabilities'])}")
    print(f"  Keywords: {', '.join(task['keywords'])}")
    print(f"  Deadline: {deadline.strftime('%Y-%m-%d')}")
    print(f"{'='*50}")

    if auto:
        return add_to_queue(task)

    # Ask for confirmation
    print("\n  [Enter] to add | [e] to edit | [c] to cancel")
    try:
        choice = input("  > ").strip().lower()
        if choice == "c":
            print("  Cancelled.")
            return None
        elif choice == "e":
            # Quick edit
            new_priority = input(f"  Priority [{task['priority']}]: ").strip()
            if new_priority:
                task["priority"] = new_priority
            new_agent = input(f"  Agent [{task['recommended_agent']}]: ").strip()
            if new_agent:
                task["recommended_agent"] = new_agent
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return None

    return add_to_queue(task)


def add_to_queue(task):
    """Add parsed task to the priority queue."""
    try:
        sys.path.insert(0, str(BASE / "scripts"))
        from task_queue import TaskPriorityQueue
        queue = TaskPriorityQueue()
        task_id = queue.enqueue(
            title=task["title"],
            description=task["description"],
            priority=task["priority"],
            required_capabilities=task["required_capabilities"],
        )
        print(f"\n  Added to queue: {task_id}")
        print(f"  Agent: {task['recommended_agent'] or 'auto-assign on dispatch'}")
        return task_id
    except Exception as e:
        print(f"\n  Error adding to queue: {e}")
        # Fallback: save to file
        tasks_file = BASE / "control-plane" / "nlp-tasks.jsonl"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tasks_file, "a") as f:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
        print(f"  Saved to {tasks_file}")
        return None


def interactive_mode():
    """Interactive task creation loop."""
    print("\n  NLP Task Creator — Type tasks in plain language (Ctrl+C to exit)")
    print("  Prefix with ! for auto-add (no confirmation)\n")

    while True:
        try:
            text = input("  task> ").strip()
            if not text:
                continue
            auto = text.startswith("!")
            if auto:
                text = text[1:].strip()
            create_structured_task(text, auto=auto)
            print()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye!")
            break


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--interactive":
        interactive_mode()
    else:
        text = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
        auto = "--auto" in sys.argv
        create_structured_task(text, auto=auto)
