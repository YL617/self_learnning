<script setup lang="ts">
import { Gamepad2, Home, Send, X } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { focusApi } from '@/api/focus'
import { useAuthStore } from '@/stores/auth'
import { usePetStore } from '@/stores/pet'
import type { PetMessage } from '@/types'
import { petEvents } from '@/utils/petEvents'

const SPRITE_URL = '/pets/airi/spritesheet.webp'
const CELL_WIDTH = 192
const CELL_HEIGHT = 208
const ATLAS_COLUMNS = 8
const ATLAS_ROWS = 9
const SCALE = 0.5
const MARGIN = 12
const POSITION_KEY = 'ai_pet_pos'
const HIDDEN_KEY = 'ai_pet_hidden'

type AnimationId =
  | 'idle'
  | 'running-right'
  | 'running-left'
  | 'waving'
  | 'jumping'
  | 'talking'
  | 'failed'
  | 'waiting'

const ANIMATIONS: Record<
  AnimationId,
  { row: number; durations: number[]; loop: boolean }
> = {
  idle: { row: 0, durations: [280, 110, 110, 140, 140, 320], loop: true },
  'running-right': {
    row: 1,
    durations: [120, 120, 120, 120, 120, 120, 120, 220],
    loop: true,
  },
  'running-left': {
    row: 2,
    durations: [120, 120, 120, 120, 120, 120, 120, 220],
    loop: true,
  },
  talking: {
    row: 0,
    durations: [95, 130, 95, 130, 95, 150],
    loop: true,
  },
  waving: { row: 3, durations: [140, 140, 140, 280], loop: false },
  jumping: { row: 4, durations: [140, 140, 140, 140, 280], loop: false },
  failed: { row: 5, durations: [140, 140, 140, 140, 140, 140, 140, 240], loop: true },
  waiting: { row: 6, durations: [150, 150, 150, 150, 150, 260], loop: true },
}

const auth = useAuthStore()
const petStore = usePetStore()
const position = ref({ x: 0, y: 0 })
const dragging = ref(false)
const moved = ref(false)
const bubbleOpen = ref(false)
const isWide = ref(true)
const hidden = ref(localStorage.getItem(HIDDEN_KEY) === '1')
const animation = ref<AnimationId>('idle')
const frame = ref(0)
const direction = ref<'left' | 'right'>('right')
const petSays = ref('')
const countdown = ref(0)
const chatMessages = ref<PetMessage[]>([])
const chatInput = ref('')
const chatSending = ref(false)
const chatLoading = ref(false)
const chatError = ref('')

let animationTimer: number | undefined
let roamFrame: number | undefined
let countdownTimer: number | undefined
let speechTimer: number | undefined
let talkTimer: number | undefined
let unsubscribeEvents: (() => void) | undefined
let dragOffset = { x: 0, y: 0 }
let dragStart = { x: 0, y: 0 }

const pet = computed(() => petStore.pet)
const visible = computed(
  () =>
    auth.isLoggedIn &&
    Boolean(petStore.pet) &&
    (petStore.isPlaying || (isWide.value && !hidden.value)),
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

function clampX(value: number) {
  const maxX = window.innerWidth - CELL_WIDTH * SCALE - MARGIN
  return Math.max(MARGIN, Math.min(value, maxX))
}

function clampY(value: number) {
  const maxY = window.innerHeight - CELL_HEIGHT * SCALE - MARGIN
  return Math.max(MARGIN, Math.min(value, maxY))
}

function loadPosition() {
  try {
    const saved = JSON.parse(localStorage.getItem(POSITION_KEY) || 'null')
    if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
      position.value = { x: saved.x, y: saved.y }
    }
  } catch {
    // 使用默认位置
  }
  position.value = {
    x: clampX(position.value.x || window.innerWidth - 150),
    y: clampY(position.value.y || window.innerHeight - 220),
  }
}

