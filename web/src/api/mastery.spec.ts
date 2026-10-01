import { describe, expect, it, vi } from 'vitest'

import { masteryApi, masteryLevel } from './mastery'
import { http } from './http'

vi.mock('./http', () => ({
  http: { get: vi.fn() },
}))

describe('masteryApi 契约', () => {
  it('list 调用 /mastery 并透传 limit', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: [] } as any)
    await masteryApi.list({ limit: 20 })
    expect(http.get).toHaveBeenCalledWith('/mastery', { params: { limit: 20 } })
  })

  it('summary 调用 /mastery/summary', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: {} } as any)
    await masteryApi.summary()
    expect(http.get).toHaveBeenCalledWith('/mastery/summary')
  })

  it('weak 调用 /mastery/weak 并透传染色阈值', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: [] } as any)
    await masteryApi.weak({ threshold: 70, limit: 3 })
    expect(http.get).toHaveBeenCalledWith('/mastery/weak', {
      params: { threshold: 70, limit: 3 },
    })
  })

  it('get 调用 /mastery/{id}', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: {} } as any)
    await masteryApi.get(7)
    expect(http.get).toHaveBeenCalledWith('/mastery/7')
  })
})

describe('masteryLevel', () => {
  it('按分数划分等级', () => {
    expect(masteryLevel(0).tone).toBe('weak')
    expect(masteryLevel(59).tone).toBe('weak')
    expect(masteryLevel(60).tone).toBe('steady')
    expect(masteryLevel(84).tone).toBe('steady')
    expect(masteryLevel(85).tone).toBe('strong')
    expect(masteryLevel(100).tone).toBe('strong')
  })

  it('越界与小数会被夹取后再判定', () => {
    expect(masteryLevel(-20).tone).toBe('weak')
    expect(masteryLevel(999).tone).toBe('strong')
    expect(masteryLevel(84.6).tone).toBe('strong')
  })
})
