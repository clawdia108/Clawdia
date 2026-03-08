#!/usr/bin/env python3
"""
Clawdia Centralized Configuration
===================================
Single source of truth for every path, threshold, constant, and agent
definition used across the OpenClaw system.

Usage:
    from config import *
    # or
    from scripts.config import BASE, AGENTS, load_secrets
"""

from pathlib import Path

# ============================================================
# 1. BASE PATH
# ============================================================

BASE = Path("/Users/josefhofman/Clawdia")

# ============================================================
# 2. PATHS — Logs
# ============================================================

LOGS_DIR = BASE / "logs"
ORCHESTRATOR_LOG = LOGS_DIR / "orchestrator.log"
PID_FILE = LOGS_DIR / "orchestrator.pid"
COST_LOG = LOGS_DIR / "cost-tracker.json"
CIRCUIT_STATE_FILE = LOGS_DIR / "circuit-breaker.json"
EVENT_LOG = LOGS_DIR / "events.jsonl"
RECOVERY_LOG = LOGS_DIR / "recovery.log"
BUS_LOG = LOGS_DIR / "bus.log"
WORKFLOW_LOG = LOGS_DIR / "workflow.log"
LIFECYCLE_LOG = LOGS_DIR / "agent-lifecycle.log"
PERF_FILE = LOGS_DIR / "agent-performance.json"
NOTIFICATION_STATE_FILE = LOGS_DIR / "notification-state.json"
LEARNING_LOG = LOGS_DIR / "learning.log"
OUTCOME_LOG = LOGS_DIR / "outcomes.jsonl"
DRAFT_LOG = LOGS_DIR / "draft-generator.log"
SCORER_LOG = LOGS_DIR / "lead-scorer.log"
SALES_AUTOPILOT_LOG = LOGS_DIR / "sales-autopilot.log"

# ============================================================
# 2b. PATHS — Triggers
# ============================================================

TRIGGER_DIR = BASE / "triggers"
TRIGGER_OUTBOX = TRIGGER_DIR / "outbox"
TRIGGER_PROCESSED = TRIGGER_DIR / "processed"

# ============================================================
# 2c. PATHS — Approval Queue
# ============================================================

APPROVAL_DIR = BASE / "approval-queue"
APPROVAL_PENDING = APPROVAL_DIR / "pending"
APPROVAL_APPROVED = APPROVAL_DIR / "approved"
APPROVAL_REJECTED = APPROVAL_DIR / "rejected"
APPROVAL_EXPIRED = APPROVAL_DIR / "expired"

# ============================================================
# 2d. PATHS — Agent Bus
# ============================================================

BUS_DIR = BASE / "bus"
BUS_OUTBOX = BUS_DIR / "outbox"
BUS_INBOX = BUS_DIR / "inbox"
BUS_PROCESSED = BUS_DIR / "processed"
BUS_DEAD_LETTER = BUS_DIR / "dead-letter"
BUS_COWORK_STATUS = BUS_DIR / "cowork-status"

# ============================================================
# 2e. PATHS — Workflows
# ============================================================

WORKFLOW_DEFS_DIR = BASE / "workflows" / "definitions"
WORKFLOW_RUNS_DIR = BASE / "workflows" / "runs"
WORKFLOW_COMPLETED_DIR = BASE / "workflows" / "completed"

# ============================================================
# 2f. PATHS — State & Knowledge
# ============================================================

STATE_FILE = BASE / "knowledge" / "EXECUTION_STATE.json"
HEARTBEAT_FILE = BASE / "memory" / "HEARTBEAT.md"
LEARNING_FILE = BASE / "knowledge" / "AGENT_LEARNINGS.json"
KNOWLEDGE_INSIGHTS = BASE / "knowledge" / "AGENT_INSIGHTS.md"
TODAY_SUMMARY = BASE / "knowledge" / "TODAY_SUMMARY.md"
IMPROVEMENTS_FILE = BASE / "knowledge" / "IMPROVEMENTS.md"
ESCALATION_ALERTS = BASE / "knowledge" / "ESCALATION_ALERTS.json"
USER_DIGEST_AM = BASE / "knowledge" / "USER_DIGEST_AM.md"