function savePosition() {
  localStorage.setItem(POSITION_KEY, JSON.stringify(position.value))
}

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
      } else if (petStore.isPlaying) {
        runAnimation(
          direction.value === 'left' ? 'running-left' : 'running-right',
        )
      } else {
        runAnimation('idle')
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
}

function startRoaming() {
  if (roamFrame !== undefined) {
    cancelAnimationFrame(roamFrame)
  }
  direction.value = position.value.x > window.innerWidth / 2 ? 'left' : 'right'
  runAnimation(direction.value === 'left' ? 'running-left' : 'running-right')
  const step = () => {
    if (!petStore.isPlaying || dragging.value) {
      roamFrame = undefined
      return
    }
    const maxX = window.innerWidth - CELL_WIDTH * SCALE - MARGIN
    if (position.value.x <= MARGIN) {
      position.value.x = MARGIN
      direction.value = 'right'
      runAnimation('running-right')
    } else if (position.value.x >= maxX) {
      position.value.x = maxX
      direction.value = 'left'
      runAnimation('running-left')
    }
    position.value.x = clampX(
      position.value.x + (direction.value === 'left' ? -1 : 1) * 1.1,
    )
    if (Math.random() < 0.003) {
      direction.value = animation.value === 'running-left' ? 'left' : 'right'
      runAnimation('jumping')
    }
    roamFrame = requestAnimationFrame(step)
  }
  roamFrame = requestAnimationFrame(step)
}

function stopRoaming() {
  if (roamFrame !== undefined) {
    cancelAnimationFrame(roamFrame)
    roamFrame = undefined
  }
}

function tickCountdown() {
  countdown.value = petStore.remainingSeconds
  if (countdown.value <= 0 && petStore.isPlaying) {
    stopCountdown()
    void petStore.endPlay()
  }
}

function startCountdown() {
  stopCountdown()
  tickCountdown()
  countdownTimer = window.setInterval(tickCountdown, 1000)
}

function stopCountdown() {
  if (countdownTimer !== undefined) {
    window.clearInterval(countdownTimer)
    countdownTimer = undefined
  }
}

