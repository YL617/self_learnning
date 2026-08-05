<script setup lang="ts">
import { ArrowRight } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const account = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  if (!account.value.trim() || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.login(account.value, password.value)
    router.push('/')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-screen">
    <div class="auth-card">
      <h1>登录 AI智学管家</h1>
      <p>继续你的学习规划、练习与成长闭环</p>
      <form class="auth-form" @submit.prevent="submit">
        <div class="field">
          <span>邮箱或用户名</span>
          <input v-model="account" class="input" placeholder="demo@example.com" />
        </div>
        <div class="field">
          <span>密码</span>
          <input v-model="password" class="input" type="password" placeholder="请输入密码" />
        </div>
        <p v-if="error" class="text-danger" style="margin: 0">{{ error }}</p>
        <button class="btn btn-primary btn-block" type="submit" :disabled="loading">
          <ArrowRight :size="16" />
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
      <p class="auth-link">还没有账号？<router-link to="/register">立即注册</router-link></p>
    </div>
  </div>
</template>
