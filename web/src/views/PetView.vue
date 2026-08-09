<script setup lang="ts">
import {
  Apple,
  Gamepad2,
  Hand,
  HeartHandshake,
  Home,
  MessageCircle,
  PawPrint,
  Send,
  Sparkles,
  Wallet,
} from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { focusApi } from '@/api/focus'
import { usePetStore } from '@/stores/pet'
import type { CoinTransaction, Pet, PetMessage } from '@/types'

const SPRITE_URL = '/pets/airi/spritesheet.webp'
const CELL_WIDTH = 192
const CELL_HEIGHT = 208
const ATLAS_COLUMNS = 8
const ATLAS_ROWS = 9
const SCALE = 0.82

type AnimationId = 'idle' | 'waving' | 'jumping' | 'failed' | 'waiting'

const ANIMATIONS: Record<
  AnimationId,
  { row: number; durations: number[]; loop: boolean }
> = {
  idle: { row: 0, durations: [280, 110, 110, 140, 140, 320], loop: true },
  waving: { row: 3, durations: [140, 140, 140, 280], loop: false },
  jumping: { row: 4, durations: [140, 140, 140, 140, 280], loop: false },
  failed: { row: 5, durations: [140, 140, 140, 140, 140, 140, 140, 240], loop: true },
  waiting: { row: 6, durations: [150, 150, 150, 150, 150, 260], loop: true },
}

const petStore = usePetStore()
const pet = computed(() => petStore.pet)
const transactions = ref<CoinTransaction[]>([])
const messages = ref<PetMessage[]>([])
const newName = ref('')
const chatInput = ref('')
const error = ref('')
const success = ref('')
const sending = ref(false)
const loadingChat = ref(false)
const petSays = ref('')
const animation = ref<AnimationId>('idle')
const frame = ref(0)
const countdown = ref(0)
const chatBodyRef = ref<HTMLElement | null>(null)
let animationTimer: number | undefined
let speechTimer: number | undefined
let countdownTimer: number | undefined

const balance = computed(() =>
  transactions.value.reduce((sum, tx) => sum + tx.amount, 0),
)
const expPercent = computed(() => {
  if (!pet.value) return 0
  const threshold = pet.value.level * 100
  return Math.min(100, Math.round((pet.value.exp / threshold) * 100))
})
const hungerPercent = computed(() => {
  if (!pet.value) return 0
  return Math.min(100, pet.value.hunger)
})
const moodPercent = computed(() => {
  if (!pet.value) return 0
  return Math.min(100, pet.value.mood)
})
const dailyLimitReached = computed(
  () => (pet.value?.play_count_today ?? 0) >= 5,
)
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
  if (animationTimer !== undefined) {
    window.clearTimeout(animationTimer)
  }
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

function stopAnimation() {
  if (animationTimer !== undefined) {
    window.clearTimeout(animationTimer)
  }
  if (speechTimer !== undefined) {
    window.clearTimeout(speechTimer)
  }
  if (countdownTimer !== undefined) {
    window.clearInterval(countdownTimer)
  }
}

function showPetSays(text: string) {
  petSays.value = text
  if (speechTimer !== undefined) {
    window.clearTimeout(speechTimer)
  }
  speechTimer = window.setTimeout(() => {
    petSays.value = ''
  }, 4200)
}

function stopCountdown() {
  if (countdownTimer !== undefined) {
    window.clearInterval(countdownTimer)
    countdownTimer = undefined
  }
}

function tickCountdown() {
  countdown.value = petStore.remainingSeconds
  if (countdown.value <= 0 && petStore.isPlaying) {
    stopCountdown()
    void endOuting()
  }
}

function startCountdown() {
  stopCountdown()
  tickCountdown()
  countdownTimer = window.setInterval(tickCountdown, 1000)
}

