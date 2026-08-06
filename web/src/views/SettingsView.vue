<script setup lang="ts">
import { Download, Trash2 } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { usersApi } from '@/api/users'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const error = ref('')
const success = ref('')

async function exportData() {
  error.value = ''
  success.value = ''
  try {
    const { data } = await usersApi.exportData()
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'ai-study-data.json'
    link.click()
    URL.revokeObjectURL(url)
    success.value = '数据已导出'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '导出失败'
  }
}

async function deleteAccount() {
  if (!window.confirm('确定注销账号吗？所有学习数据将永久删除且无法恢复。')) return
  error.value = ''
  success.value = ''
  try {
    await usersApi.deleteAccount()
    auth.logout()
    router.push('/login')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '注销失败'
  }
}
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">账号设置</h1>
        <p class="page-subtitle">导出个人学习数据，或注销账号并删除全部数据</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" style="color: #15803d">{{ success }}</p>

    <div class="card">
      <h2><Download :size="16" style="vertical-align: -2px" /> 数据导出</h2>
      <p class="muted">
        导出内容包括个人资料、学习计划、练习记录、错题本、专注记录、宠物与智学币流水。
      </p>
      <button class="btn btn-primary" type="button" @click="exportData">
        <Download :size="16" />
        导出 JSON 数据
      </button>
    </div>

    <div class="card">
      <h2><Trash2 :size="16" style="vertical-align: -2px" /> 注销账号</h2>
      <p class="muted">注销后账号和相关学习数据将永久删除，此操作不可恢复。</p>
      <button class="btn btn-danger" type="button" @click="deleteAccount">
        <Trash2 :size="16" />
        注销账号
      </button>
    </div>
  </section>
</template>
