// Embedded demo data for Vercel deployment
// This makes the dashboard work without a backend server

export interface Agent {
  id: string
  name: string
  role: string
  status: 'active' | 'idle' | 'watching' | 'sleeping'
  emoji: string
  color: string
  tasksToday: number
  lastActive: string
  skills: string[]
  description: string
  dailyOutput: string
}

export interface TaskItem {
  id: string
  title: string
  agent: string
  status: 'running' | 'pending_approval' | 'queued' | 'done' | 'blocked'
  priority: 'critical' | 'high' | 'medium' | 'low'
  updatedAt: string
  summary: string
}

export interface DealItem {
  id: string
  company: string
  value: number
  stage: string
  health: number
  owner: string
  nextAction: string
  daysInStage: number
}

export interface ActivityEntry {
  id: string
  agent: string
  action: string
  detail: string
  time: string
  type: 'success' | 'info' | 'warning' | 'pending'
}

export const agents: Agent[] = [
  {
    id: 'inboxforge',
    name: 'InboxForge',
    role: 'Email & Blog',
    status: 'active',
    emoji: '✉️',
    color: 'violet',
    tasksToday: 4,
    lastActive: '2 min ago',
    skills: ['Email Drafts', 'Blog Posts', 'Follow-ups', 'Tone Matching'],
    description: 'Writes emails and articles in your voice. Currently drafting 3 follow-ups.',
    dailyOutput: '4 emails drafted, 1 blog outline',
  },
  {
    id: 'dealops',
    name: 'DealOps',
    role: 'Pipeline Ops',
    status: 'active',
    emoji: '🎯',
    color: 'blue',
    tasksToday: 6,
    lastActive: '5 min ago',
    skills: ['Pipeline Review', 'Follow-up Queue', 'Risk Detection', 'SPIN Prep'],
    description: 'Organizing your pipeline. 3 deals need attention today.',
    dailyOutput: '6 follow-ups queued, 2 risk alerts',
  },
  {
    id: 'growthlab',
    name: 'GrowthLab',
    role: 'Intel & Experiments',
    status: 'active',
    emoji: '🔬',
    color: 'emerald',
    tasksToday: 3,
    lastActive: '12 min ago',
    skills: ['YouTube Intel', 'Competitor Watch', 'Web Scraping', 'Experiment Design'],
    description: 'Scanning YouTube for HR tech content. Found 2 competitor moves.',
    dailyOutput: '3 videos analyzed, 1 pricing change detected',
  },
  {
    id: 'timebox',
    name: 'Timebox',
    role: 'Calendar & Planning',
    status: 'idle',
    emoji: '📅',
    color: 'cyan',
    tasksToday: 1,
    lastActive: '1h ago',
    skills: ['Weekly Planning', 'Deep Work Blocks', 'Capacity Alerts', 'Meeting Prep'],
    description: 'Your week is planned. Next refresh: Sunday 8pm.',
    dailyOutput: 'Weekly plan v2 delivered',
  },
  {
    id: 'knowledgekeeper',
    name: 'KnowledgeKeeper',
    role: 'Knowledge Base',
    status: 'active',
    emoji: '📚',
    color: 'amber',
    tasksToday: 2,
    lastActive: '20 min ago',
    skills: ['Book Processing', 'YouTube Transcription', 'Daily Digest', 'Insight Extraction'],
    description: 'Processing "Never Split the Difference". 7 insights extracted so far.',
    dailyOutput: '1 book processed, AM digest sent',
  },
  {
    id: 'reviewer',
    name: 'Reviewer',
    role: 'Quality Gate',
    status: 'watching',
    emoji: '🔍',
    color: 'rose',
    tasksToday: 8,
    lastActive: '8 min ago',
    skills: ['Quality Check', 'Tone Review', 'Risk Assessment', 'Consistency'],
    description: 'Reviewed 8 outputs today. 2 sent back for revision.',
    dailyOutput: '8 reviews, 6 passed, 2 returned',
  },
]

