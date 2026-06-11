import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { JobRun } from '../../types/job-history'
import { useFmt } from '../../lib/use-timezone'
import { statusColor, statusLabel } from './job-status-palette'

interface JobTimelineChartProps {
  runs: JobRun[]
  onRunClick?: (runId: string) => void
}

export function JobTimelineChart({ runs, onRunClick }: JobTimelineChartProps) {
  const ref = useRef<HTMLDivElement>(null)
  const fmt = useFmt()

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    const data = runs.map((r) => ({
      value: [r.started_at ?? r.scheduled_run_time, r.duration_ms ?? 0],
      itemStyle: { color: statusColor(r.status) },
      runId: r._id,
      status: r.status,
      total_inserted: r.total_inserted,
    }))
    chart.setOption({
      grid: { left: 56, right: 16, top: 16, bottom: 32 },
      // useUTC controls how echarts formats axis ticks for `type: 'time'`.
      // True = UTC; false = browser-local. Matches selected tz mode.
      useUTC: fmt.mode === 'utc',
      xAxis: { type: 'time' },
      yAxis: { type: 'value', name: 'duration (ms)' },
      tooltip: {
        trigger: 'item',
        formatter: (p: { value: [string, number]; data: { runId: string; status: string; total_inserted: number | null } }) =>
          `<b>${fmt.fullDateTime(p.value[0])}</b><br/>` +
          `${statusLabel(p.data.status)} · ${p.value[1]}ms<br/>` +
          `inserted: ${p.data.total_inserted ?? '—'}<br/>` +
          `<small>${p.data.runId}</small>`,
      },
      series: [
        {
          type: 'scatter',
          symbolSize: 9,
          data,
        },
      ],
    })

    chart.on('click', (params) => {
      const d = (params as { data?: { runId?: string } }).data
      if (onRunClick && d?.runId) onRunClick(d.runId)
    })

    function onResize() {
      chart.resize()
    }
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [runs, onRunClick, fmt])

  return <div ref={ref} className="job-timeline-chart" style={{ width: '100%', height: 280 }} />
}
