import {
  useQuery,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  fetchStrategies,
  fetchBacktestRun,
  runBacktest,
  listBacktestRuns,
  listAllBacktestRuns,
  fetchBacktestOrders,
  fetchBacktestTradesPage,
  fetchBacktestMarkers,
  fetchBacktestStats,
  setVerdict,
  setBacktestName,
  type RunBacktestBody,
  type BacktestRunScope,
  type BacktestRunResult,
  type TradeSortKey,
  type TradeSortDir,
  type TradeFilterKey,
} from '../api/backtest-api'

export function useStrategyList() {
  return useQuery({
    queryKey: ['backtest-strategies'],
    queryFn: fetchStrategies,
    staleTime: 5 * 60 * 1000,
  })
}

// Deep-link via the run path segment so the workbench selects it and reload/back/forward work.
export function useRunBacktest() {
  const navigate = useNavigate()
  return useMutation({
    mutationFn: (body: RunBacktestBody) => runBacktest(body),
    onSuccess: ({ request_id }) =>
      void navigate({ to: '/backtest/{-$runId}/{-$tab}', params: { runId: request_id, tab: undefined } }),
  })
}

export function useBacktestRun(runId: string | null) {
  return useQuery({
    queryKey: ['backtest-run', runId],
    queryFn: () => fetchBacktestRun(runId!),
    enabled: !!runId,
    refetchInterval: (q) => (q.state.data?.status === 'started' ? 1500 : false),
  })
}

export function useBacktestRuns(scope: BacktestRunScope | null) {
  return useQuery({
    queryKey: ['backtest-runs', scope],
    queryFn: () => listBacktestRuns(scope!),
    enabled: !!scope?.strategy,
  })
}

export function useAllBacktestRuns(scope: Omit<BacktestRunScope, 'strategy'>, enabled = true) {
  return useQuery({
    queryKey: ['backtest-runs', 'all', scope],
    queryFn: () => listAllBacktestRuns(scope),
    enabled,
  })
}

export interface TradesQueryOpts {
  sortKey: TradeSortKey
  sortDir: TradeSortDir
  filter: TradeFilterKey
}

// Keyed by sort/filter so changing either starts a fresh keyset walk.
export function useBacktestTrades(
  runId: string,
  { sortKey, sortDir, filter }: TradesQueryOpts,
  enabled: boolean,
) {
  return useInfiniteQuery({
    queryKey: ['backtest-trades', runId, sortKey, sortDir, filter],
    queryFn: ({ pageParam }) =>
      fetchBacktestTradesPage(runId, { cursor: pageParam, sortKey, sortDir, filter }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.has_more ? last.next_cursor : undefined),
    enabled: enabled && !!runId,
  })
}

export function useBacktestMarkers(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['backtest-markers', runId],
    queryFn: () => fetchBacktestMarkers(runId),
    enabled: enabled && !!runId,
  })
}

export function useBacktestStats(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['backtest-stats', runId],
    queryFn: () => fetchBacktestStats(runId),
    enabled: enabled && !!runId,
  })
}

export function useBacktestOrders(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['backtest-orders', runId],
    queryFn: () => fetchBacktestOrders(runId),
    enabled: enabled && !!runId,
  })
}

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

// Also invalidates the history-list queries: list rows come from a separate query key,
// and the renamed run must show in the rail.
export function useSetBacktestName(runId: string) {
  const qc = useQueryClient()
  const key = ['backtest-run', runId]
  return useMutation({
    mutationFn: (name: string | null) => setBacktestName(runId, name),
    onMutate: async (name) => {
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<BacktestRunResult>(key)
      if (previous) qc.setQueryData<BacktestRunResult>(key, { ...previous, name })
      return { previous }
    },
    onError: (_err, _name, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous)
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: key })
      void qc.invalidateQueries({ queryKey: ['backtest-runs'] })
    },
  })
}