export const tasks: TaskItem[] = [
  {
    id: 'T-001',
    title: 'Follow-up email to Mycroft CEO',
    agent: 'InboxForge',
    status: 'pending_approval',
    priority: 'critical',
    updatedAt: '5 min ago',
    summary: 'CEO is leaving Friday. Re-engagement email with demo link drafted.',
  },
  {
    id: 'T-002',
    title: 'YouTube competitor scan — HR tech',
    agent: 'GrowthLab',
    status: 'running',
    priority: 'high',
    updatedAt: '12 min ago',
    summary: 'Scanning 15 channels. Found Sloneek pricing increase (+20%).',
  },
  {
    id: 'T-003',
    title: 'Process "Never Split the Difference"',
    agent: 'KnowledgeKeeper',
    status: 'running',
    priority: 'medium',
    updatedAt: '20 min ago',
    summary: 'Chapter 5/10 done. 7 insights extracted, 2 sales applications identified.',
  },
  {
    id: 'T-004',
    title: 'Pipeline risk assessment — Q1 deals',
    agent: 'DealOps',
    status: 'done',
    priority: 'high',
    updatedAt: '30 min ago',
    summary: '12 deals reviewed. 3 flagged at-risk, 5 follow-ups queued.',
  },
  {
    id: 'T-005',
    title: 'Blog draft: "Why Engagement Surveys Fail"',
    agent: 'InboxForge',
    status: 'pending_approval',
    priority: 'medium',
    updatedAt: '1h ago',
    summary: '1,200 word draft with CTA. Based on GrowthLab YouTube insights.',
  },
  {
    id: 'T-006',
    title: 'Scrape competitor pricing pages',
    agent: 'GrowthLab',
    status: 'queued',
    priority: 'medium',
    updatedAt: '2h ago',
    summary: 'Weekly check of Sloneek, LutherOne, Teamio, Pinya HR pricing.',
  },
  {
    id: 'T-007',
    title: 'Re-engagement email for DataNest',
    agent: 'InboxForge',
    status: 'queued',
    priority: 'high',
    updatedAt: '45 min ago',
    summary: 'No response in 8 days. Draft creative breakup-style follow-up.',
  },
  {
    id: 'T-008',
    title: 'Weekly plan — March 10-14',
    agent: 'Timebox',
    status: 'done',
    priority: 'medium',
    updatedAt: '3h ago',
    summary: '3 demos, 2 deep work blocks, 1 admin afternoon planned.',
  },
  {
    id: 'T-009',
    title: 'Review InboxForge Mycroft email',
    agent: 'Reviewer',
    status: 'done',
    priority: 'high',
    updatedAt: '10 min ago',
    summary: 'PASS — tone matches, CTA is clear, length appropriate.',
  },
  {
    id: 'T-010',
    title: 'SPIN prep: Innovatrics demo',
    agent: 'DealOps',
    status: 'running',
    priority: 'critical',
    updatedAt: '15 min ago',
    summary: 'Demo tomorrow 10am. Researching their tech stack and pain points.',
  },
]

