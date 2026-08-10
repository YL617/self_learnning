<script setup lang="ts">
import { ArrowRight } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
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
      <h1>注册 AI智学管家</h1>
      <p>创建一个账号，开始你的个性化学习</p>
      <form class="auth-form" @submit.prevent="submit">
        <div class="field">
          <span>用户名</span>
          <input v-model="username" class="input" placeholder="2-64 个字符" />
        </div>
        <div class="field">
          <span>邮箱</span>
          <input v-model="email" class="input" type="email" placeholder="demo@example.com" />
        </div>
        <div class="field">
          <span>密码</span>
          <input v-model="password" class="input" type="password" placeholder="至少 6 位" />
        </div>
        <p v-if="error" class="text-danger" style="margin: 0">{{ error }}</p>
        <button class="btn btn-primary btn-block" type="submit" :disabled="loading">
          <ArrowRight :size="16" />
          {{ loading ? '注册中...' : '注册并进入' }}
        </button>
      </form>
      <p class="auth-link">已有账号？<router-link to="/login">去登录</router-link></p>
      <p class="auth-link">
        注册即代表同意
        <router-link to="/terms">用户协议</router-link>
        与
        <router-link to="/privacy">隐私政策</router-link>
      </p>
      <p class="auth-icp">皖ICP备2026025771号</p>
    </div>
  </div>
</template>
