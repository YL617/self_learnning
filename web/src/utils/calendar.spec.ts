import { describe, expect, it } from 'vitest'

import {
  addDays,
  addMonths,
  dateKey,
  daysInMonth,
  firstOffset,
  isToday,
  monthKey,
} from './calendar'

describe('calendar helpers', () => {
  it('returns correct days in month', () => {
    expect(daysInMonth(2026, 2)).toBe(28)
    expect(daysInMonth(2028, 2)).toBe(29)
    expect(daysInMonth(2026, 4)).toBe(30)
    expect(daysInMonth(2026, 1)).toBe(31)
  })

  it('returns monday-first offset', () => {
    expect(firstOffset(2026, 8)).toBe(5)
    expect(firstOffset(2026, 2)).toBe(6)
  })

  it('builds month and date keys', () => {
    expect(monthKey(2026, 8)).toBe('2026-08')
    expect(dateKey(2026, 8, 9)).toBe('2026-08-09')
  })

  it('navigates months and days', () => {
    expect(addMonths(2026, 12, 1)).toEqual([2027, 1])
    expect(addMonths(2026, 1, -1)).toEqual([2025, 12])
    expect(addDays(2026, 3, 1, -1)).toEqual([2026, 2, 28])
    expect(addDays(2026, 12, 31, 1)).toEqual([2027, 1, 1])
  })

  it('detects today key', () => {
    const now = new Date()
    const key = dateKey(now.getFullYear(), now.getMonth() + 1, now.getDate())
    expect(isToday(key)).toBe(true)
    expect(isToday('1999-01-01')).toBe(false)
  })
})
