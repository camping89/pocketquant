import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  fetchStrategies,
  fetchBacktestRun,
  runBacktest,
  listBacktestRuns,
  fetchBacktestOrders,
  setVerdict,
  type RunBacktestBody,
  type BacktestRunScope,
  type BacktestRunResult,
} from '../api/backtest-api'

export function useStrategyList() {
  return useQuery({
    queryKey: ['backtest-strategies'],
    queryFn: fetchStrategies,
    staleTime: 5 * 60 * 1000,
  })
}

/** Start a run, then deep-link to its detail route so reload/back/forward work. */
export function useRunBacktest() {
  const navigate = useNavigate()
  return useMutation({
    mutationFn: (body: RunBacktestBody) => runBacktest(body),
    onSuccess: ({ request_id }) =>
      void navigate({ to: '/backtest/$runId', params: { runId: request_id } }),
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

/** History runs for a scope. Disabled until a strategy is chosen (validation Q5:
 *  the rail is empty until then). */
export function useBacktestRuns(scope: BacktestRunScope | null) {
  return useQuery({
    queryKey: ['backtest-runs', scope],
    queryFn: () => listBacktestRuns(scope!),
    enabled: !!scope?.strategy,
  })
}

/** Orders for a run — lazy: only fetched once ``enabled`` (the Orders tab opens). */
export function useBacktestOrders(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['backtest-orders', runId],
    queryFn: () => fetchBacktestOrders(runId),
    enabled: enabled && !!runId,
  })
}

/** Set/clear a run's verdict with an optimistic cache update; revert the cached
 *  run on failure (the caller keeps the textarea text + surfaces the error). */
export function useSetVerdict(runId: string) {
  const qc = useQueryClient()
  const key = ['backtest-run', runId]
  return useMutation({
    mutationFn: (verdict: string | null) => setVerdict(runId, verdict),
    onMutate: async (verdict) => {
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<BacktestRunResult>(key)
      if (previous) qc.setQueryData<BacktestRunResult>(key, { ...previous, verdict })
      return { previous }
    },
    onError: (_err, _verdict, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous)
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: key }),
  })
}
