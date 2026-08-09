<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import type { AdminQuestion } from '@/types'

const items = ref<AdminQuestion[]>([])
const error = ref('')

async function load() {
  try {
    const { data } = await adminApi.questions()
    items.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function remove(item: AdminQuestion) {
  if (!window.confirm(`确定删除题目「${item.stem.slice(0, 30)}」吗？`)) return
  try {
    await adminApi.deleteQuestion(item.id)
    items.value = items.value.filter((row) => row.id !== item.id)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">题目管理</h1>
        <p class="page-subtitle">查看并删除平台生成的练习题目</p>
      </div>
    </div>
    <p v-if="error" class="text-danger">{{ error }}</p>
    <div v-if="!items.length" class="empty">暂无题目</div>
    <div v-else class="list">
      <div v-for="item in items" :key="item.id" class="card">
        <div class="row gap wrap" style="justify-content: space-between">
          <div>
            <span class="badge">{{ item.subject }}</span>
            <span class="badge badge-amber">{{ item.question_type }}</span>
          </div>
          <button class="btn btn-danger" type="button" @click="remove(item)">删除</button>
        </div>
        <p style="margin: 8px 0 0">{{ item.stem }}</p>
        <small class="muted">{{ item.knowledge_point }} · {{ item.created_at }}</small>
      </div>
    </div>
  </section>
</template>
