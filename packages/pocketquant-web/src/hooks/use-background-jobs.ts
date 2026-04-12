import { useQuery } from '@tanstack/react-query'
import { fetchJobs } from '../api/monitor-api'

export function useBackgroundJobs() {
  return useQuery({
    queryKey: ['background-jobs'],
    queryFn: fetchJobs,
    refetchInterval: 30_000,
  })
}
