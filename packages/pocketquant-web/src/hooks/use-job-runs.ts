import { useQuery } from '@tanstack/react-query'
import { fetchRuns, type FetchRunsParams } from '../api/system-jobs-api'

export function useJobRuns(jobId: string, params: FetchRunsParams = {}) {
  return useQuery({
    queryKey: ['job-runs', jobId, params],
    queryFn: () => fetchRuns(jobId, params),
    refetchInterval: 15_000,
  })
}
