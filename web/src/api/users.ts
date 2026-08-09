import { http } from './http'
import type { User } from '@/types'

export const usersApi = {
  me: () => http.get<User>('/users/me'),
  updateMe: (nickname: string) => http.patch<User>('/users/me', { nickname }),
  changePassword: (oldPassword: string, newPassword: string) =>
    http.post<{ message: string }>('/users/me/password', {
      old_password: oldPassword,
      new_password: newPassword,
    }),
  uploadAvatar: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<User>('/users/me/avatar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  exportData: () => http.get<Record<string, unknown>>('/users/me/export'),
  deleteAccount: () => http.delete<void>('/users/me'),
}
