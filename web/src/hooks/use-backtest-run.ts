import { useQuery, useMutation } from '@tanstack/react-query'
import {
  fetchStrategies,
  fetchBacktestRun,
  runBacktest,
  type RunBacktestBody,
} from '../api/backtest-api'

export function useStrategyList() {
  return useQuery({
    queryKey: ['backtest-strategies'],
    queryFn: fetchStrategies,
    staleTime: 5 * 60 * 1000,
  })
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: (body: RunBacktestBody) => runBacktest(body),
  })
}

/** Poll a run until it reaches a terminal status; stop polling once terminal. */
export function useBacktestRun(runId: string | null) {
  return useQuery({
    queryKey: ['backtest-run', runId],
    queryFn: () => fetchBacktestRun(runId!),
    enabled: !!runId,
    refetchInterval: (q) => (q.state.data?.status === 'started' ? 1500 : false),
  })
}
