# HEARTBEAT.md — CopyAgent

## Active Cron Tasks
1. **Morning content production** (09:00 M-F) → drafts/*.md, brief status updates
2. **Slack intel extraction** (10:00, 14:00, 18:00 M-F) → SLACK_INSIGHTS.md, OBJECTION_LIBRARY.md
3. **Template polish** (Wed 10:00) → templates/sales/*.md + Pipedrive upload
4. **Content calendar** (Mon 09:30) → briefs/auto-generated/*.md
5. **Weekly blog article** (Tue 09:00) → Write + publish 1 quality blog post to behavera.com/admin
6. **Blog improvement** (Thu 10:00) → Review + improve existing blog articles on behavera.com
7. **Daily book excerpt email** (07:30 M-F) → Send Josef a curated excerpt from today's book study

## Behavera Admin Access
- URL: www.behavera.com/admin
- Login: josef.hofman@behavera.com
- Password: Admin1234
- Tasks: Add new blog articles, improve existing content, fix visual issues

## Blog Writing Standards
- Czech language, SEO-optimized
- 1200-2000 words
- Include Gallup/research stats
- FAQ section (3-5 questions)
- CTAs to Echo Pulse
- Use knowledge/CONTENT_SALES_BRIDGE.md for topic-to-funnel mapping
- Review with playbooks/COPYWRITER_PIPELINE.md scoring (must hit 80+)

## Daily Book Excerpt Email
Every morning at 07:30, KnowledgeKeeper studies a book. CopyAgent:
1. Reads the latest book insight from knowledge/book-insights/
2. Picks the most powerful excerpt or framework
3. Writes a short, punchy email (5-8 sentences) with the key insight
4. Sends via Gmail MCP to josef.hofman@behavera.com
5. Subject: "📚 Denní úryvek: [Book Title] — [Key Insight]"
6. Must be practical — not just "interesting" but "here's how to use this today"

## Knowledge Sources
- Product: knowledge/COPYWRITER_KNOWLEDGE_BASE.md
- Voice: knowledge/JOSEF_TONE_OF_VOICE.md
- Phrases: knowledge/CZECH_PHRASE_LIBRARY.md
- Objections: knowledge/OBJECTION_LIBRARY.md
- Slack: knowledge/SLACK_INSIGHTS.md
- Book insights: knowledge/book-insights/*.md (from KnowledgeKeeper)
- Pipeline: pipedrive/PIPELINE_STATUS.md (for COPY_NEEDED flags)

## Rules
- All output in Czech unless specifically requested in English
- Use Josef's real tone — no corporate, no buzzwords
- Every template max 1 showcase link (keep powder dry)
- No signature in email templates
- Blog articles: publish via behavera.com/admin, quality over quantity
- Book excerpt emails: genuinely useful, not fluff

## Dependencies
- Reads: knowledge/*.md, pipedrive/PIPELINE_STATUS.md, briefs/QUEUE.md, intel/DAILY-INTEL.md
- Writes: drafts/*.md, delivery-queue/*.md, templates/sales/*.md, knowledge/SLACK_INSIGHTS.md
- Gmail MCP: daily book excerpt to josef.hofman@behavera.com
- Behavera admin: blog posts, content improvements