# ============================================================
# 2g. PATHS — Control Plane
# ============================================================

AGENT_STATE_FILE = BASE / "control-plane" / "agent-states.json"
AGENT_REGISTRY = BASE / "control-plane" / "agent-registry.json"
MODEL_ROUTER_FILE = BASE / "control-plane" / "model-router.json"
OUTPUT_CONTRACTS_FILE = BASE / "control-plane" / "output-contracts.json"
REVIEW_GATES_FILE = BASE / "control-plane" / "review-gates.json"

# ============================================================
# 2h. PATHS — Tasks
# ============================================================

TASKS_OPEN_DIR = BASE / "tasks" / "open"
TASKS_DONE_DIR = BASE / "tasks" / "done"
WORKBOARD_FILE = BASE / "WORKBOARD.md"

# ============================================================
# 2i. PATHS — Reviews
# ============================================================

REVIEW_IN_PROGRESS_DIR = BASE / "reviews" / "in-progress"
PENDING_REVIEWS_FILE = BASE / "reviews" / "PENDING_REVIEWS.md"
SCORECARD_FILE = BASE / "reviews" / "daily-scorecard" / "SCOREBOARD.md"
SCORE_STATE_FILE = BASE / "reviews" / "daily-scorecard" / "score_state.json"
WEEKLY_REPORT_FILE = BASE / "reviews" / "daily-scorecard" / "WEEKLY_REPORT.md"
MISSION_CONTROL_FILE = BASE / "MISSION_CONTROL.md"

# ============================================================
# 2j. PATHS — Pipedrive / Sales
# ============================================================

PIPEDRIVE_DIR = BASE / "pipedrive"
STALE_DEALS_FILE = PIPEDRIVE_DIR / "STALE_DEALS.md"
DEAL_SCORING_FILE = PIPEDRIVE_DIR / "DEAL_SCORING.md"
PIPELINE_STATUS_FILE = PIPEDRIVE_DIR / "PIPELINE_STATUS.md"
SCORING_LOG_FILE = PIPEDRIVE_DIR / "SCORING_LOG.md"
DEALS_COMPACT_FILE = PIPEDRIVE_DIR / "pipedrive_deals_compact.json"
PIPEDRIVE_ENV_FILE = BASE / ".secrets" / "pipedrive.env"

# ============================================================
# 2k. PATHS — Drafts & Content
# ============================================================

DRAFTS_DIR = BASE / "drafts"

# ============================================================
# 2l. PATHS — Secrets
# ============================================================

SECRETS_DIR = BASE / ".secrets"
ALL_CREDENTIALS_FILE = SECRETS_DIR / "ALL_CREDENTIALS.env"

# ============================================================
# 2m. PATHS — Scripts (for subprocess calls)
# ============================================================

SCRIPTS_DIR = BASE / "scripts"
SCRIPT_NOTIFY = SCRIPTS_DIR / "notify.sh"
SCRIPT_HEARTBEAT = SCRIPTS_DIR / "heartbeat-check.sh"
SCRIPT_OLLAMA_ROUTER = SCRIPTS_DIR / "ollama-router.sh"
SCRIPT_SALES_AUTOPILOT = SCRIPTS_DIR / "sales-autopilot.sh"
SCRIPT_MORNING_BRIEFING = SCRIPTS_DIR / "morning-briefing.sh"
SCRIPT_KNOWLEDGE_SYNC = SCRIPTS_DIR / "knowledge_sync.py"
SCRIPT_ADHD_SCORECARD = SCRIPTS_DIR / "adhd-scorecard.py"
SCRIPT_LEAD_SCORER = SCRIPTS_DIR / "pipedrive_lead_scorer.py"

# ============================================================
# 3. TIMING CONSTANTS
# ============================================================

