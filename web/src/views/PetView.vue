<script setup lang="ts">
import { PawPrint, Wallet } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { focusApi } from '@/api/focus'
import type { CoinTransaction, Pet } from '@/types'

const pet = ref<Pet | null>(null)
const transactions = ref<CoinTransaction[]>([])
const newName = ref('')
const error = ref('')
const success = ref('')

const balance = computed(() =>
  transactions.value.reduce((sum, tx) => sum + tx.amount, 0),
)
const expPercent = computed(() => {
  if (!pet.value) return 0
  const threshold = pet.value.level * 100
  return Math.min(100, Math.round((pet.value.exp / threshold) * 100))
})

async function load() {
  error.value = ''
  try {
    const [petRes, coinRes] = await Promise.all([focusApi.pet(), focusApi.transactions()])
    pet.value = petRes.data
    transactions.value = coinRes.data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

async function rename() {
  if (!pet.value || !newName.value.trim()) return
  try {
    const { data } = await focusApi.renamePet(pet.value.id, newName.value.trim())
    pet.value = data
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
    pet.value = data
    success.value = `喂食成功，消耗 ${amount} 智学币`
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '喂食失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">我的宠物</h1>
        <p class="page-subtitle">完成任务积累经验，用智学币喂养成长伙伴</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" style="color: #15803d">{{ success }}</p>

    <div class="grid grid-3">
      <div class="card" style="grid-column: span 2">
        <template v-if="pet">
          <div class="row gap" style="justify-content: center; flex-direction: column">
            <div class="pet-visual"><PawPrint :size="52" /></div>
            <h2 style="text-align: center; margin: 4px 0 0">
              {{ pet.name }} · Lv.{{ pet.level }}
            </h2>
            <div class="muted" style="text-align: center">心情 {{ pet.mood }}/100</div>
            <div>
              <div class="progress-label">
                <span>经验</span>
                <span>{{ pet.exp }}/{{ pet.level * 100 }}</span>
              </div>
              <div class="progress-track">
                <div class="progress-bar" :style="{ width: `${expPercent}%` }" />
              </div>
            </div>
          </div>
          <div class="row gap wrap" style="margin-top: 16px; justify-content: center">
            <button class="btn btn-teal" type="button" @click="feed(10)">喂食 10 币</button>
            <button class="btn btn-teal" type="button" @click="feed(50)">喂食 50 币</button>
          </div>
          <div class="row gap" style="margin-top: 16px">
            <input v-model="newName" class="input" placeholder="输入新名字" />
            <button class="btn btn-outline" type="button" @click="rename">改名</button>
          </div>
        </template>
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
    </div>
  </section>
</template>
