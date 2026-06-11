import { sma } from './moving-average'

export function bollingerBands(
  data: number[],
  period = 20,
  stdDev = 2,
): { upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[] } {
  const middle = sma(data, period)

  const upper: (number | null)[] = []
  const lower: (number | null)[] = []

  for (let i = 0; i < data.length; i++) {
    if (middle[i] === null) {
      upper.push(null)
      lower.push(null)
    } else {
      let variance = 0
      for (let j = i - period + 1; j <= i; j++) {
        variance += (data[j] - (middle[i] as number)) ** 2
      }
      const sd = Math.sqrt(variance / period)
      upper.push((middle[i] as number) + stdDev * sd)
      lower.push((middle[i] as number) - stdDev * sd)
    }
  }

  return { upper, middle, lower }
}
