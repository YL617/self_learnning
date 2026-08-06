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
      ],
    },
  ],
})

router.beforeEach((to) => {
  const loggedIn = Boolean(getToken())
  if (!to.meta.public && !loggedIn) {
    return { name: 'login' }
  }
  if ((to.name === 'login' || to.name === 'register') && loggedIn) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
