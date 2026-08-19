<script setup lang="ts">
import {
  BarChart3,
  Bell,
  Bot,
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
  Shield,
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
  { label: 'AI 数字人', to: '/digital-human', icon: Bot },
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
    <router-link to="/profile" class="top-user">
      <span class="top-avatar">
        <img
          v-if="auth.user?.avatar_url"
          :src="auth.user.avatar_url"
          alt="头像"
        />
        <span v-else>{{ (auth.user?.nickname || auth.user?.username || '我').slice(0, 1) }}</span>
      </span>
      <span class="top-name">{{ auth.user?.nickname || auth.user?.username || '个人中心' }}</span>
    </router-link>
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
        <router-link
          v-if="auth.user?.is_admin"
          to="/admin"
          class="nav-item"
          :class="{ active: route.path.startsWith('/admin') }"
        >
          <Shield :size="18" />
          <span>管理后台</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <button class="btn btn-ghost btn-block" type="button" @click="logout">
          <LogOut :size="16" />
          退出登录
        </button>
        <div class="site-icp">皖ICP备2026025771号</div>
      </div>
    </aside>
    <main class="main">
      <router-view />
    </main>
    <AIPetFloater />
  </div>
</template>

<style scoped>
.top-user {
  position: fixed;
  top: 14px;
  right: 20px;
  z-index: 950;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  text-decoration: none;
  color: var(--text);
  box-shadow: var(--shadow);
}

.top-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  overflow: hidden;
  background: #e8f0fe;
  color: var(--primary);
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 14px;
}

.top-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.top-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}

@media (max-width: 900px) {
  .top-user {
    top: 10px;
    right: 12px;
  }
}
</style>
