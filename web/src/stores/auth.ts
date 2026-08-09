import { defineStore } from 'pinia'

import { http, clearSession, setSession } from '@/api/http'
import type { TokenResponse, User } from '@/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('ai_study_token') || '',
    user: JSON.parse(localStorage.getItem('ai_study_user') || 'null') as User | null,
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
  },
  actions: {
    async login(account: string, password: string) {
      const { data } = await http.post<TokenResponse>('/auth/login', {
        account,
        password,
      })
      this.applySession(data)
    },
    async register(payload: { email: string; username: string; password: string }) {
      const { data } = await http.post<TokenResponse>('/auth/register', payload)
      this.applySession(data)
    },
    applySession(data: TokenResponse) {
      setSession(data)
      this.token = data.access_token
      this.user = data.user
    },
    setUser(user: User) {
      this.user = user
      localStorage.setItem('ai_study_user', JSON.stringify(user))
    },
    async me() {
      const { data } = await http.get<User>('/users/me')
      this.setUser(data)
      return data
    },
    logout() {
      clearSession()
      this.token = ''
      this.user = null
    },
  },
})
