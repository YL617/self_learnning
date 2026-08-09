<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import type { DocumentItem } from '@/types'

const items = ref<DocumentItem[]>([])
const error = ref('')

async function load() {
  try {
    const { data } = await adminApi.documents()
    items.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function remove(item: DocumentItem) {
  if (!window.confirm(`确定删除文档「${item.filename}」吗？`)) return
  try {
    await adminApi.deleteDocument(item.id)
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
        <h1 class="page-title">文档管理</h1>
        <p class="page-subtitle">查看并删除用户上传的学习文档</p>
      </div>
    </div>
    <p v-if="error" class="text-danger">{{ error }}</p>
    <div v-if="!items.length" class="empty">暂无文档</div>
    <div v-else class="list">
      <div v-for="item in items" :key="item.id" class="card list-item">
        <div class="list-item-main">
          <div class="list-item-title">{{ item.filename }}</div>
          <div class="list-item-sub">
            {{ item.file_type }} · {{ item.status }} · {{ item.size_bytes }} 字节
          </div>
        </div>
        <button class="btn btn-danger" type="button" @click="remove(item)">删除</button>
      </div>
    </div>
  </section>
</template>