CYCLE_SECONDS = 1800                    # 30 min orchestrator cycles
WORK_HOURS = (7, 20)                    # Active window (7 AM - 8 PM)
NIGHTLY_HOUR = 23                       # Nightly tasks run at 11 PM
MORNING_BRIEFING_WINDOW = (7, 9)        # Morning briefing generation window
ERROR_RETRY_SECONDS = 300               # Wait 5 min on orchestrator error
RECOVERY_TIMEOUT_SECONDS = 120          # Max time for a recovery script
SALES_AUTOPILOT_TIMEOUT = 180           # Max time for sales-autopilot.sh
MORNING_BRIEFING_TIMEOUT = 120          # Max time for morning-briefing.sh
KNOWLEDGE_SYNC_TIMEOUT = 60             # Max time for knowledge_sync.py
SCORECARD_TIMEOUT = 30                  # Max time for adhd-scorecard.py
HEARTBEAT_TIMEOUT = 30                  # Max time for heartbeat-check.sh
NOTIFY_TIMEOUT = 10                     # Max time for notify.sh
OLLAMA_TIMEOUT = 60                     # Default Ollama call timeout
OLLAMA_HEALTH_TIMEOUT = 5               # Ollama health check timeout

# ============================================================
# 3b. TIMING — Approval & Triggers
# ============================================================

APPROVAL_EXPIRY_HOURS = 48              # Pending approvals expire after 48h
TRIGGER_CLEANUP_DAYS = 7                # Remove processed triggers older than 7d
EVENT_LOG_MAX_LINES = 10000             # Trim events.jsonl beyond this
EVENT_LOG_MAX_BYTES = 1_000_000         # Trigger trim when events.jsonl exceeds 1MB
ORCHESTRATOR_LOG_MAX_BYTES = 500_000    # Rotate orchestrator.log at 500KB
SCORER_LOG_MAX_BYTES = 200_000          # Trim lead-scorer.log at 200KB

# ============================================================
# 3c. TIMING — Task Escalation
# ============================================================

OVERDUE_WARN_HOURS = 1
OVERDUE_CRITICAL_HOURS = 4
BLOCKED_ESCALATE_HOURS = 24
STALE_WARN_HOURS = 12
STALE_CRITICAL_HOURS = 24
STALE_THRESHOLD_HOURS = 24              # knowledge_sync stale output threshold

# ============================================================
# 4. AGENT DEFINITIONS (orchestrator outputs)
# ============================================================

AGENT_OUTPUTS = {
    "spojka": {
        "file": "knowledge/USER_DIGEST_AM.md",
        "max_hours": 24,
        "recovery": "morning-briefing.sh",
    },
    "obchodak": {
        "file": "pipedrive/PIPELINE_STATUS.md",
        "max_hours": 48,
        "recovery": "pipedrive_lead_scorer.py",
    },
    "postak": {
        "file": "inbox/INBOX_DIGEST.md",
        "max_hours": 24,
        "recovery": None,
    },
    "strateg": {
        "file": "intel/DAILY-INTEL.md",
        "max_hours": 48,
        "recovery": None,
    },
    "kalendar": {
        "file": "calendar/TODAY.md",
        "max_hours": 24,
        "recovery": None,
    },
    "kontrolor": {
        "file": "reviews/SYSTEM_HEALTH.md",
        "max_hours": 72,
        "recovery": None,
    },
    "archivar": {
        "file": "knowledge/IMPROVEMENTS.md",
        "max_hours": 72,
        "recovery": "knowledge_sync.py",
    },
}

# ============================================================
# 4b. AGENT DEFINITIONS (lifecycle — capabilities & tiers)
# ============================================================

