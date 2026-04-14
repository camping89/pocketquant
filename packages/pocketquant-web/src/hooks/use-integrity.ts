import { useMutation } from '@tanstack/react-query'
import { repairIntegrity } from '../api/monitor-api'

interface RepairParams {
  symbol: string
  exchange: string
  interval: string
  daysBack?: number
}

export function useIntegrityRepair() {
  return useMutation({
    mutationFn: (params: RepairParams) =>
      repairIntegrity(params.symbol, params.exchange, params.interval, params.daysBack),
  })
}
