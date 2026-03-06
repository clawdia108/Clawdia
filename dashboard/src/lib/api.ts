import { agents, tasks, deals, activity, metrics, pipelineStages, weeklyRevenue } from './demo-data'
import type { Agent, TaskItem, DealItem, ActivityEntry } from './demo-data'

export type { Agent, TaskItem, DealItem, ActivityEntry }

export const api = {
  getAgents: () => Promise.resolve(agents),
  getTasks: () => Promise.resolve(tasks),
  getDeals: () => Promise.resolve(deals),
  getActivity: () => Promise.resolve(activity),
  getMetrics: () => Promise.resolve(metrics),
  getPipelineStages: () => Promise.resolve(pipelineStages),
  getWeeklyRevenue: () => Promise.resolve(weeklyRevenue),
}
