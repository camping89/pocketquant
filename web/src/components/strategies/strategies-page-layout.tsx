import { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExnessStrip } from './exness-strip'
import { StrategyListSidebar } from './strategy-list-sidebar'
import { SubscriptionDrawer } from './subscription-drawer'
import { listSubscriptions, type Subscription } from '../../api/strategy-api'

export function StrategiesPageLayout() {
  // Keep only the id: the selected row is read from the polled list on every
  // render, so the drawer follows Start/Stop without re-selecting.
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: subs = [], isLoading: subsLoading, error } = useQuery({
    queryKey: ['subscriptions'],
    queryFn: () => listSubscriptions(),
    staleTime: 10_000,
    refetchInterval: 5_000,
  })
  const selectedSub = subs.find((s) => s.id === selectedId) ?? null
  const closeDrawer = useCallback(() => setSelectedId(null), [])

  function handleSelectSub(sub: Subscription) {
    setSelectedId((prev) => (prev === sub.id ? null : sub.id))
  }

  return (
    <div className="strategies-page">
      <ExnessStrip />

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <StrategyListSidebar
          subs={subs}
          isLoading={subsLoading}
          error={error}
          selectedSubId={selectedId}
          onSelect={handleSelectSub}
        />
      </div>

      {selectedSub && <SubscriptionDrawer key={selectedSub.id} sub={selectedSub} onClose={closeDrawer} />}
    </div>
  )
}
