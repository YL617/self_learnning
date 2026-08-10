<script setup lang="ts">
import { Apple, Crown, Gamepad2, Hand, MessageCircle, Send, Sparkles } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { focusApi } from '@/api/focus'
import { usersApi } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import type { Pet, PetMessage } from '@/types'

const SPRITE_URL = '/pets/airi/spritesheet.webp'
const CELL_WIDTH = 192
const CELL_HEIGHT = 208
const ATLAS_COLUMNS = 8
const ATLAS_ROWS = 9
const SCALE = 1.05

type AnimationId = 'idle' | 'waving' | 'jumping' | 'talking' | 'waiting'

const ANIMATIONS: Record<
  AnimationId,
  { row: number; durations: number[]; loop: boolean }
> = {
  idle: { row: 0, durations: [280, 110, 110, 140, 140, 320], loop: true },
  waving: { row: 3, durations: [140, 140, 140, 280], loop: false },
  jumping: { row: 4, durations: [140, 140, 140, 140, 280], loop: false },
  talking: { row: 0, durations: [95, 130, 95, 130, 95, 150], loop: true },
  waiting: { row: 6, durations: [150, 150, 150, 150, 150, 260], loop: true },
}

const auth = useAuthStore()
const pet = ref<Pet | null>(null)
const messages = ref<PetMessage[]>([])
const chatInput = ref('')
const sending = ref(false)
const loading = ref(true)
const access = ref(false)
const accessReason = ref('')
const error = ref('')
const animation = ref<AnimationId>('idle')
const frame = ref(0)
const chatBodyRef = ref<HTMLElement | null>(null)
let animationTimer: number | undefined

const spriteStyle = computed(() => {
  const state = ANIMATIONS[animation.value]
  return {
    width: `${CELL_WIDTH * SCALE}px`,
    height: `${CELL_HEIGHT * SCALE}px`,
    backgroundImage: `url(${SPRITE_URL})`,
    backgroundSize: `${CELL_WIDTH * ATLAS_COLUMNS * SCALE}px ${
      CELL_HEIGHT * ATLAS_ROWS * SCALE
    }px`,
    backgroundPosition: `${-frame.value * CELL_WIDTH * SCALE}px ${
      -state.row * CELL_HEIGHT * SCALE
    }px`,
  }
})

function runAnimation(id: AnimationId) {
  if (animationTimer !== undefined) window.clearTimeout(animationTimer)
  animation.value = id
  frame.value = 0
  const state = ANIMATIONS[id]
  const step = (index: number) => {
    if (index >= state.durations.length) {
      if (state.loop) {
        frame.value = 0
        animationTimer = window.setTimeout(() => step(1), state.durations[0])
      } else {
        runAnimation(pet.value?.runaway ? 'waiting' : 'idle')
      }
      return
    }
    frame.value = index
    animationTimer = window.setTimeout(() => step(index + 1), state.durations[index])
  }
  step(0)
}

