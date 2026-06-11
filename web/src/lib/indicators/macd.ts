import { ema } from './moving-average'

export function macd(
  data: number[],
  fast = 12,
  slow = 26,
  signal = 9,
): { macdLine: (number | null)[]; signalLine: (number | null)[]; histogram: (number | null)[] } {
  const emaFast = ema(data, fast)
  const emaSlow = ema(data, slow)

  const macdLine: (number | null)[] = data.map((_, i) =>
    emaFast[i] !== null && emaSlow[i] !== null
      ? (emaFast[i] as number) - (emaSlow[i] as number)
      : null,
  )

  const macdValues = macdLine.filter((v): v is number => v !== null)
  const signalRaw = ema(macdValues, signal)

  const signalLine: (number | null)[] = []
  let si = 0
  for (let i = 0; i < macdLine.length; i++) {
    if (macdLine[i] === null) {
      signalLine.push(null)
    } else {
      signalLine.push(signalRaw[si] ?? null)
      si++
    }
  }

  const histogram: (number | null)[] = data.map((_, i) =>
    macdLine[i] !== null && signalLine[i] !== null
      ? (macdLine[i] as number) - (signalLine[i] as number)
      : null,
  )

  return { macdLine, signalLine, histogram }
}
