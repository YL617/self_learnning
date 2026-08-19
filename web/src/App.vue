<script setup lang="ts">
import { onMounted } from 'vue'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

onMounted(() => {
  if (auth.isLoggedIn) {
    auth.me().catch(() => {
      // 网络异常时保留本地会话，不阻断页面
    })
  }
})
</script>

<template>
  <router-view />
</template>
