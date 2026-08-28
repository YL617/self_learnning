<script setup lang="ts">
import { Bell, Plus, Trash2 } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { notificationsApi, remindersApi } from '@/api/ops'
import type { NotificationItem, Reminder } from '@/types'

const notifications = ref<NotificationItem[]>([])
const reminders = ref<Reminder[]>([])
const title = ref('')
const remindAt = ref('')
const error = ref('')
const success = ref('')

function formatRemindTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function load() {
  error.value = ''
  try {
    const [noteRes, remindRes] = await Promise.all([
      notificationsApi.list(),
      remindersApi.list(),
    ])
    notifications.value = noteRes.data
    reminders.value = remindRes.data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function add() {
  if (!title.value.trim() || !remindAt.value) return
  try {
    await remindersApi.create(title.value.trim(), new Date(remindAt.value).toISOString())
    title.value = ''
    remindAt.value = ''
    success.value = '提醒已添加'
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '添加失败'
  }
}

async function dismiss(item: NotificationItem) {
  if (item.kind !== 'reminder') return
  await notificationsApi.dismiss(item.id)
  await load()
}

async function remove(reminder: Reminder) {
  await remindersApi.remove(reminder.id)
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">提醒与通知</h1>
        <p class="page-subtitle">设置学习提醒，查看未完成任务与到期通知</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div class="card">
      <h2><Bell :size="16" style="vertical-align: -2px" /> 通知中心</h2>
      <div v-if="!notifications.length" class="empty">暂无通知</div>
      <div v-else class="list">
        <div v-for="item in notifications" :key="`${item.kind}-${item.id}`" class="list-item">
            <div class="list-item-main">
              <div class="list-item-title">{{ item.title }}</div>
              <div class="list-item-sub">
                {{ item.kind === 'reminder' ? '定时提醒 · ' + formatRemindTime(item.remind_at) : '未完成任务' }}
              </div>
          </div>
          <button v-if="item.kind === 'reminder'" class="btn btn-ghost" type="button" @click="dismiss(item)">
            已读
          </button>
        </div>
      </div>
    </div>

    <div class="card">
      <h2><Plus :size="16" style="vertical-align: -2px" /> 新建提醒</h2>
      <div class="row gap wrap">
        <input v-model="title" class="input" style="flex: 1; min-width: 200px" placeholder="提醒内容" />
        <input v-model="remindAt" class="input" type="datetime-local" />
        <button class="btn btn-primary" type="button" @click="add">
          <Plus :size="16" />
          添加
        </button>
      </div>
    </div>

    <div class="card">
      <h2>我的提醒</h2>
      <div v-if="!reminders.length" class="empty">还没有提醒</div>
      <div v-else class="list">
        <div v-for="reminder in reminders" :key="reminder.id" class="list-item">
          <div class="list-item-main">
            <div class="list-item-title">{{ reminder.title }}</div>
            <div class="list-item-sub">{{ formatRemindTime(reminder.remind_at) }}</div>
          </div>
          <button class="btn btn-ghost" style="padding: 6px" type="button" @click="remove(reminder)">
            <Trash2 :size="16" color="#dc2626" />
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
