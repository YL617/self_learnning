<script setup lang="ts">
import { Gamepad2, Home, X } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { usePetStore } from '@/stores/pet'

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

let animationTimer: number | undefined
let roamFrame: number | undefined
let countdownTimer: number | undefined
let speechTimer: number | undefined
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
  window.removeEventListener('resize', updateWidth)
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
      <div class="pet-sprite" :style="spriteStyle" />
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
          <template v-else-if="petSays">
            <div class="bubble-title">{{ pet?.name || '小智' }}</div>
            <div class="bubble-text">{{ petSays }}</div>
          </template>
          <template v-else>
            <div class="bubble-title">{{ pet?.name || '小智' }} · Lv.{{ pet?.level || 1 }}</div>
            <div class="bubble-text">
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
  width: 200px;
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
