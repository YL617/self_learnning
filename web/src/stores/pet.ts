import { defineStore } from 'pinia'

import { focusApi } from '@/api/focus'
import type { Pet, PetPlaySession, PetPlaySummary } from '@/types'

export const usePetStore = defineStore('pet', {
  state: () => ({
    pet: null as Pet | null,
    session: null as PetPlaySession | null,
    summary: null as PetPlaySummary | null,
    loaded: false,
  }),
  getters: {
    isPlaying: (state) => state.session?.status === 'active',
    remainingSeconds: (state) => {
      if (!state.pet?.playing_until) return 0
      const raw = state.pet.playing_until
      const normalized = /(Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`
      const until = new Date(normalized).getTime()
      return Math.max(0, Math.floor((until - Date.now()) / 1000))
    },
  },
  actions: {
    applyPet(pet: Pet) {
      this.pet = pet
    },
    async loadPet(force = false) {
      if (this.loaded && !force) return this.pet
      const { data } = await focusApi.pet()
      this.pet = data
      this.loaded = true
      return data
    },
    async syncPlayState() {
      if (!this.pet) return null
      const { data } = await focusApi.petPlayState(this.pet.id)
      this.session = data.session ?? null
      this.summary = data.summary ?? null
      this.pet = data.pet
      return data
    },
    async startPlay() {
      if (!this.pet) return null
      const { data } = await focusApi.startPetPlay(this.pet.id)
      this.session = data.session ?? null
      this.summary = data.summary ?? null
      this.pet = data.pet
      return data
    },
    async endPlay() {
      if (!this.pet) return null
      const { data } = await focusApi.endPetPlay(this.pet.id)
      this.session = data.session ?? null
      this.summary = data.summary ?? null
      this.pet = data.pet
      return data
    },
    clearSummary() {
      this.summary = null
    },
    reset() {
      this.pet = null
      this.session = null
      this.summary = null
      this.loaded = false
    },
  },
})