AGENTS = {
    "spojka": {
        "display": "Spojka",
        "tier": "economy",
        "capabilities": ["briefing", "synthesis"],
    },
    "obchodak": {
        "display": "Obchod\u00e1k",
        "tier": "economy",
        "capabilities": ["crm", "scoring"],
    },
    "postak": {
        "display": "Po\u0161\u0165\u00e1k",
        "tier": "standard",
        "capabilities": ["email", "drafting"],
    },
    "strateg": {
        "display": "Strat\u00e9g",
        "tier": "standard",
        "capabilities": ["research", "intel"],
    },
    "kalendar": {
        "display": "Kalend\u00e1\u0159",
        "tier": "economy",
        "capabilities": ["calendar", "scheduling"],
    },
    "kontrolor": {
        "display": "Kontrolor",
        "tier": "economy",
        "capabilities": ["review", "quality"],
    },
    "archivar": {
        "display": "Archiv\u00e1\u0159",
        "tier": "economy",
        "capabilities": ["knowledge", "archive"],
    },
    "udrzbar": {
        "display": "\u00dadržbá\u0159",
        "tier": "economy",
        "capabilities": ["crm", "priorities"],
    },
    "textar": {
        "display": "Texta\u0159",
        "tier": "standard",
        "capabilities": ["writing", "email"],
    },
    "hlidac": {
        "display": "Hl\u00edda\u010d",
        "tier": "free",
        "capabilities": ["tracking", "gamification"],
    },
    "planovac": {
        "display": "Pl\u00e1nova\u010d",
        "tier": "economy",
        "capabilities": ["planning", "focus"],
    },
    "vyvojar": {
        "display": "V\u00fdvoj\u00e1\u0159",
        "tier": "premium",
        "capabilities": ["code", "analysis"],
    },
}

# ============================================================
# 4c. AGENT STATE MACHINE — Valid Transitions
# ============================================================

AGENT_TRANSITIONS = {
    "idle": ["assigned"],
    "assigned": ["working", "idle"],
    "working": ["reviewing", "done", "failed", "idle"],
    "reviewing": ["done", "working", "failed"],
    "done": ["idle"],
    "failed": ["idle", "assigned"],
}

# ============================================================
# 4d. AGENT STUCK THRESHOLDS (minutes)
# ============================================================

STUCK_THRESHOLDS = {
    "assigned": 30,     # 30 min before escalation
    "working": 120,     # 2 hours
    "reviewing": 60,    # 1 hour
}

# Auto-reset to idle when stuck for 3x the threshold
STUCK_AUTO_RESET_MULTIPLIER = 3

# ============================================================
# 4e. AGENT RECOVERY
# ============================================================

MAX_RECOVERY_ATTEMPTS = 3

# ============================================================
# 5. BUS SUBSCRIPTIONS (topic -> subscribers)
# ============================================================

BUS_SUBSCRIPTIONS = {
    # Sales pipeline events
    "pipeline.scored": ["postak", "udrzbar", "textar"],
    "pipeline.stale_deals": ["postak", "udrzbar"],
    "pipeline.deal_won": ["hlidac", "textar", "archivar"],
    "pipeline.deal_lost": ["hlidac", "strateg"],
    "pipeline.high_value_deal": ["obchodak", "textar"],

    # Content events
    "content.draft_ready": ["kontrolor"],
    "content.review_passed": ["postak"],
    "content.review_failed": ["textar", "postak"],
    "content.approved": ["postak"],

    # System events
    "system.morning_briefing": ["kalendar", "planovac", "udrzbar"],
    "system.agent_recovered": ["kontrolor", "hlidac"],
    "system.health_check": ["kontrolor"],
    "system.knowledge_synced": ["archivar", "strateg"],
    "system.nightly_complete": ["hlidac"],

    # Approval events
    "approval.submitted": ["kontrolor"],
    "approval.approved": ["postak", "textar"],
    "approval.rejected": ["textar"],

    # Research events
    "research.intel_ready": ["textar", "obchodak"],
    "research.competitor_found": ["strateg", "udrzbar"],

    # Calendar events
    "calendar.meeting_soon": ["planovac", "kalendar"],
    "calendar.day_planned": ["planovac"],

    # Cowork bridge events (Claude Desktop scheduled tasks)
    "system.cowork_complete": ["kontrolor", "hlidac"],
}

