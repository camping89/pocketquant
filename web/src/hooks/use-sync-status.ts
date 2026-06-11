import { useQuery } from '@tanstack/react-query'
import { fetchSyncStatus } from '../api/market-data-api'

export function useSyncStatus() {
  return useQuery({
    queryKey: ['sync-status'],
    queryFn: fetchSyncStatus,
    refetchInterval: 30_000,
  })
}
