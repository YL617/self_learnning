<script setup lang="ts">
import {
  ArrowLeft,
  FileQuestion,
  Files,
  GraduationCap,
  KeyRound,
  LayoutDashboard,
  Users,
} from 'lucide-vue-next'
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { label: '运营看板', to: '/admin', icon: LayoutDashboard },
  { label: '用户管理', to: '/admin/users', icon: Users },
  { label: '激活码管理', to: '/admin/codes', icon: KeyRound },
  { label: '题目管理', to: '/admin/questions', icon: FileQuestion },
  { label: '文档管理', to: '/admin/documents', icon: Files },
  { label: '课程管理', to: '/admin/courses', icon: GraduationCap },
]
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="admin-brand">
        <strong>AI智学管家</strong>
        <small>管理后台</small>
      </div>
      <nav class="admin-nav">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="admin-nav-item"
          :class="{ active: route.path === item.to }"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="admin-footer">
        <router-link to="/" class="btn btn-ghost btn-block">
          <ArrowLeft :size="16" />
          返回学习端
        </router-link>
      </div>
    </aside>
    <main class="admin-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.admin-shell {
  display: flex;
  min-height: 100vh;
  background: var(--bg);
}

.admin-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #111827;
  color: #fff;
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  gap: 18px;
  position: sticky;
  top: 0;
  height: 100vh;
}

.admin-brand {
  display: flex;
  flex-direction: column;
  padding: 4px 8px;
}

.admin-brand strong {
  font-size: 16px;
}

.admin-brand small {
  color: #9ca3af;
  font-size: 12px;
}

.admin-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.admin-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  color: #d1d5db;
  text-decoration: none;
  font-weight: 500;
}

.admin-nav-item:hover,
.admin-nav-item.active {
  background: #1f2937;
  color: #fff;
}

.admin-footer {
  border-top: 1px solid #374151;
  padding-top: 12px;
}

.admin-footer .btn {
  color: #d1d5db;
  border-color: #374151;
  background: transparent;
}

.admin-main {
  flex: 1;
  min-width: 0;
  padding: 28px;
}

@media (max-width: 900px) {
  .admin-shell {
    flex-direction: column;
  }

  .admin-sidebar {
    width: 100%;
    height: auto;
    position: static;
  }

  .admin-nav {
    flex-direction: row;
    overflow-x: auto;
  }

  .admin-nav-item {
    white-space: nowrap;
  }

  .admin-main {
    padding: 16px;
  }
}
</style>
