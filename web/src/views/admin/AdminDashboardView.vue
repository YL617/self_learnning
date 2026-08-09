<script setup lang="ts">
import { Coins, FileQuestion, RefreshCw, Timer, Users } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import type { StatsOverview } from '@/types'

const stats = ref<StatsOverview | null>(null)
const error = ref('')
const loading = ref(false)

const snapshot = computed(() => stats.value?.ai_monitor?.snapshot || null)
const usage = computed(() => stats.value?.ai_monitor?.usage || [])
const maxTokens = computed(() =>
  Math.max(1, ...usage.value.map((row) => row.tokens)),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await adminApi.stats()
    stats.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function refreshMonitor() {
  error.value = ''
  try {
    const { data } = await adminApi.refreshAiMonitor()
    if (stats.value) stats.value.ai_monitor = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '刷新失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">运营看板</h1>
        <p class="page-subtitle">平台数据与 DeepSeek AI 服务状态</p>
      </div>
      <button class="btn btn-outline" type="button" @click="load">
        刷新数据
      </button>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <div v-if="loading && !stats" class="empty">正在加载数据...</div>

    <template v-if="stats">
      <div class="grid grid-4">
        <div class="card stat-card">
          <div class="stat-icon"><Users :size="22" /></div>
          <div>
            <div class="stat-value">{{ stats.user_count }}</div>
            <div class="stat-label">用户数 · 今日活跃 {{ stats.active_today }}</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon"><FileQuestion :size="22" /></div>
          <div>
            <div class="stat-value">{{ stats.question_count }}</div>
            <div class="stat-label">题目 · 错题 {{ stats.wrong_book_count }}</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon"><Timer :size="22" /></div>
          <div>
            <div class="stat-value">{{ stats.total_focus_minutes }}</div>
            <div class="stat-label">累计专注分钟</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon"><Coins :size="22" /></div>
          <div>
            <div class="stat-value">{{ stats.total_coins_issued }}</div>
            <div class="stat-label">智学币发放 · 计划 {{ stats.plan_count }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="row gap space-between">
          <h2>DeepSeek AI 服务</h2>
          <button class="btn btn-outline" type="button" @click="refreshMonitor">
            <RefreshCw :size="16" />
            立即刷新
          </button>
        </div>
        <div v-if="snapshot" class="ai-monitor">
          <div class="ai-balance">
            <span>总余额</span>
            <strong>¥{{ snapshot.total_balance }}</strong>
            <small>
              赠金 ¥{{ snapshot.granted_balance }} · 充值 ¥{{ snapshot.topped_up_balance }}
            </small>
          </div>
          <div class="ai-status">
            <span class="badge" :class="snapshot.status === 'ok' ? 'badge-green' : 'badge-amber'">
              {{ snapshot.status === 'ok' ? '可用' : '异常' }}
            </span>
            <span class="muted">最后检查 {{ snapshot.checked_at }}</span>
          </div>
        </div>
        <div v-if="stats?.ai_monitor?.is_low_balance" class="low-balance">
          DeepSeek 余额低于 ¥{{ stats.ai_monitor.low_balance_threshold }}，建议尽快充值
        </div>
        <p v-if="snapshot?.error_message" class="text-danger">{{ snapshot.error_message }}</p>
        <div v-if="usage.length" class="usage-table-wrap">
          <div class="usage-bars">
            <div
              v-for="row in usage.slice(0, 14)"
              :key="row.id"
              class="usage-bar"
              :style="{ height: `${Math.max(4, (row.tokens / maxTokens) * 80)}px` }"
              :title="`${row.usage_date} · ${row.tokens} tokens`"
            />
          </div>
          <table class="usage-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>Token</th>
                <th>费用</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in usage" :key="row.id">
                <td>{{ row.usage_date }}</td>
                <td>{{ row.tokens }}</td>
                <td>¥{{ row.cost.toFixed(4) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">暂无用量记录</div>
        <p class="muted" style="margin-top: 12px">
          通义千问 / 智谱 GLM 暂不支持官方余额查询，仅 DeepSeek 提供实时监控
        </p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.ai-monitor {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px 0;
}

.ai-balance {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ai-balance strong {
  font-size: 30px;
  line-height: 1.2;
}

.ai-balance small {
  color: var(--text-2);
}

.ai-status {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.low-balance {
  background: #fef2f2;
  color: var(--danger);
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 10px 14px;
  margin-top: 12px;
}

.usage-bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 90px;
  padding: 10px 0;
}

.usage-bar {
  flex: 1;
  min-width: 8px;
  background: var(--primary);
  border-radius: 4px 4px 0 0;
}

.usage-table-wrap {
  overflow-x: auto;
}

.usage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.usage-table th,
.usage-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}

.usage-table th {
  color: var(--text-2);
  font-weight: 600;
}
</style>