# Bus message defaults
BUS_DEFAULT_TTL_HOURS = 24
BUS_MESSAGE_MAX_RETRIES = 3
BUS_CLEANUP_MAX_AGE_DAYS = 7
BUS_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

# ============================================================
# 6. TRIGGER ROUTING RULES (event -> agent actions)
# ============================================================

TRIGGER_ROUTES = {
    "pipeline_scored": [
        ("postak", "generate_follow_ups"),
        ("udrzbar", "update_priorities"),
    ],
    "stale_deals_found": [
        ("postak", "draft_follow_ups"),
    ],
    "morning_briefing_ready": [
        ("kalendar", "update_today"),
        ("planovac", "generate_plan"),
    ],
    "deal_won": [
        ("hlidac", "log_achievement"),
        ("textar", "draft_onboarding"),
    ],
    "approval_approved": [
        ("postak", "send_approved_emails"),
    ],
    "agent_recovered": [
        ("kontrolor", "log_recovery"),
    ],
    "knowledge_synced": [
        ("archivar", "process_insights"),
    ],
}

# ============================================================
# 7. CIRCUIT BREAKER SETTINGS
# ============================================================

CIRCUIT_BREAKER_THRESHOLD = 3           # Failures before opening circuit
CIRCUIT_BREAKER_RESET_SECONDS = 300     # 5 min cooldown before auto-reset

# ============================================================
# 8. COST TRACKING — Pricing per 1M tokens
# ============================================================

MODEL_PRICING = {
    "claude-opus-4-6": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-3-5-haiku-latest": {"input": 0.0008, "output": 0.004},
    "gpt-5.2": {"input": 0.00175, "output": 0.007},
    "gpt-5-mini": {"input": 0.0004, "output": 0.0016},
    "gpt-5-nano": {"input": 0.00005, "output": 0.0002},
    "ollama/llama3.1:8b": {"input": 0, "output": 0},
}

# Fallback pricing when model not found
MODEL_PRICING_DEFAULT = {"input": 0.003, "output": 0.015}

DAILY_BUDGETS = {
    "free": 0,
    "economy": 3.0,
    "standard": 8.0,
    "premium": 20.0,
}

# ============================================================
# 9. NOTIFICATION SETTINGS
# ============================================================

NOTIFICATION_FOCUS_HOURS = (9, 12)          # Don't interrupt during deep work
NOTIFICATION_MIN_INTERVAL_MINUTES = 15      # Min time between notifications
NOTIFICATION_BATCH_DELAY_SECONDS = 30       # Wait before sending to batch
NOTIFICATION_ESCALATION_THRESHOLD = 3       # P0 alerts bypass all suppression
NOTIFICATION_BATCH_SIZE = 3                 # Send batch after N queued

# ============================================================
# 10. REVIEW PROTOCOL
# ============================================================

REVIEW_MAX_ROUNDS = 3

# ============================================================
# 11. SCORECARD — ADHD gamification settings
# ============================================================

SCORECARD_CHECKS = [
    ("knowledge/USER_DIGEST_AM.md", "Morning briefing generated", 10),
    ("pipedrive/PIPELINE_STATUS.md", "Pipeline reviewed", 15),
    ("pipedrive/STALE_DEALS.md", "Stale deals identified", 10),
    ("pipedrive/DEAL_SCORING.md", "Lead scoring complete", 10),
    ("inbox/INBOX_DIGEST.md", "Inbox triaged", 15),
    ("intel/DAILY-INTEL.md", "Market intel updated", 10),
    ("calendar/TODAY.md", "Daily plan created", 10),
]

SCORECARD_APPROVAL_BONUS_PER_ITEM = 5
SCORECARD_DRAFT_BONUS_PER_ITEM = 10
SCORECARD_TRIGGER_BONUS_PER_ITEM = 3
SCORECARD_TRIGGER_BONUS_CAP = 15
SCORECARD_RECOVERY_BONUS_PER_ITEM = 8
SCORECARD_MILESTONE_NOTIFY_THRESHOLD = 50

