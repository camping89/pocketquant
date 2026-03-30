import { useQuery } from '@tanstack/react-query'
import { fetchSymbols } from '../api/market-data-api'

export function useSymbols(exchange?: string) {
  return useQuery({
    queryKey: ['symbols', exchange],
    queryFn: () => fetchSymbols(exchange),
    staleTime: 30 * 60 * 1000,
  })
}
