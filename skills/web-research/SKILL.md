---
name: web-research
description: Perform structured web research on topics. Use when any agent needs to find current information online for their domain.
tools: Bash
---

# Web Research Skill

## When to use
- GrowthLab: daily research sweeps
- Any agent: filling knowledge gaps during self-improvement

## Method

### Quick research (use first)
```bash
# HN front page
curl -s "https://news.ycombinator.com/front" | head -200
# GitHub trending
curl -s "https://api.github.com/search/repositories?q=agent+framework&sort=stars&order=desc&per_page=5" | jq '.items[] | {name, stars: .stargazers_count, description, url: .html_url}'
```

### Deep research (if quick isn't enough)
Use browser automation to read full articles and extract key information.

## Output format
Always structure research output as:
```
## Finding: [Title]
- **Source:** [URL]
- **Date:** [YYYY-MM-DD]
- **Relevance:** [HIGH/MED/LOW]
- **Summary:** [2-3 sentences]
- **Action items:** [if any]
```

## Rules
- ALWAYS cite sources
- NEVER fabricate information
- Mark uncertain info as [UNVERIFIED]
- Prefer primary sources over aggregators
