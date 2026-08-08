<script setup lang="ts">
import { CheckCircle2, Circle, Plus, Trash2 } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { todosApi } from '@/api/ops'
import type { Todo } from '@/types'

const todos = ref<Todo[]>([])
const title = ref('')
const due = ref(new Date().toISOString().slice(0, 10))
const error = ref('')
const success = ref('')

async function load() {
  try {
    const { data } = await todosApi.list()
    todos.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function add() {
  if (!title.value.trim()) return
  error.value = ''
  success.value = ''
  try {
    await todosApi.create(title.value.trim(), due.value)
    title.value = ''
    success.value = '待办已添加'
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '添加失败'
  }
}

async function toggle(todo: Todo) {
  await todosApi.update(todo.id, !todo.completed)
  await load()
}

async function remove(todo: Todo) {
  if (!window.confirm(`确定删除待办「${todo.title}」吗？`)) return
  await todosApi.remove(todo.id)
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">待办事项</h1>
        <p class="page-subtitle">记录每天要完成的学习任务</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" style="color: #15803d">{{ success }}</p>

    <div class="card">
      <div class="row gap wrap">
        <input v-model="title" class="input" style="flex: 1; min-width: 220px" placeholder="输入待办内容" />
        <input v-model="due" class="input" type="date" />
        <button class="btn btn-primary" type="button" @click="add">
          <Plus :size="16" />
          添加
        </button>
      </div>
    </div>

    <div class="card">
      <h2>我的待办</h2>
      <div v-if="!todos.length" class="empty">还没有待办</div>
      <div v-else class="list">
        <div v-for="todo in todos" :key="todo.id" class="list-item">
          <button class="btn" style="padding: 4px" type="button" @click="toggle(todo)">
            <CheckCircle2 v-if="todo.completed" :size="20" color="#15803d" />
            <Circle v-else :size="20" color="#94a3b8" />
          </button>
          <div class="list-item-main">
            <div class="list-item-title" :class="{ muted: todo.completed }">{{ todo.title }}</div>
            <div class="list-item-sub">{{ todo.due_date }}</div>
          </div>
          <button class="btn btn-ghost" style="padding: 6px" type="button" @click="remove(todo)">
            <Trash2 :size="16" color="#dc2626" />
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