async function scrollChat() {
  await nextTick()
  if (chatBodyRef.value) {
    chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const accessRes = await usersApi.digitalHumanAccess()
    access.value = accessRes.data.access
    accessReason.value = accessRes.data.reason || ''
    if (!access.value) return
    const petRes = await focusApi.pet()
    pet.value = petRes.data
    const messagesRes = await focusApi.petMessages(pet.value.id)
    messages.value = messagesRes.data
    runAnimation(pet.value.runaway ? 'waiting' : 'idle')
    await scrollChat()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function sendMessage() {
  const text = chatInput.value.trim()
  if (!pet.value || !text || sending.value) return
  sending.value = true
  error.value = ''
  try {
    const { data } = await focusApi.chatPet(pet.value.id, text)
    pet.value = data.pet
    messages.value = data.messages
    chatInput.value = ''
    runAnimation('talking')
    setTimeout(() => runAnimation('idle'), 2200)
    await scrollChat()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '发送失败'
  } finally {
    sending.value = false
  }
}

async function feed(amount: number) {
  if (!pet.value) return
  try {
    const { data } = await focusApi.feedPet(pet.value.id, amount)
    pet.value = data
    runAnimation('jumping')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '喂食失败'
  }
}

async function pat() {
  if (!pet.value) return
  try {
    const { data } = await focusApi.patPet(pet.value.id)
    pet.value = data.pet
    runAnimation('waving')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '互动失败'
  }
}

async function play() {
  if (!pet.value) return
  try {
    const { data } = await focusApi.playPet(pet.value.id)
    pet.value = data.pet
    runAnimation('jumping')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '互动失败'
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (animationTimer !== undefined) window.clearTimeout(animationTimer)
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">AI 数字人</h1>
        <p class="page-subtitle">你的 AI 学习伙伴，会说话、会互动、记得你的学习节奏</p>
      </div>
      <span class="badge badge-teal">
        <Crown :size="13" />
        完整会员专属
      </span>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>

    <div v-if="loading" class="empty">正在加载数字人...</div>

    <div v-else-if="!access" class="card upgrade-card">
      <Sparkles :size="28" />
      <h2>升级完整会员后解锁 AI 数字人</h2>
      <p class="muted">{{ accessReason || '数字人功能需要完整会员（30 元/月）' }}</p>
      <router-link to="/profile" class="btn btn-primary">前往个人中心</router-link>
    </div>

    <template v-else-if="pet">
      <div class="grid grid-2 digital-grid">
        <div class="card stage-card">
          <div class="digital-stage">
            <div class="pet-sprite" :style="spriteStyle" />
            <span class="stage-badge">AI 数字人 · Lv.{{ pet.level }}</span>
          </div>
          <h2 class="pet-name">{{ pet.name }} · Lv.{{ pet.level }}</h2>
          <div class="stat-row">
            <span>心情 {{ pet.mood }}/100</span>
            <span>饱食度 {{ pet.hunger }}/100</span>
            <span>经验 {{ pet.exp }}/{{ pet.level * 100 }}</span>
          </div>
          <div class="actions">
            <button class="btn btn-teal" type="button" @click="feed(10)">
              <Apple :size="16" />
              喂食
            </button>
            <button class="btn btn-outline" type="button" @click="pat">
              <Hand :size="16" />
              摸摸
            </button>
            <button class="btn btn-outline" type="button" @click="play">
              <Gamepad2 :size="16" />
              玩耍
            </button>
          </div>
        </div>

        <div class="card chat-card">
          <div class="chat-head">
            <MessageCircle :size="17" />
            <strong>{{ pet.name }}</strong>
            <span class="online-dot" />
          </div>
          <div ref="chatBodyRef" class="chat-body">
            <div v-if="!messages.length" class="chat-empty">
              和小智聊聊今天的学习吧
            </div>
            <div
              v-for="msg in messages"
              :key="msg.id"
              class="chat-line"
              :class="msg.role"
            >
              <div class="chat-bubble">{{ msg.content }}</div>
            </div>
            <div v-if="sending" class="chat-line assistant">
              <div class="chat-bubble">正在思考……</div>
            </div>
          </div>
          <form class="chat-form" @submit.prevent="sendMessage">
            <input
              v-model="chatInput"
              class="input"
              maxlength="500"
              :placeholder="`和${pet.name}聊聊今天的学习`"
            />
            <button
              class="btn btn-primary chat-send"
              type="submit"
              :disabled="sending || !chatInput.trim()"
            >
              <Send :size="16" />
            </button>
          </form>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.upgrade-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  padding: 48px 20px;
}

.upgrade-card h2 {
  margin: 0;
}

.digital-grid {
  grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
}

.stage-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.digital-stage {
  position: relative;
  min-height: 320px;
  display: grid;
  place-items: center;
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.pet-sprite {
  image-rendering: pixelated;
  animation: float 3.2s ease-in-out infinite;
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

.stage-badge {
  position: absolute;
  right: 12px;
  top: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 10px;
  color: var(--text-2);
  font-size: 12px;
  font-weight: 600;
}

.pet-name {
  margin: 0;
  text-align: center;
}

.stat-row {
  display: flex;
  justify-content: center;
  gap: 16px;
  color: var(--text-2);
  font-size: 13px;
  flex-wrap: wrap;
}

.actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.chat-card {
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.chat-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.online-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #16a34a;
  margin-left: auto;
}

.chat-body {
  flex: 1;
  min-height: 380px;
  max-height: 440px;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-empty {
  margin: auto;
  color: var(--text-2);
}

.chat-line {
  display: flex;
}

.chat-line.assistant {
  justify-content: flex-start;
}

.chat-line.user {
  justify-content: flex-end;
}

.chat-bubble {
  max-width: 82%;
  padding: 9px 12px;
  border-radius: 10px 10px 10px 2px;
  background: #eef3f8;
  color: var(--text);
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-line.user .chat-bubble {
  background: var(--primary);
  color: #fff;
  border-radius: 10px 10px 2px 10px;
}

.chat-form {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
}

.chat-send {
  width: 42px;
  padding: 0;
}

@media (max-width: 900px) {
  .digital-grid {
    grid-template-columns: 1fr;
  }
}
</style>
