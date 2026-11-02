import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../api/api-client'

// Mirrors GET /admin/safeguards: the env caps plus the trader's stored live flag and
// the entry pause.
export interface Safeguards {
  live_trading: boolean
  daily_loss_cap: number | null
  max_lots: number | null
  leverage: number
  risk_per_trade: number
  entries_paused: boolean
}

export const SAFEGUARDS_KEY = ['safeguards']

export function useSafeguards() {
  return useQuery({
    queryKey: SAFEGUARDS_KEY,
    queryFn: () => apiFetch<Safeguards>('/api/v1/admin/safeguards'),
    refetchInterval: 5_000,
  })
}
