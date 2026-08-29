<script setup lang="ts">
import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
  UserRound,
} from 'lucide-vue-next'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const account = ref('')
const password = ref('')
const showPassword = ref(false)
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
      <div class="auth-brand">
        <span class="brand-mark">智</span>
        <span class="auth-brand-name">AI智学管家</span>
      </div>
      <div class="auth-head">
        <h1>登录</h1>
        <p>继续你的学习规划、练习与成长闭环</p>
      </div>
      <form class="auth-form" @submit.prevent="submit">
        <div class="field">
          <span>邮箱或用户名</span>
          <div class="auth-input-wrap">
            <UserRound :size="16" />
            <input
              v-model="account"
              class="input"
              autocomplete="username"
              placeholder="demo@example.com"
            />
          </div>
        </div>
        <div class="field">
          <span>密码</span>
          <div class="auth-input-wrap">
            <LockKeyhole :size="16" />
            <input
              v-model="password"
              class="input"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="请输入密码"
            />
            <button class="password-toggle" type="button" @click="showPassword = !showPassword">
              <EyeOff v-if="showPassword" :size="16" />
              <Eye v-else :size="16" />
            </button>
          </div>
        </div>
        <div v-if="error" class="auth-error">
          <AlertCircle :size="15" />
          <span>{{ error }}</span>
        </div>
        <button class="btn btn-primary btn-block" type="submit" :disabled="loading">
          <ArrowRight :size="16" />
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
      <p class="auth-link">还没有账号？<router-link to="/register">立即注册</router-link></p>
      <div class="auth-foot">
        <router-link to="/privacy">隐私政策</router-link>
        <span>·</span>
        <router-link to="/terms">用户协议</router-link>
        <span class="auth-icp">皖ICP备2026025771号</span>
      </div>
    </div>
  </div>
</template>