SCORECARD_LEVELS = [
    (0, "Sales Padawan", "You're just getting started"),
    (100, "Deal Hunter", "You smell opportunities"),
    (300, "Pipeline Warrior", "CRM is your weapon"),
    (600, "Revenue Ninja", "Silent but effective"),
    (1000, "Sales Samurai", "Honor in every deal"),
    (1500, "Pipeline Jedi", "The force is with you"),
    (2500, "Deal Machine", "Unstoppable momentum"),
    (4000, "Revenue Dragon", "Fear the pipeline"),
    (6000, "Sales Legend", "They write songs about you"),
    (10000, "Pipeline God", "Mere mortals bow"),
]

SCORECARD_ACHIEVEMENTS = {
    "first_50_day": ("First 50-Point Day", "Score 50+ points in a single day"),
    "first_100_day": ("Century Club", "Score 100+ points in a single day"),
    "3_day_streak": ("On Fire", "3-day streak"),
    "5_day_streak": ("Unstoppable", "5-day streak"),
    "7_day_streak": ("Week Warrior", "7-day streak"),
    "14_day_streak": ("Fortnight Force", "14-day streak"),
    "30_day_streak": ("Monthly Monster", "30-day streak"),
    "1000_points": ("Grand", "Reach 1,000 total points"),
    "2500_points": ("Elite", "Reach 2,500 total points"),
    "5000_points": ("Legendary", "Reach 5,000 total points"),
    "10000_points": ("Transcendent", "Reach 10,000 total points"),
    "all_agents_healthy": ("Army Commander", "All 7 agents healthy in one check"),
    "first_recovery": ("Phoenix", "Auto-recover a stale agent"),
    "week_500": ("Weekly Crusher", "500+ points in a single week"),
    "consistent_5": ("Consistency King", "Score 30+ pts for 5 consecutive days"),
}

# ============================================================
# 12. LEARNING SYSTEM — Outcome weights
# ============================================================

OUTCOME_TYPES = {
    "deal_won": {"weight": 10, "agents": ["obchodak", "textar", "postak", "udrzbar"]},
    "deal_lost": {"weight": -3, "agents": ["obchodak", "textar"]},
    "email_replied": {"weight": 5, "agents": ["textar", "postak"]},
    "email_ignored": {"weight": -1, "agents": ["textar"]},
    "meeting_booked": {"weight": 7, "agents": ["postak", "kalendar"]},
    "task_completed_fast": {"weight": 3, "agents": []},
    "task_failed": {"weight": -2, "agents": []},
    "review_passed_first": {"weight": 2, "agents": []},
    "review_needed_revision": {"weight": -1, "agents": []},
    "recovery_success": {"weight": 4, "agents": []},
}

# ============================================================
# 13. DRAFT GENERATOR — SPIN Selling templates
# ============================================================

SPIN_TEMPLATES = {
    "cold_followup": {
        "subject_template": "Zpetna vazba na {org_name}",
        "approach": "situation",
        "tone": "friendly_professional",
        "max_length": 150,
    },
    "warm_reengagement": {
        "subject_template": "Jak to jde s {topic}?",
        "approach": "problem",
        "tone": "helpful",
        "max_length": 120,
    },
    "hot_closing": {
        "subject_template": "{org_name} -- dalsi kroky",
        "approach": "need_payoff",
        "tone": "direct",
        "max_length": 100,
    },
    "demo_followup": {
        "subject_template": "Shrnuti z demo -- {org_name}",
        "approach": "implication",
        "tone": "professional",
        "max_length": 200,
    },
}

SPIN_PROMPTS = {
    "situation": "Ask about their current situation. What tools do they use? How do they measure employee engagement? Be curious, not pushy.",
    "problem": "Gently surface a problem they might have. Employee turnover? Hard to get honest feedback? Missing pulse on team morale?",
    "implication": "Help them see what happens if they don't solve this. What does poor engagement cost? What do they miss without regular feedback?",
    "need_payoff": "Paint the picture of the solution. How would regular pulse surveys help? What would they learn? How fast could they start?",
}

