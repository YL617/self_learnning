import { http } from './http'
import type { OnboardingPayload, OnboardingResponse } from '@/types'

export const onboardingApi = {
  get: () => http.get<OnboardingResponse>('/users/me/onboarding'),
  submit: (data: OnboardingPayload) =>
    http.post<OnboardingResponse>('/onboarding', data),
}