function formatCountdown() {
  const total = Math.max(0, countdown.value)
  const minutes = Math.floor(total / 60).toString().padStart(2, '0')
  const seconds = (total % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
}

async function scrollChat() {
  await nextTick()
  if (chatBodyRef.value) {
    chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight
  }
}

async function loadTransactions() {
  const { data } = await focusApi.transactions()
  transactions.value = data
}

async function greet() {
  if (!pet.value) return
  loadingChat.value = true
  try {
    const { data } = await focusApi.greetPet(pet.value.id)
    petStore.applyPet(data.pet)
    messages.value = data.messages
    await scrollChat()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '问候生成失败'
  } finally {
    loadingChat.value = false
  }
}

async function loadChat() {
  if (!pet.value) return
  loadingChat.value = true
  try {
    const { data } = await focusApi.petMessages(pet.value.id)
    messages.value = data
    if (!data.length) {
      await greet()
    }
    await scrollChat()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '聊天记录加载失败'
  } finally {
    loadingChat.value = false
  }
}

async function load() {
  error.value = ''
  try {
    const [coinRes] = await Promise.all([
      focusApi.transactions(),
      petStore.loadPet(),
    ])
    transactions.value = coinRes.data
    await petStore.syncPlayState()
    if (petStore.summary) {
      const summary = petStore.summary
      success.value =
        `${summary.message} 心情 +${summary.mood_gain}，` +
        `经验 +${summary.exp_gain}，饱食度 -${summary.hunger_loss}`
      showPetSays(summary.message)
      petStore.clearSummary()
    }
    if (petStore.isPlaying) {
      startCountdown()
    }
    runAnimation(pet.value?.runaway ? 'waiting' : 'idle')
    await loadChat()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function rename() {
  if (!pet.value || !newName.value.trim()) return
  try {
    const { data } = await focusApi.renamePet(pet.value.id, newName.value.trim())
    petStore.applyPet(data)
    newName.value = ''
    success.value = '改名成功'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '改名失败'
  }
}

async function feed(amount: number) {
  if (!pet.value) return
  try {
    const { data } = await focusApi.feedPet(pet.value.id, amount)
    petStore.applyPet(data)
    success.value = `喂食成功，消耗 ${amount} 智学币`
    showPetSays(data.runaway ? '吃饱啦，我回来啦！' : '好吃，能量满满！')
    runAnimation(data.runaway ? 'waiting' : 'jumping')
    await loadTransactions()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '喂食失败'
  }
}

async function pat() {
  if (!pet.value) return
  try {
    const { data } = await focusApi.patPet(pet.value.id)
    petStore.applyPet(data.pet)
    showPetSays(data.reply)
    runAnimation('waving')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '互动失败'
  }
}

async function play() {
  if (!pet.value) return
  try {
    const { data } = await focusApi.playPet(pet.value.id)
    petStore.applyPet(data.pet)
    showPetSays(data.reply)
    runAnimation('jumping')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '互动失败'
  }
}

async function revive() {
  if (!pet.value) return
  try {
    const { data } = await focusApi.revivePet(pet.value.id)
    petStore.applyPet(data.pet)
    showPetSays(data.reply)
    runAnimation('jumping')
    await loadTransactions()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '找回失败'
  }
}

async function startOuting() {
  if (!pet.value) return
  try {
    const data = await petStore.startPlay()
    if (data?.session) {
      success.value = '小智出门玩啦，记得 15 分钟后回来'
      showPetSays('出门玩啦！')
      runAnimation('jumping')
      startCountdown()
      await loadTransactions()
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '出门失败'
  }
}

async function endOuting() {
  if (!petStore.isPlaying) return
  try {
    const data = await petStore.endPlay()
    stopCountdown()
    if (data?.summary) {
      const summary = data.summary
      success.value =
        `${summary.message} 心情 +${summary.mood_gain}，` +
        `经验 +${summary.exp_gain}，饱食度 -${summary.hunger_loss}`
      showPetSays(summary.message)
      runAnimation('jumping')
    }
    await loadTransactions()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '回家失败'
  }
}

async function sendMessage() {
  const text = chatInput.value.trim()
  if (!pet.value || !text || sending.value) return
  sending.value = true
  error.value = ''
  try {
    const { data } = await focusApi.chatPet(pet.value.id, text)
    petStore.applyPet(data.pet)
    messages.value = data.messages
    chatInput.value = ''
    runAnimation('idle')
    await scrollChat()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '发送失败'
  } finally {
    sending.value = false
  }
}

onMounted(load)
onBeforeUnmount(stopAnimation)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">AI 宠物</h1>
        <p class="page-subtitle">
          {{ pet?.name || '小智' }} 会记住你的学习节奏，陪你完成每一天的计划
        </p>
      </div>
      <div class="row gap wrap">
        <span class="badge badge-teal">
          <Sparkles :size="13" />
          AI 学习伙伴
        </span>
        <span class="badge">
          <PawPrint :size="13" />
          Lv.{{ pet?.level || 1 }}
        </span>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div class="grid grid-2 pet-grid">
      <div class="card pet-panel">
        <div class="pet-stage" :class="`stage-${pet?.evolution_stage || 1}`">
          <div class="pet-sprite" :style="spriteStyle" />
          <transition name="pop">
            <div v-if="petSays" class="speech-bubble">{{ petSays }}</div>
          </transition>
          <span class="stage-badge">第 {{ pet?.evolution_stage || 1 }} 阶段</span>
        </div>

        <h2 class="pet-name">{{ pet?.name || '小智' }} · Lv.{{ pet?.level || 1 }}</h2>
        <div v-if="pet?.runaway" class="badge badge-amber" style="margin: 0 auto">
          离家出走，请使用寻回卷轴
        </div>

        <div class="stat-list">
          <div>
            <div class="progress-label">
              <span>经验</span>
              <span>{{ pet?.exp || 0 }}/{{ (pet?.level || 1) * 100 }}</span>
            </div>
            <div class="progress-track">
              <div
                class="progress-bar"
                :style="{ width: `${expPercent}%` }"
              />
            </div>
          </div>
          <div>
            <div class="progress-label">
              <span>心情</span>
              <span>{{ pet?.mood || 0 }}/100</span>
            </div>
            <div class="progress-track">
              <div
                class="progress-bar mood"
                :style="{ width: `${moodPercent}%` }"
              />
            </div>
          </div>
          <div>
            <div class="progress-label">
              <span>饱食度</span>
              <span>{{ pet?.hunger || 0 }}/100</span>
            </div>
            <div class="progress-track">
              <div
                class="progress-bar hunger"
                :style="{ width: `${hungerPercent}%` }"
              />
            </div>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-teal" type="button" @click="feed(10)">
            <Apple :size="16" />
            普通饲料
          </button>
          <button class="btn btn-teal" type="button" @click="feed(50)">
            <Sparkles :size="16" />
            高级营养
          </button>
          <button class="btn btn-outline" type="button" @click="pat">
            <Hand :size="16" />
            摸摸
          </button>
          <button class="btn btn-outline" type="button" @click="play">
            <Gamepad2 :size="16" />
            玩耍
          </button>
          <button
            v-if="pet?.runaway"
            class="btn btn-danger"
            type="button"
            @click="revive"
          >
            <HeartHandshake :size="16" />
            寻回
          </button>
        </div>

        <div class="play-row">
          <template v-if="petStore.isPlaying">
            <span class="badge badge-teal">
              <Gamepad2 :size="13" />
              出门玩中 · {{ formatCountdown() }}
            </span>
            <button class="btn btn-outline" type="button" @click="endOuting">
              <Home :size="16" />
              回家
            </button>
          </template>
          <template v-else>
            <button
              class="btn btn-outline"
              type="button"
              :disabled="dailyLimitReached || !pet"
              @click="startOuting"
            >
              <Gamepad2 :size="16" />
              出门玩（20 币）
            </button>
            <span v-if="dailyLimitReached" class="badge badge-amber">
              今日次数已用完
            </span>
          </template>
        </div>

        <div class="rename-row">
          <input
            v-model="newName"
            class="input"
            maxlength="64"
            placeholder="输入新名字"
          />
          <button class="btn btn-ghost" type="button" @click="rename">
            <PawPrint :size="16" />
            改名
          </button>
        </div>
      </div>

      <div class="card chat-panel">
        <div class="chat-head">
          <MessageCircle :size="17" />
          <strong>{{ pet?.name || '小智' }}</strong>
          <span class="online-dot" />
        </div>
        <div ref="chatBodyRef" class="chat-body">
          <div v-if="loadingChat && !messages.length" class="chat-empty">
            正在思考……
          </div>
          <div v-else-if="!messages.length" class="chat-empty">
            还没有聊过，先打个招呼吧
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
            <div class="chat-bubble typing">正在思考……</div>
          </div>
        </div>
        <form class="chat-form" @submit.prevent="sendMessage">
          <input
            v-model="chatInput"
            class="input"
            maxlength="500"
            :placeholder="`和${pet?.name || '小智'}聊聊今天的学习`"
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

    <div class="card">
      <h2><Wallet :size="16" style="vertical-align: -2px" /> 智学币账本</h2>
      <div class="stat-card" style="margin-bottom: 14px">
        <div class="stat-icon"><Wallet :size="20" /></div>
        <div>
          <div class="stat-value">{{ balance }}</div>
          <div class="stat-label">当前余额</div>
        </div>
      </div>
      <div v-if="!transactions.length" class="empty">暂无收支记录</div>
      <div v-else class="list">
        <div v-for="tx in transactions.slice(0, 10)" :key="tx.id" class="list-item">
          <div class="list-item-main">
            <div class="list-item-title">{{ tx.reason }}</div>
            <div class="list-item-sub">{{ tx.created_at }}</div>
          </div>
          <span :class="tx.amount >= 0 ? 'badge badge-green' : 'badge badge-amber'">
            {{ tx.amount >= 0 ? '+' : '' }}{{ tx.amount }}
          </span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pet-grid {
  grid-template-columns: minmax(300px, 0.85fr) minmax(0, 1.15fr);
}

.pet-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pet-stage {
  position: relative;
  min-height: 260px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #f8fafc;
  overflow: hidden;
}

.pet-sprite {
  image-rendering: pixelated;
  display: block;
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

.stage-1 .pet-sprite {
  filter: drop-shadow(0 0 18px rgba(37, 99, 235, 0.28));
}

.stage-2 .pet-sprite {
  filter: drop-shadow(0 0 20px rgba(13, 148, 136, 0.34));
}

.stage-3 .pet-sprite {
  filter: drop-shadow(0 0 22px rgba(147, 51, 234, 0.3));
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

.speech-bubble {
  position: absolute;
  left: 12px;
  top: 12px;
  max-width: 220px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px 8px 8px 2px;
  padding: 8px 11px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.5;
  box-shadow: var(--shadow);
}

.pop-enter-active,
.pop-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

.pet-name {
  margin: 0;
  text-align: center;
  font-size: 20px;
}

.stat-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.progress-label {
  display: flex;
  justify-content: space-between;
  color: var(--text-2);
  font-size: 13px;
  margin-bottom: 4px;
}

.progress-track {
  height: 8px;
  border-radius: 999px;
  background: #edf1f5;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  border-radius: 999px;
  background: var(--primary);
  transition: width 0.3s ease;
}

.progress-bar.mood {
  background: #d97706;
}

.progress-bar.hunger {
  background: var(--teal);
}

.actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.actions .btn {
  padding: 8px 6px;
  font-size: 13px;
}

.play-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.rename-row {
  display: flex;
  gap: 8px;
}

.rename-row .input {
  flex: 1;
  min-width: 0;
}

.chat-panel {
  display: flex;
  flex-direction: column;
  min-height: 520px;
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
  font-size: 13px;
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
  border-radius: 10px 10px 10px 2px;
  padding: 9px 12px;
  background: #eef3f8;
  color: var(--text);
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-line.user .chat-bubble {
  border-radius: 10px 10px 2px 10px;
  background: var(--primary);
  color: #fff;
}

.chat-line.assistant .chat-bubble {
  border: 1px solid var(--border);
}

.typing {
  color: var(--text-2);
}

.chat-form {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  background: #fbfcfd;
}

.chat-form .input {
  flex: 1;
  min-width: 0;
}

.chat-send {
  width: 42px;
  padding: 0;
  flex-shrink: 0;
}

.text-success {
  color: #15803d;
}

@media (max-width: 900px) {
  .actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pet-grid {
    grid-template-columns: 1fr;
  }
}
</style>
