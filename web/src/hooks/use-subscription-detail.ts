import { useQuery } from '@tanstack/react-query'
import { fetchOrders, fetchSnapshot } from '../api/strategy-api'

export function useSubscriptionSnapshot(subId: string) {
  return useQuery({
    queryKey: ['subscription-snapshot', subId],
    queryFn: () => fetchSnapshot(subId),
    refetchInterval: 5_000,
  })
}

export function useSubscriptionOrders(subId: string) {
  return useQuery({
    queryKey: ['subscription-orders', subId],
    queryFn: () => fetchOrders(subId),
    refetchInterval: 5_000,
  })
}
