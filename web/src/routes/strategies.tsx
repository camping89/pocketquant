/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { createFileRoute } from '@tanstack/react-router'
import { StrategiesPageLayout } from '../components/strategies/strategies-page-layout'

export const Route = createFileRoute('/strategies')({
  component: StrategiesPage,
})

function StrategiesPage() {
  return <StrategiesPageLayout />
}
