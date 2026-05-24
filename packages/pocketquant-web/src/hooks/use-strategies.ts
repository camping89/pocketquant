/**
 * List query for all loaded strategy IDs.
 * Returns string[] from /api/v1/backtest/strategies.
 */
import { useQuery } from '@tanstack/react-query'
import { fetchStrategies } from '../api/backtest-api'

export function useStrategiesList() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: fetchStrategies,
    staleTime: 30_000,
  })
}
