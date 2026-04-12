import { useMutation } from '@tanstack/react-query'
import { checkIntegrity, repairIntegrity } from '../api/monitor-api'

interface IntegrityParams {
  symbol: string
  exchange: string
  interval: string
  daysBack?: number
}

export function useIntegrityCheck() {
  return useMutation({
    mutationFn: (params: IntegrityParams) =>
      checkIntegrity(params.symbol, params.exchange, params.interval, params.daysBack),
  })
}

export function useIntegrityRepair() {
  return useMutation({
    mutationFn: (params: IntegrityParams) =>
      repairIntegrity(params.symbol, params.exchange, params.interval, params.daysBack),
  })
}
