import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { focusApi } from '@/api/focus'
import type { Pet, PetPlaySession } from '@/types'
import { usePetStore } from './pet'

vi.mock('@/api/focus', () => ({
  focusApi: {
    pet: vi.fn(),
    petPlayState: vi.fn(),
    startPetPlay: vi.fn(),
    endPetPlay: vi.fn(),
  },
}))

const pet: Pet = {
  id: 1,
  name: '小智',
  level: 1,
  exp: 0,
  mood: 100,
  hunger: 100,
  evolution_stage: 1,
  runaway: false,
  play_count_today: 0,
}

describe('pet store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('computes play state from session and playing_until as UTC', () => {
    const store = usePetStore()
    store.pet = {
      ...pet,
      playing_until: new Date(Date.now() + 120000).toISOString(),
    }
    store.session = { status: 'active' } as PetPlaySession

    expect(store.isPlaying).toBe(true)
    expect(store.remainingSeconds).toBeGreaterThan(100)
    expect(store.remainingSeconds).toBeLessThanOrEqual(120)
  })

  it('syncs play state from api', async () => {
    const store = usePetStore()
    store.pet = pet
    vi.mocked(focusApi.petPlayState).mockResolvedValue({
      data: { session: null, summary: null, pet },
    } as any)

    await store.syncPlayState()

    expect(focusApi.petPlayState).toHaveBeenCalledWith(1)
    expect(store.session).toBeNull()
    expect(store.summary).toBeNull()
  })
})