export const deals: DealItem[] = [
  { id: 'D-001', company: 'Innovatrics', value: 48000, stage: 'Demo', health: 85, owner: 'Josef', nextAction: 'Demo tomorrow 10am', daysInStage: 3 },
  { id: 'D-002', company: 'Mycroft', value: 36000, stage: 'Proposal', health: 45, owner: 'Josef', nextAction: 'CEO follow-up (leaving Friday)', daysInStage: 7 },
  { id: 'D-003', company: 'DataNest', value: 24000, stage: 'Negotiation', health: 30, owner: 'Josef', nextAction: 'Breakup email if no reply by Wed', daysInStage: 12 },
  { id: 'D-004', company: 'Kiwi.com', value: 72000, stage: 'Discovery', health: 70, owner: 'Josef', nextAction: 'Schedule technical deep-dive', daysInStage: 5 },
  { id: 'D-005', company: 'Productboard', value: 60000, stage: 'Proposal', health: 75, owner: 'Josef', nextAction: 'Send revised pricing', daysInStage: 4 },
  { id: 'D-006', company: 'Kentico', value: 42000, stage: 'Demo', health: 90, owner: 'Josef', nextAction: 'Follow-up after demo yesterday', daysInStage: 1 },
  { id: 'D-007', company: 'Socialbakers', value: 55000, stage: 'Closed Won', health: 100, owner: 'Josef', nextAction: 'Onboarding kickoff', daysInStage: 0 },
  { id: 'D-008', company: 'JetBrains', value: 96000, stage: 'Discovery', health: 60, owner: 'Josef', nextAction: 'Intro call with VP People', daysInStage: 8 },
]

export const activity: ActivityEntry[] = [
  { id: 'A-001', agent: 'Reviewer', action: 'Approved', detail: 'Mycroft follow-up email — PASS', time: '10 min ago', type: 'success' },
  { id: 'A-002', agent: 'GrowthLab', action: 'Intel Found', detail: 'Sloneek raised prices 20% — opportunity for us', time: '12 min ago', type: 'warning' },
  { id: 'A-003', agent: 'InboxForge', action: 'Draft Ready', detail: 'Mycroft CEO re-engagement email in approval queue', time: '15 min ago', type: 'pending' },
  { id: 'A-004', agent: 'DealOps', action: 'Risk Alert', detail: 'DataNest — 12 days no response, flagged at-risk', time: '25 min ago', type: 'warning' },
  { id: 'A-005', agent: 'KnowledgeKeeper', action: 'Processing', detail: '"Never Split the Difference" — Chapter 5/10', time: '20 min ago', type: 'info' },
  { id: 'A-006', agent: 'DealOps', action: 'Completed', detail: 'Pipeline review done — 12 deals, 3 at-risk flagged', time: '30 min ago', type: 'success' },
  { id: 'A-007', agent: 'InboxForge', action: 'Draft Ready', detail: 'Blog: "Why Engagement Surveys Fail" — in review', time: '1h ago', type: 'pending' },
  { id: 'A-008', agent: 'Timebox', action: 'Delivered', detail: 'Weekly plan v2 — 3 demos, 2 deep work blocks', time: '3h ago', type: 'success' },
  { id: 'A-009', agent: 'GrowthLab', action: 'Analyzed', detail: '3 YouTube videos transcribed — HR engagement topic', time: '2h ago', type: 'info' },
  { id: 'A-010', agent: 'Reviewer', action: 'Returned', detail: 'DataNest email — needs warmer tone', time: '1h ago', type: 'warning' },
]

export const metrics = {
  activeAgents: 4,
  totalAgents: 6,
  tasksToday: 24,
  tasksCompleted: 16,
  pendingApprovals: 3,
  insightsToday: 7,
  pipelineValue: 433000,
  dealsAtRisk: 2,
  hotDeals: 3,
  emailsDrafted: 4,
  experimentsRunning: 1,
  booksProcessed: 1,
}

export const pipelineStages = [
  { name: 'Discovery', count: 2, value: 168000, color: '#3b82f6' },
  { name: 'Demo', count: 2, value: 90000, color: '#8b5cf6' },
  { name: 'Proposal', count: 2, value: 96000, color: '#f59e0b' },
  { name: 'Negotiation', count: 1, value: 24000, color: '#f97316' },
  { name: 'Closed Won', count: 1, value: 55000, color: '#10b981' },
]

export const weeklyRevenue = [
  { week: 'W1', target: 80000, actual: 0 },
  { week: 'W2', target: 160000, actual: 55000 },
  { week: 'W3', target: 240000, actual: 55000 },
  { week: 'W4', target: 320000, actual: 55000 },
]