# ============================================================
# 14. OLLAMA — Local model config
# ============================================================

OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_API_URL = "http://localhost:11434"
OLLAMA_GENERATE_URL = f"{OLLAMA_API_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_API_URL}/api/tags"
OLLAMA_DEFAULT_TEMPERATURE = 0.7
OLLAMA_DEFAULT_MAX_TOKENS = 300

# ============================================================
# 15. NIGHTLY TASKS — git sync patterns
# ============================================================

NIGHTLY_GIT_ADD_PATTERNS = [
    "knowledge/",
    "memory/",
    "pipedrive/*.md",
    "reviews/",
    "logs/cost-tracker.json",
    "logs/events.jsonl",
]

# ============================================================
# 16. REQUIRED DIRECTORIES (auto-created on startup)
# ============================================================

REQUIRED_DIRS = [
    LOGS_DIR,
    TRIGGER_OUTBOX,
    TRIGGER_PROCESSED,
    APPROVAL_PENDING,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    APPROVAL_EXPIRED,
    BASE / "inbox",
    BASE / "intel",
    BUS_OUTBOX,
    BUS_INBOX,
    BUS_PROCESSED,
    BUS_DEAD_LETTER,
    BUS_COWORK_STATUS,
    WORKFLOW_DEFS_DIR,
    WORKFLOW_RUNS_DIR,
    WORKFLOW_COMPLETED_DIR,
    REVIEW_IN_PROGRESS_DIR,
    DRAFTS_DIR,
    TASKS_OPEN_DIR,
    TASKS_DONE_DIR,
]


def ensure_dirs():
    """Create all required directories if they don't exist."""
    for d in REQUIRED_DIRS:
        d.mkdir(parents=True, exist_ok=True)


# ============================================================
# 17. MISSION CONTROL — Dashboard agent definitions
# ============================================================

MISSION_CONTROL_AGENTS = {
    "obchodak": {
        "name": "Obchod\u00e1k",
        "role": "Echo Pulse Pipeline",
        "mission": "Fill Josef's calendar with Echo Pulse demos at 50-200 employee companies.",
        "outputs": ["pipedrive/DEAL_SCORING.md", "pipedrive/PIPELINE_STATUS.md", "pipedrive/ENRICHMENT_LOG.md"],
    },
    "hlidac": {
        "name": "Hl\u00edda\u010d",
        "role": "Revenue Accountability",
        "mission": "Drive Josef to close 20+ Echo Pulse deals/month = 258K+ CZK commission.",
        "outputs": ["reviews/daily-scorecard/SCOREBOARD.md"],
    },
    "textar": {
        "name": "Texta\u0159",
        "role": "Echo Pulse Sales Content",
        "mission": "Write emails that get CEOs to book Echo Pulse demos.",
        "outputs": ["drafts/", "templates/sales/"],
    },
    "strateg": {
        "name": "Strat\u00e9g",
        "role": "Prospect Research",
        "mission": "Find companies with 50-200 employees that need engagement surveys NOW.",
        "outputs": ["intel/DAILY-INTEL.md", "intel/COMPETITOR_WATCH.md"],
    },
    "postak": {
        "name": "Po\u0161\u0165\u00e1k",
        "role": "Lead Response",
        "mission": "Never let a warm Echo Pulse lead go cold in the inbox.",
        "outputs": ["inbox/TRIAGE.md", "inbox/FOLLOW_UPS.md"],
    },
    "archivar": {
        "name": "Archiv\u00e1\u0159",
        "role": "Sales Knowledge",
        "mission": "Arm Josef with knowledge that closes Echo Pulse deals.",
        "outputs": ["knowledge/READING_TRACKER.md", "knowledge/AGENT_INSIGHTS.md"],
    },
    "kalendar": {
        "name": "Kalend\u00e1\u0159",
        "role": "Demo Scheduling",
        "mission": "Pack Josef's calendar with Echo Pulse demos, protect calling time.",
        "outputs": ["calendar/TODAY.md", "calendar/TOMORROW_PREP.md"],
    },
    "vyvojar": {
        "name": "V\u00fdvoj\u00e1\u0159",
        "role": "Sales Automation",
        "mission": "Build tools that put more Echo Pulse prospects in front of Josef.",
        "outputs": ["scripts/BUILD_LOG.md"],
    },
    "kontrolor": {
        "name": "Kontrolor",
        "role": "Revenue QA",
        "mission": "Ensure every agent is pulling its weight toward Echo Pulse sales.",
        "outputs": ["reviews/HEALTH_REPORT.md", "reviews/SYSTEM_HEALTH.md"],
    },
}

