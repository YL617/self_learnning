<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import type { AdminUser } from '@/types'

const users = ref<AdminUser[]>([])
const keyword = ref('')
const error = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await adminApi.users({ q: keyword.value || undefined })
    users.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function updateUser(user: AdminUser, patch: Record<string, unknown>) {
  try {
    const { data } = await adminApi.updateUser(user.id, patch)
    Object.assign(user, data)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '更新失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">用户管理</h1>
        <p class="page-subtitle">搜索、禁用、调整会员等级与角色</p>
      </div>
      <div class="row gap">
        <input v-model="keyword" class="input" placeholder="搜索邮箱 / 用户名 / 昵称" @keyup.enter="load" />
        <button class="btn btn-primary" type="button" @click="load">搜索</button>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <div v-if="loading && !users.length" class="empty">正在加载用户...</div>
    <div v-else class="table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>会员</th>
            <th>角色</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>
              <div class="user-cell">
                <strong>{{ user.nickname || user.username }}</strong>
                <small>{{ user.email }}</small>
              </div>
            </td>
            <td>
              <select
                class="select"
                :value="user.membership_level"
                @change="updateUser(user, { membership_level: ($event.target as HTMLSelectElement).value })"
              >
                <option value="free">免费</option>
                <option value="vip">VIP</option>
              </select>
            </td>
            <td>
              <select
                class="select"
                :value="user.role"
                @change="updateUser(user, { role: ($event.target as HTMLSelectElement).value })"
              >
                <option value="user">用户</option>
                <option value="admin">管理员</option>
              </select>
            </td>
            <td>
              <span class="badge" :class="user.is_active ? 'badge-green' : 'badge-amber'">
                {{ user.is_active ? '启用' : '禁用' }}
              </span>
            </td>
            <td>
              <button
                class="btn btn-ghost"
                type="button"
                @click="updateUser(user, { is_active: !user.is_active })"
              >
                {{ user.is_active ? '禁用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.table-wrap {
  overflow-x: auto;
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  font-size: 13px;
}

.admin-table th,
.admin-table td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.admin-table th {
  background: #f8fafc;
  color: var(--text-2);
  font-weight: 600;
}

.user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-cell small {
  color: var(--text-2);
}

.select {
  min-width: 90px;
}
</style>
