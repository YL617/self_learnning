<script setup lang="ts">
import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  UserRound,
} from 'lucide-vue-next'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value.trim() || !email.value.trim() || password.value.length < 6) {
    error.value = '请填写用户名、邮箱和至少 6 位密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.register({
      username: username.value,
      email: email.value,
      password: password.value,
    })
    router.push('/onboarding')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '注册失败，请稍后重试'
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
        <h1>注册</h1>
        <p>创建一个账号，开始你的个性化学习</p>
      </div>
      <form class="auth-form" @submit.prevent="submit">
        <div class="field">
          <span>用户名</span>
          <div class="auth-input-wrap">
            <UserRound :size="16" />
            <input
              v-model="username"
              class="input"
              autocomplete="username"
              placeholder="2-64 个字符"
            />
          </div>
        </div>
        <div class="field">
          <span>邮箱</span>
          <div class="auth-input-wrap">
            <Mail :size="16" />
            <input
              v-model="email"
              class="input"
              type="email"
              autocomplete="email"
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
              autocomplete="new-password"
              placeholder="至少 6 位"
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
          {{ loading ? '注册中...' : '注册并进入' }}
        </button>
      </form>
      <p class="auth-link">已有账号？<router-link to="/login">去登录</router-link></p>
      <div class="auth-foot">
        <span>注册即代表同意</span>
        <router-link to="/terms">用户协议</router-link>
        <span>与</span>
        <router-link to="/privacy">隐私政策</router-link>
        <span class="auth-icp">皖ICP备2026025771号</span>
      </div>
    </div>
  </div>
</template>
