import { useQuery } from '@tanstack/react-query'
import { fetchStrategies } from '../api/backtest-api'
import { fetchStrategyDefaults } from '../api/strategy-api'

export function useStrategiesList() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    staleTime: 30_000,
  })
}

export function useStrategyDefaults(code: string) {
  return useQuery({
    queryKey: ['strategy-defaults', code],
    queryFn: () => fetchStrategyDefaults(code),
    enabled: !!code,
    staleTime: 5 * 60 * 1000,
  })
}
