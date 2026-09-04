import { http } from './http'
import type {
  CalendarEvent,
  Course,
  CourseRecommendation,
  NotificationItem,
  Reminder,
  Todo,
  WeeklyReport,
} from '@/types'

export const todosApi = {
  list: () => http.get<Todo[]>('/todos'),
  create: (title: string, due_date: string) =>
    http.post<Todo>('/todos', { title, due_date }),
  update: (id: number, completed: boolean) =>
    http.patch<Todo>(`/todos/${id}`, { completed }),
  remove: (id: number) => http.delete<void>(`/todos/${id}`),
}

export const remindersApi = {
  list: () => http.get<Reminder[]>('/reminders'),
  create: (title: string, remind_at: string) =>
    http.post<Reminder>('/reminders', { title, remind_at }),
  remove: (id: number) => http.delete<void>(`/reminders/${id}`),
}

export const notificationsApi = {
  list: () => http.get<NotificationItem[]>('/notifications'),
  dismiss: (id: number) =>
    http.patch<void>(`/notifications/${id}/dismiss`),
}

export const calendarApi = {
  month: (month: string) => http.get<CalendarEvent[]>('/calendar', { params: { month } }),
}

export const coursesApi = {
  list: () => http.get<Course[]>('/courses'),
  recommendations: () =>
    http.get<CourseRecommendation[]>('/courses/recommendations'),
  saveRecommendation: (id: number) =>
    http.post<CourseRecommendation>(`/courses/recommendations/${id}/save`),
  dismissRecommendation: (id: number) =>
    http.post<CourseRecommendation>(`/courses/recommendations/${id}/dismiss`),
}

export const reportsApi = {
  weekly: () => http.get<WeeklyReport>('/reports/weekly'),
}

export const demoApi = {
  seed: () => http.post<{ message: string }>('/demo/seed'),
}
