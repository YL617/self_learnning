<script setup lang="ts">
import { Bot, CheckCircle2, Crown, Send, Sparkles } from 'lucide-vue-next'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { planChatApi } from '@/api/planChat'
import { useAuthStore } from '@/stores/auth'
import type { PlanDraft } from '@/types'

const auth = useAuthStore()
const router = useRouter()

const isVip = computed(() =>
  ['advanced', 'full'].includes(auth.user?.membership_level || ''),
)
const messages = ref<Array<{ role: string; content: string }>>([])
const draft = ref<PlanDraft | null>(null)
const sessionId = ref<number | null>(null)
const input = ref('')
const loading = ref(false)
const error = ref('')
const messagesEl = ref<HTMLElement | null>(null)

function scrollDown() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function startNew() {
  loading.value = true
  error.value = ''
  messages.value = []
  draft.value = null
  sessionId.value = null
  try {
    const { data } = await planChatApi.start()
    sessionId.value = data.session_id
    messages.value.push({ role: 'assistant', content: data.reply })
    scrollDown()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '无法开始对话'
  } finally {
    loading.value = false
  }
}

async function send() {
  const content = input.value.trim()
  if (!content || !sessionId.value || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content })
  loading.value = true
  error.value = ''
  try {
    const { data } = await planChatApi.send(sessionId.value, content)
    messages.value.push({ role: 'assistant', content: data.reply })
    if (data.draft) {
      draft.value = data.draft
    }
    scrollDown()
  } catch (err: any) {
    messages.value.pop()
    error.value = err?.response?.data?.detail || '发送失败'
  } finally {
    loading.value = false
  }
}

async function confirmPlan() {
  if (!sessionId.value || !draft.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const { data } = await planChatApi.confirm(sessionId.value)
    router.push(`/plans/${data.plan_id}`)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '确认失败'
  } finally {
    loading.value = false
  }
}

async function enableVip() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await planChatApi.enableDemoVip()
    auth.setUser(data)
    await startNew()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '开通失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (isVip.value) startNew()
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">AI 对话规划</h1>
        <p class="page-subtitle">与 AI 对话完善学习计划，确认后再生成正式计划</p>
      </div>
      <span v-if="isVip" class="badge badge-amber"><Crown :size="14" /> VIP 专属</span>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>

    <div v-if="!isVip" class="card vip-lock">
      <Crown :size="40" />
      <h2>AI 对话规划仅限 VIP 用户</h2>
      <p class="muted">AI 会主动追问你的专业、目标、时间与薄弱点，并支持在对话中反复调整计划草稿。</p>
      <button class="btn btn-primary" type="button" :disabled="loading" @click="enableVip">
        <Sparkles :size="16" />
        模拟开通 VIP（演示）
      </button>
    </div>

    <template v-else>
      <div class="card chat-card">
        <div class="chat-header">
          <div class="row gap">
            <Bot :size="18" />
            <strong>规划顾问</strong>
          </div>
          <button class="btn btn-ghost" type="button" :disabled="loading" @click="startNew">
            新对话
          </button>
        </div>

        <div ref="messagesEl" class="chat-messages">
          <div
            v-for="(message, index) in messages"
            :key="index"
            class="chat-message"
            :class="message.role === 'user' ? 'user' : 'assistant'"
          >
            {{ message.content }}
          </div>
          <div v-if="loading" class="chat-message assistant typing">AI 正在思考...</div>
        </div>

        <div class="chat-input">
          <input
            v-model="input"
            class="input"
            placeholder="回答 AI 的问题，或提出计划修改意见"
            :disabled="loading"
            @keyup.enter="send"
          />
          <button class="btn btn-primary" type="button" :disabled="loading || !input.trim()" @click="send">
            <Send :size="16" />
            发送
          </button>
        </div>
      </div>

      <div v-if="draft" class="card">
        <div class="row space-between">
          <h2 style="margin: 0"><Sparkles :size="16" style="vertical-align: -2px" /> 计划草稿</h2>
          <button class="btn btn-primary" type="button" :disabled="loading" @click="confirmPlan">
            <CheckCircle2 :size="16" />
            确认并生成正式计划
          </button>
        </div>
        <p class="page-subtitle">{{ draft.title }} · {{ draft.goal }}</p>
        <div class="list" style="margin-top: 12px">
          <div v-for="item in draft.items" :key="item.id || item.order_index" class="list-item">
            <div class="list-item-main">
              <div class="list-item-title">{{ item.title }}</div>
              <div class="list-item-sub">
                {{ item.subject || '综合' }} · {{ item.scheduled_date }} · {{ item.duration_minutes }} 分钟
              </div>
            </div>
          </div>
        </div>
        <p class="muted" style="margin: 12px 0 0">确认前可以继续在对话中提出修改，草稿会随之更新。</p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.vip-lock {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  padding: 40px 24px;
}

.vip-lock h2 {
  margin: 6px 0 0;
}

.vip-lock p {
  max-width: 480px;
  margin: 0 0 8px;
}

.chat-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}

.chat-messages {
  max-height: 420px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 2px;
}

.chat-message {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: var(--radius);
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-message.assistant {
  align-self: flex-start;
  background: #f1f5f9;
  color: var(--text);
}

.chat-message.user {
  align-self: flex-end;
  background: var(--primary);
  color: #fff;
}

.chat-message.typing {
  color: var(--text-2);
}

.chat-input {
  display: flex;
  gap: 8px;
}

.chat-input .input {
  flex: 1;
}
</style>
