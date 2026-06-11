import { useQuery } from '@tanstack/react-query'
import { fetchStats } from '../api/system-jobs-api'

export function useJobStats(jobId: string, window: '24h' | '7d' | '30d' = '24h') {
  return useQuery({
    queryKey: ['job-stats', jobId, window],
    queryFn: () => fetchStats(jobId, window),
    refetchInterval: 30_000,
  })
}
