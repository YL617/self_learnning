<script setup lang="ts">
import {
  BookOpenCheck,
  CalendarDays,
  FileQuestion,
  Files,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  PawPrint,
  Timer,
} from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

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
  </div>
</template>
