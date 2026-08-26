export function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

export function firstOffset(year: number, month: number): number {
  const weekday = new Date(year, month - 1, 1).getDay()
  return (weekday + 6) % 7
}

export function monthKey(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

export function dateKey(year: number, month: number, day: number): string {
  return `${monthKey(year, month)}-${String(day).padStart(2, '0')}`
}

export function isToday(key: string): boolean {
  const now = new Date()
  return dateKey(now.getFullYear(), now.getMonth() + 1, now.getDate()) === key
}

export function addMonths(year: number, month: number, delta: number): [number, number] {
  const total = year * 12 + (month - 1) + delta
  const nextYear = Math.floor(total / 12)
  const nextMonth = (total % 12) + 1
  return [nextYear, nextMonth]
}

export function addDays(year: number, month: number, day: number, delta: number): [number, number, number] {
  const date = new Date(year, month - 1, day + delta)
  return [date.getFullYear(), date.getMonth() + 1, date.getDate()]
}
