import type { RunReport } from '../../shared/types'

export class ReportStore {
  private reports: RunReport[] = []

  list() {
    return [...this.reports]
  }

  latest() {
    return this.reports[0] ?? null
  }

  add(report: RunReport) {
    this.reports = [report, ...this.reports].slice(0, 10)
  }

  replace(report: RunReport) {
    this.reports = this.reports.map((current) => (current.id === report.id ? report : current))
    if (!this.reports.find((current) => current.id === report.id)) {
      this.add(report)
    }
  }
}
