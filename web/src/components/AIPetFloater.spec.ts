import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { focusApi } from '@/api/focus'
import { useAuthStore } from '@/stores/auth'
import { petEvents } from '@/utils/petEvents'
import type { Pet, PetMessage, PetPlaySession } from '@/types'
import AIPetFloater from './AIPetFloater.vue'

vi.mock('@/api/focus', () => ({
  focusApi: {
    pet: vi.fn(),
    petPlayState: vi.fn(),
    petMessages: vi.fn(),
    chatPet: vi.fn(),
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

let currentWrapper: ReturnType<typeof mount> | undefined

async function mountFloater() {
  const pinia = createPinia()
  setActivePinia(pinia)
  localStorage.setItem('ai_study_token', 'test-token')
  localStorage.setItem('ai_study_user', JSON.stringify({ username: 'tester' }))
  useAuthStore().applySession({
    access_token: 'test-token',
    token_type: 'bearer',
    user: { id: 1, email: 't@example.com', username: 'tester', membership_level: 'free' },
  })
  const wrapper = mount(AIPetFloater, {
    global: {
      plugins: [pinia],
      stubs: { teleport: true },
    },
  })
  await flushPromises()
  currentWrapper = wrapper
  return wrapper
}

describe('AIPetFloater', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(focusApi.pet).mockResolvedValue({ data: pet } as any)
    vi.mocked(focusApi.petPlayState).mockResolvedValue({
      data: { session: null, summary: null, pet },
    } as any)
    vi.mocked(focusApi.petMessages).mockResolvedValue({ data: [] } as any)
  })

  afterEach(() => {
    currentWrapper?.unmount()
    currentWrapper = undefined
  })

  it('shows floater and opens chat with empty hint', async () => {
    const wrapper = await mountFloater()

    expect(wrapper.find('.pet-floater').exists()).toBe(true)
    await wrapper.find('.pet-floater').trigger('click')
    await flushPromises()

    expect(focusApi.petMessages).toHaveBeenCalledWith(1)
    await vi.waitFor(() => {
      expect(wrapper.find('.chat-hint').exists()).toBe(true)
    })
    expect(wrapper.find('.chat-hint').text()).toContain('先打个招呼吧')
  })

  it('sends chat message', async () => {
    const assistant: PetMessage = {
      id: 3,
      role: 'assistant',
      kind: 'chat',
      content: '好的，我们一起复习错题吧！',
      created_at: new Date().toISOString(),
    }
    const user: PetMessage = {
      id: 2,
      role: 'user',
      kind: 'chat',
      content: '今天学什么',
      created_at: new Date().toISOString(),
    }
    vi.mocked(focusApi.chatPet).mockResolvedValue({
      data: { reply: assistant.content, pet, messages: [user, assistant] },
    } as any)
    const wrapper = await mountFloater()

    await wrapper.find('.pet-floater').trigger('click')
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.find('.chat-form input').exists()).toBe(true)
    })
    await wrapper.find('.chat-form input').setValue('今天学什么')
    await wrapper.find('.chat-form').trigger('submit')

    expect(focusApi.chatPet).toHaveBeenCalledWith(1, '今天学什么')
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('一起复习错题吧')
    })
  })

  it('plays talking animation with spoken text on learning events', async () => {
    const wrapper = await mountFloater()

    petEvents.emit({ kind: 'focus' })
    await nextTick()

    expect(wrapper.find('.pet-sprite').attributes('data-state')).toBe('talking')
    await vi.waitFor(() => {
      expect(wrapper.find('.spoken-line').text()).toContain('专注完成')
    })
    expect(wrapper.find('.pet-says').exists()).toBe(false)
  })

  it('shows countdown and home button while playing', async () => {
    const session: PetPlaySession = {
      id: 1,
      status: 'active',
      started_at: new Date().toISOString(),
      duration_minutes: 15,
      coin_cost: 20,
      mood_gain: 15,
      exp_gain: 20,
      hunger_loss: 15,
      created_at: new Date().toISOString(),
    }
    vi.mocked(focusApi.petPlayState).mockResolvedValue({
      data: {
        session,
        summary: null,
        pet: { ...pet, playing_until: new Date(Date.now() + 600000).toISOString() },
      },
    } as any)

    const wrapper = await mountFloater()

    expect(wrapper.find('.countdown').exists()).toBe(true)
    expect(wrapper.text()).toContain('回家')
  })

  it('stays hidden when user hid the pet', async () => {
    localStorage.setItem('ai_pet_hidden', '1')
    const wrapper = await mountFloater()

    expect(wrapper.find('.pet-floater').exists()).toBe(false)
  })
})
