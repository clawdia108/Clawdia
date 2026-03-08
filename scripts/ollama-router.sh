#!/bin/bash
# Ollama Local Router — zero-cost classification, triaging, and quick tasks
# Uses llama3.1:8b running locally for instant, free processing

set -e
cd /Users/josefhofman/Clawdia

ollama_query() {
    local prompt="$1"
    local max_tokens="${2:-512}"

    python3 -c "
import json, urllib.request, sys

data = json.dumps({
    'model': 'llama3.1:8b',
    'prompt': sys.argv[1],
    'stream': False,
    'options': {'num_predict': int(sys.argv[2]), 'temperature': 0.1}
}).encode()

req = urllib.request.Request('http://localhost:11434/api/generate', data=data, headers={'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req, timeout=60)
    result = json.loads(resp.read())
    print(result.get('response', 'ERROR: no response'))
except Exception as e:
    print(f'ERROR: {e}')
" "$prompt" "$max_tokens"
}

case "$1" in
    classify)
        shift
        ollama_query "Classify this text into exactly ONE category: sales_lead, follow_up, meeting_prep, content_idea, bug_report, feature_request, internal_ops, urgent_action. Reply with ONLY the category name, nothing else.

Text: $*"
        ;;

    triage)
        shift
        ollama_query "You are a sales operations triage system. Analyze this text and respond in EXACTLY this JSON format (no markdown, no explanation):
{\"priority\": \"P0 or P1 or P2\", \"agent\": \"agent_name\", \"action\": \"one-line description\"}

Available agents: obchodak, textar, postak, strateg, kalendar, hlidac

Rules:
- P0: Revenue at risk, client waiting, deadline today
- P1: Important but can wait 24h
- P2: Nice to have, no urgency

Text: $*" 256
        ;;

    summarize)
        FILE="$2"
        if [ ! -f "$FILE" ]; then echo "File not found: $FILE"; exit 1; fi
        CONTENT=$(head -100 "$FILE")
        ollama_query "Summarize this in 3 bullet points, max 15 words each. Be direct, no fluff.

$CONTENT" 256
        ;;

    extract)
        FILE="$2"
        if [ ! -f "$FILE" ]; then echo "File not found: $FILE"; exit 1; fi
        CONTENT=$(head -200 "$FILE")
        ollama_query "Extract all action items from this text. Return as a numbered list. Only include concrete actions, not observations.

$CONTENT" 512
        ;;

    sentiment)
        shift
        ollama_query "Analyze the sentiment of this email/message. Reply in JSON format only:
{\"sentiment\": \"positive or neutral or negative or urgent\", \"buying_signal\": true or false, \"needs_response\": true or false, \"key_emotion\": \"one word\"}

Text: $*" 128
        ;;

    route)
        shift
        ollama_query "Given this task, which agent should handle it? Available agents:
- obchodak: CRM, deals, pipeline hygiene
- textar: emails, blog posts, content writing
- postak: email triage, sending, follow-ups
- strateg: market research, competitor analysis
- archivar: knowledge synthesis, book processing
- kalendar: calendar, meeting prep, time blocking
- vyvojar: system building, coding, automation
- spojka: coordination, delegation, user-facing
- kontrolor: quality checks, system health
- hlidac: performance tracking, gamification

Reply with ONLY the agent name.

Task: $*" 64
        ;;

    adhd-focus)
        shift
        ollama_query "You help a person with ADHD stay focused. Given this context, tell them the ONE most important thing to do RIGHT NOW. Be extremely specific and actionable. Max 2 sentences. No options, no lists, just the one thing.

Context: $*" 128
        ;;

    batch-triage)
        # Read lines from stdin, triage each one
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            echo "---"
            echo "Input: $line"
            echo -n "Result: "
            ollama_query "Classify priority (P0/P1/P2) and assign agent. Reply: PRIORITY|AGENT|ACTION

Agents: obchodak, textar, postak, strateg, kalendar, hlidac

Text: $line" 64
        done
        ;;

    *)
        echo "Usage: $0 {classify|triage|summarize|extract|sentiment|route|adhd-focus|batch-triage} [args]"
        exit 1
        ;;
esac
