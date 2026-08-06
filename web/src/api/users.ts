import { http } from './http'

export const usersApi = {
  exportData: () => http.get<Record<string, unknown>>('/users/me/export'),
  deleteAccount: () => http.delete<void>('/users/me'),
}