# ============================================================
# 18. PIPEDRIVE CUSTOM FIELD KEYS
# ============================================================

PD_FIELD_LEAD_SOURCE = "545839ef97506e40a691aa34e0d24a82be08d624"
PD_FIELD_LEAD_TAG = "992635de0ece3a9e8a6a88ea5458a8ac2e14ffc1"
PD_FIELD_FIRST_CALL = "b89c5f67c94d5a3bde2f2b1728646673169a007f"
PD_FIELD_ACCOUNT_STATUS = "3f9bbdc78cf6dd9551ed45112800987a7cb2ea51"
PD_FIELD_USE_CASE = "5d832816b0d2d2a47a1d7b76f4382d3665d03020"
PD_FIELD_PRODUCT = "f4f43d7b1284bc4049adb933c3f79ee2d327f637"
PD_FIELD_ICO = "e8f41ce53b4a2eba1050b385216bb4db7e789fca"
PD_FIELD_MRR = "6c4a9ab5743abd972ed7746fb5d2a0035a543acf"

PD_LEAD_SOURCE_LABELS = {
    89: "Cold",
    88: "Inbound",
    97: "Referral",
    94: "Partner",
    96: "Event",
    98: "Customer",
}
PD_FIRST_CALL_LABELS = {152: "Connected", 153: "Not Connected"}

PD_SALES_STAGES = {
    7: ("Interested/Qualified", 1),
    8: ("Demo Scheduled", 2),
    28: ("Ongoing Discussion", 3),
    9: ("Proposal made", 4),
    10: ("Negotiation", 5),
    12: ("Pilot", 6),
    29: ("Contract Sent", 7),
    11: ("Invoice sent", 8),
}
PD_ONBOARDING_STAGES = {
    16: ("Sales Action Needed", 1),
    15: ("Waiting for Customer", 2),
    17: ("1. Pulse Planned", 3),
    18: ("Probation Period", 4),
    19: ("Customers", 5),
    20: ("Test Only", 6),
    32: ("Not Converted", 7),
}
PD_PARTNERSHIP_STAGES = {22: "Talking", 23: "Serious talks", 24: "Preparations", 25: "Active partnership"}
PD_CHURNED_STAGES = {30: "Churned customers", 31: "Onetime deals"}

# Echo Pulse product ID for scoring boost
PD_ECHO_PULSE_PRODUCT_ID = 107
PD_ENGAGEMENT_USE_CASE_ID = 127

# ============================================================
# 19. SECRETS LOADER
# ============================================================


def load_secrets(path=None):
    """Load secrets from .secrets/ALL_CREDENTIALS.env.

    Returns a dict of KEY=VALUE pairs.
    Skips comments and blank lines.
    Strips 'export ' prefix and surrounding quotes.
    """
    env_path = Path(path) if path else ALL_CREDENTIALS_FILE
    if not env_path.exists():
        return {}

    secrets = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        secrets[key.strip()] = value
    return secrets


def load_pipedrive_env():
    """Load Pipedrive-specific secrets from .secrets/pipedrive.env."""
    return load_secrets(PIPEDRIVE_ENV_FILE)