function formatCountdown() {
  const total = Math.max(0, countdown.value)
  const minutes = Math.floor(total / 60).toString().padStart(2, '0')
  const seconds = (total % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
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

function onPointerDown(event: PointerEvent) {
  dragging.value = true
  moved.value = false
  dragStart = { x: event.clientX, y: event.clientY }
  dragOffset = { x: event.clientX - position.value.x, y: event.clientY - position.value.y }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  stopRoaming()
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return
  if (
    Math.abs(event.clientX - dragStart.x) > 5 ||
    Math.abs(event.clientY - dragStart.y) > 5
  ) {
    moved.value = true
  }
  if (moved.value) {
    position.value = {
      x: clampX(event.clientX - dragOffset.x),
      y: clampY(event.clientY - dragOffset.y),
    }
  }
}

function onPointerUp() {
  dragging.value = false
  if (moved.value) {
    savePosition()
  }
  if (petStore.isPlaying) {
    startRoaming()
  }
}

function onClickPet() {
  if (moved.value) return
  bubbleOpen.value = !bubbleOpen.value
  if (bubbleOpen.value && !petStore.isPlaying) {
    void openChat()
  }
}

async function openChat() {
  if (!petStore.pet || chatMessages.value.length) return
  chatLoading.value = true
  chatError.value = ''
  try {
    const { data } = await focusApi.petMessages(petStore.pet.id)
    chatMessages.value = data
  } catch (err: any) {
    chatError.value = err?.response?.data?.detail || '聊天加载失败'
  } finally {
    chatLoading.value = false
  }
}

async function sendChat() {
  const text = chatInput.value.trim()
  if (!petStore.pet || !text || chatSending.value) return
  chatSending.value = true
  chatError.value = ''
  try {
    const { data } = await focusApi.chatPet(petStore.pet.id, text)
    petStore.applyPet(data.pet)
    chatMessages.value = data.messages
    chatInput.value = ''
  } catch (err: any) {
    chatError.value = err?.response?.data?.detail || '发送失败'
  } finally {
    chatSending.value = false
  }
}

function handlePetEvent(event: { kind: 'focus' | 'plan' | 'wrong-book' }) {
  if (hidden.value) return
  stopTalking()
  runAnimation('talking')
  talkTimer = window.setTimeout(afterTalking, 2600)
}

function stopTalking() {
  if (talkTimer !== undefined) {
    window.clearTimeout(talkTimer)
    talkTimer = undefined
  }
}

function afterTalking() {
  talkTimer = undefined
  if (petStore.isPlaying) {
    runAnimation(direction.value === 'left' ? 'running-left' : 'running-right')
  } else {
    runAnimation('idle')
  }
}

function hidePet() {
  hidden.value = true
  localStorage.setItem(HIDDEN_KEY, '1')
  bubbleOpen.value = false
}

async function endPlay() {
  bubbleOpen.value = false
  const data = await petStore.endPlay()
  if (data?.summary) {
    showPetSays(data.summary.message)
  }
  stopRoaming()
  runAnimation('idle')
}

function updateWidth() {
  isWide.value = window.innerWidth >= 1024
  position.value = {
    x: clampX(position.value.x),
    y: clampY(position.value.y),
  }
}

watch(
  () => petStore.isPlaying,
  (playing) => {
    if (playing) {
      startCountdown()
      startRoaming()
      bubbleOpen.value = true
    } else {
      stopCountdown()
      stopRoaming()
      stopTalking()
      bubbleOpen.value = false
      runAnimation('idle')
    }
  },
)

watch(
  () => auth.isLoggedIn,
  (loggedIn) => {
    if (!loggedIn) {
      stopRoaming()
      stopCountdown()
      petStore.reset()
      bubbleOpen.value = false
    }
  },
)

onMounted(async () => {
  loadPosition()
  updateWidth()
  window.addEventListener('resize', updateWidth)
  unsubscribeEvents = petEvents.on(handlePetEvent)
  if (auth.isLoggedIn) {
    try {
      await petStore.loadPet()
      await petStore.syncPlayState()
      if (petStore.isPlaying) {
        startCountdown()
        startRoaming()
        bubbleOpen.value = true
      } else {
        runAnimation('idle')
      }
      if (petStore.summary) {
        showPetSays(petStore.summary.message)
        petStore.clearSummary()
      }
    } catch {
      runAnimation('idle')
    }
  }
})

onBeforeUnmount(() => {
  stopAnimation()
  stopRoaming()
  stopCountdown()
  stopTalking()
  window.removeEventListener('resize', updateWidth)
  if (unsubscribeEvents) {
    unsubscribeEvents()
  }
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="pet-floater"
      :class="{ dragging }"
      :style="{ left: `${position.x}px`, top: `${position.y}px` }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @click="onClickPet"
    >
      <div
        class="pet-sprite"
        :class="{ talking: animation === 'talking' }"
        :data-state="animation"
        :style="spriteStyle"
      />
      <button
        v-if="!petStore.isPlaying"
        class="hide-btn"
        type="button"
        aria-label="隐藏宠物"
        @click.stop="hidePet"
      >
        <X :size="14" />
      </button>
      <transition name="pop">
        <div v-if="bubbleOpen || petStore.isPlaying" class="bubble">
          <template v-if="petStore.isPlaying">
            <div class="bubble-title">
              <Gamepad2 :size="14" />
              {{ pet?.name || '小智' }} 出门玩中
            </div>
            <div class="countdown">{{ formatCountdown() }}</div>
            <button class="btn btn-outline" type="button" @click.stop="endPlay">
              <Home :size="14" />
              回家
            </button>
          </template>
          <template v-else>
            <div class="chat-head-row">
              <div class="bubble-title">
                {{ pet?.name || '小智' }} · Lv.{{ pet?.level || 1 }}
              </div>
              <button
                class="bubble-close"
                type="button"
                aria-label="关闭"
                @click.stop="bubbleOpen = false"
              >
                <X :size="14" />
              </button>
            </div>
            <div v-if="petSays" class="bubble-text pet-says">{{ petSays }}</div>
            <div v-if="chatError" class="chat-error">{{ chatError }}</div>
            <div class="chat-messages">
              <div v-if="chatLoading" class="chat-hint">正在思考……</div>
              <div v-else-if="!chatMessages.length" class="chat-hint">
                先打个招呼吧
              </div>
              <div
                v-for="msg in chatMessages"
                :key="msg.id"
                class="msg-line"
                :class="msg.role"
              >
                <span>{{ msg.content }}</span>
              </div>
              <div v-if="chatSending" class="msg-line assistant">
                <span>正在思考……</span>
              </div>
            </div>
            <form class="chat-form" @submit.prevent="sendChat">
              <input
                v-model="chatInput"
                maxlength="500"
                :placeholder="`和${pet?.name || '小智'}聊聊学习`"
              />
              <button
                class="send-btn"
                type="submit"
                :disabled="chatSending || !chatInput.trim()"
              >
                <Send :size="14" />
              </button>
            </form>
            <div class="bubble-text stat-line">
              心情 {{ pet?.mood || 0 }} · 饱食度 {{ pet?.hunger || 0 }}
            </div>
          </template>
        </div>
      </transition>
    </div>
  </Teleport>
</template>

<style scoped>
.pet-floater {
  position: fixed;
  z-index: 900;
  width: 96px;
  height: 104px;
  cursor: grab;
  touch-action: none;
  user-select: none;
}

.pet-floater.dragging {
  cursor: grabbing;
}

.pet-sprite {
  image-rendering: pixelated;
  display: block;
  pointer-events: none;
}

.pet-sprite.talking {
  animation: talk-bob 0.45s ease-in-out infinite;
}

@keyframes talk-bob {
  0%,
  100% {
    transform: translateY(0) scale(1);
  }
  50% {
    transform: translateY(-4px) scale(1.04);
  }
}

.hide-btn {
  position: absolute;
  right: -6px;
  top: -6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text-2);
  display: grid;
  place-items: center;
  cursor: pointer;
  box-shadow: var(--shadow);
}

.bubble {
  position: absolute;
  left: 50%;
  bottom: 108px;
  transform: translateX(-50%);
  width: 280px;
  max-height: 340px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px 8px 8px 2px;
  padding: 10px 12px;
  box-shadow: 0 8px 24px rgba(16, 24, 40, 0.14);
}

.bubble-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 6px;
}

.bubble-text {
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.5;
}

.countdown {
  font-size: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-bottom: 8px;
}

.bubble .btn {
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
}

.chat-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.chat-head-row .bubble-title {
  margin-bottom: 0;
}

.bubble-close {
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--text-2);
  display: grid;
  place-items: center;
  cursor: pointer;
  border-radius: 50%;
}

.bubble-close:hover {
  background: #f1f5f9;
}

.pet-says {
  margin: 8px 0;
  padding: 6px 9px;
  background: #f8fafc;
  border-radius: 6px;
}

.chat-error {
  margin: 6px 0;
  color: var(--danger);
  font-size: 12px;
}

.chat-messages {
  max-height: 180px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 8px 0;
}

.chat-hint {
  color: var(--text-2);
  font-size: 12px;
  text-align: center;
  padding: 8px 0;
}

.msg-line {
  display: flex;
}

.msg-line.assistant {
  justify-content: flex-start;
}

.msg-line.user {
  justify-content: flex-end;
}

.msg-line span {
  max-width: 82%;
  padding: 5px 8px;
  border-radius: 8px 8px 8px 2px;
  background: #eef3f8;
  color: var(--text);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-line.user span {
  background: var(--primary);
  color: #fff;
  border-radius: 8px 8px 2px 8px;
}

.chat-form {
  display: flex;
  gap: 6px;
}

.chat-form input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--text);
}

.send-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: var(--primary);
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.send-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.stat-line {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.pop-enter-active,
.pop-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}
</style>
