<script setup lang="ts">
import {
  BarChart3,
  Bell,
  BookOpenCheck,
  Calendar,
  CalendarDays,
  FileQuestion,
  Files,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  PawPrint,
  Settings,
  Timer,
} from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

import AIPetFloater from '@/components/AIPetFloater.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const navItems = [
  { label: '学习总览', to: '/', icon: LayoutDashboard },
  { label: '学习计划', to: '/plans', icon: CalendarDays },
  { label: '对话规划', to: '/plans/chat', icon: MessageSquareText },
  { label: '智能练习', to: '/questions', icon: FileQuestion },
  { label: '错题本', to: '/wrong-book', icon: BookOpenCheck },
  { label: '文件出题', to: '/files', icon: Files },
  { label: '专注模式', to: '/focus', icon: Timer },
  { label: '我的宠物', to: '/pet', icon: PawPrint },
  { label: '待办与日历', to: '/todos', icon: Calendar },
  { label: '提醒通知', to: '/reminders', icon: Bell },
  { label: '公开课程', to: '/courses', icon: GraduationCap },
  { label: '学习周报', to: '/reports', icon: BarChart3 },
  { label: '账号设置', to: '/settings', icon: Settings },
]

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">智</span>
        <div>
          <strong>AI智学管家</strong>
          <small>自适应学习平台</small>
        </div>
      </div>
      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ active: route.path === item.to || (item.to !== '/' && route.path.startsWith(item.to)) }"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <button class="btn btn-ghost btn-block" type="button" @click="logout">
          <LogOut :size="16" />
          退出登录
        </button>
      </div>
    </aside>
    <main class="main">
      <router-view />
    </main>
    <AIPetFloater />
  </div>
</template>
