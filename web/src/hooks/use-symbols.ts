import { useQuery } from '@tanstack/react-query'
import { fetchSymbols } from '../api/market-data-api'

export function useSymbols() {
  return useQuery({
    queryKey: ['symbols'],
    queryFn: () => fetchSymbols(),
    staleTime: 30 * 60 * 1000,
  })
}
