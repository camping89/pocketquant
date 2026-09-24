import { useQuery } from '@tanstack/react-query'
import { fetchDataLag } from '../api/market-data-api'

// The server re-measures once a minute; polling at half that keeps the badge
// at most ~90s behind a change without hammering the API.
export function useDataLag(symbol: string) {
  return useQuery({
    queryKey: ['data-lag', symbol],
    queryFn: () => fetchDataLag(symbol),
    refetchInterval: 30_000,
  })
}
