import { useMutation } from '@tanstack/react-query'
import { repairIntegrity } from '../api/monitor-api'

interface RepairParams {
  symbol: string
  interval: string
  daysBack?: number
}

export function useIntegrityRepair() {
  return useMutation({
    mutationFn: (params: RepairParams) =>
      repairIntegrity(params.symbol, params.interval, params.daysBack),
  })
}
