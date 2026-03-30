import { useQuery, useMutation } from '@tanstack/react-query'
import { fetchStrategies, runBacktest, type BacktestResponse } from '../api/backtest-api'
import type { Interval } from '../types/market-data'

export function useStrategies() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    staleTime: 60_000,
  })
}

export function useBacktest(exchange: string, symbol: string, interval: Interval) {
  const mutation = useMutation({ mutationFn: runBacktest })

  const run = (strategyId: string) => {
    const now = new Date()
    const end = now.toISOString().slice(0, 10)
    const start = new Date(now.getTime() - 30 * 86_400_000).toISOString().slice(0, 10)
    mutation.mutate({
      strategy_id: strategyId,
      symbol,
      exchange,
      interval,
      start_date: start,
      end_date: end,
    })
  }

  return {
    data: mutation.data as BacktestResponse | undefined,
    isLoading: mutation.isPending,
    run,
    reset: mutation.reset,
  }
}
