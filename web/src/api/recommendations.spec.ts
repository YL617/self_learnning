import { describe, expect, it, vi } from 'vitest'

import { actionTone, recommendationsApi } from '@/api/recommendations'
import { http } from '@/api/http'

describe('recommendations api', () => {
  it('today() 调用 /recommendations/today 并透传 limit', async () => {
    const spy = vi.spyOn(http, 'get').mockResolvedValue({ data: { items: [] } } as any)
    await recommendationsApi.today({ limit: 3 })
    expect(spy).toHaveBeenCalledWith('/recommendations/today', { params: { limit: 3 } })
    spy.mockRestore()
  })

  it('actionTone 覆盖四种动作类型', () => {
    expect(actionTone('review_wrong').tone).toBe('danger')
    expect(actionTone('review_weak').tone).toBe('amber')
    expect(actionTone('learn_new').tone).toBe('teal')
    expect(actionTone('practice').tone).toBe('neutral')
  })

  it('actionTone 对未知动作回退到中性样式', () => {
    const tone = actionTone('unknown_action')
    expect(tone.tone).toBe('neutral')
    expect(tone.icon).toBe('建议')
  })
})
