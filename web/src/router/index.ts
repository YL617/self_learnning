import { createRouter, createWebHistory } from 'vue-router'

import { getToken } from '@/api/http'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { public: true },
    },
    {
      path: '/onboarding',
      name: 'onboarding',
      component: () => import('@/views/OnboardingView.vue'),
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: () => import('@/views/PrivacyView.vue'),
      meta: { public: true },
    },
    {
      path: '/terms',
      name: 'terms',
      component: () => import('@/views/TermsView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      children: [
        { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
        { path: 'profile', name: 'profile', component: () => import('@/views/ProfileView.vue') },
        {
          path: 'digital-human',
          name: 'digital-human',
          component: () => import('@/views/DigitalHumanView.vue'),
        },
        { path: 'plans', name: 'plans', component: () => import('@/views/PlansView.vue') },
        {
          path: 'plans/chat',
          name: 'plan-chat',
          component: () => import('@/views/PlanChatView.vue'),
        },
        {
          path: 'plans/:id',
          name: 'plan-detail',
          component: () => import('@/views/PlanDetailView.vue'),
        },
        {
          path: 'questions',
          name: 'questions',
          component: () => import('@/views/QuestionsView.vue'),
        },
        { path: 'files', name: 'files', component: () => import('@/views/FilesView.vue') },
        { path: 'focus', name: 'focus', component: () => import('@/views/FocusView.vue') },
        { path: 'pet', name: 'pet', component: () => import('@/views/PetView.vue') },
        {
          path: 'wrong-book',
          name: 'wrong-book',
          component: () => import('@/views/WrongBookView.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/SettingsView.vue'),
        },
        {
          path: 'todos',
          name: 'todos',
          component: () => import('@/views/ScheduleView.vue'),
        },
        {
          path: 'calendar',
          redirect: { path: '/todos', query: { tab: 'calendar' } },
        },
        {
          path: 'reminders',
          name: 'reminders',
          component: () => import('@/views/RemindersView.vue'),
        },
        {
          path: 'courses',
          name: 'courses',
          component: () => import('@/views/CoursesView.vue'),
        },
        {
          path: 'reports',
          name: 'reports',
          component: () => import('@/views/ReportsView.vue'),
        },
      ],
    },
    {
      path: '/admin',
      component: () => import('@/layouts/AdminLayout.vue'),
      children: [
        {
          path: '',
          name: 'admin-dashboard',
          component: () => import('@/views/admin/AdminDashboardView.vue'),
        },
        {
          path: 'users',
          name: 'admin-users',
          component: () => import('@/views/admin/AdminUsersView.vue'),
        },
        {
          path: 'codes',
          name: 'admin-codes',
          component: () => import('@/views/admin/AdminCodesView.vue'),
        },
        {
          path: 'questions',
          name: 'admin-questions',
          component: () => import('@/views/admin/AdminQuestionsView.vue'),
        },
        {
          path: 'documents',
          name: 'admin-documents',
          component: () => import('@/views/admin/AdminDocumentsView.vue'),
        },
        {
          path: 'courses',
          name: 'admin-courses',
          component: () => import('@/views/admin/AdminCoursesView.vue'),
        },
      ],
    },
  ],
})

function isAdmin(): boolean {
  try {
    const user = JSON.parse(localStorage.getItem('ai_study_user') || 'null')
    return Boolean(user && (user.is_admin === true || user.role === 'admin'))
  } catch {
    return false
  }
}

router.beforeEach((to) => {
  const loggedIn = Boolean(getToken())
  if (!to.meta.public && !loggedIn) {
    return { name: 'login' }
  }
  if (to.path.startsWith('/admin') && !isAdmin()) {
    return { name: 'dashboard' }
  }
  if ((to.name === 'login' || to.name === 'register') && loggedIn) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
