<script setup lang="ts">
import { KeyRound, Plus } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import type { ActivationCode } from '@/types'

const codes = ref<ActivationCode[]>([])
const tier = ref('advanced')
const days = ref(30)
const count = ref(1)
const error = ref('')
const success = ref('')
const loading = ref(false)
const generating = ref(false)

const tierNames: Record<string, string> = {
  basic: '基础会员',
  advanced: '进阶会员',
  full: '完整会员',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await adminApi.activationCodes()
    codes.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function generate() {
  generating.value = true
  error.value = ''
  success.value = ''
  try {
    const { data } = await adminApi.createActivationCodes({
      tier: tier.value,
      days: days.value,
      count: count.value,
    })
    codes.value = [...data, ...codes.value]
    success.value = `已生成 ${data.length} 个激活码`
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '生成失败'
  } finally {
    generating.value = false
  }
}

async function revoke(code: ActivationCode) {
  error.value = ''
  try {
    const { data } = await adminApi.revokeActivationCode(code.id)
    Object.assign(code, data)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '撤销失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">激活码管理</h1>
        <p class="page-subtitle">生成、撤销并追踪闲鱼等渠道售出的激活码</p>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div class="card">
      <h2><Plus :size="16" style="vertical-align: -2px" /> 生成激活码</h2>
      <div class="form-grid">
        <div class="field">
          <span>会员档位</span>
          <select v-model="tier" class="select">
            <option value="basic">基础会员（10 元/月）</option>
            <option value="advanced">进阶会员（20 元/月）</option>
            <option value="full">完整会员（30 元/月）</option>
          </select>
        </div>
        <div class="field">
          <span>时长</span>
          <select v-model.number="days" class="select">
            <option :value="30">30 天</option>
            <option :value="90">90 天</option>
            <option :value="365">365 天</option>
          </select>
        </div>
        <div class="field">
          <span>数量</span>
          <input v-model.number="count" class="input" type="number" min="1" max="50" />
        </div>
      </div>
      <button
        class="btn btn-primary"
        type="button"
        style="margin-top: 12px"
        :disabled="generating"
        @click="generate"
      >
        <KeyRound :size="16" />
        生成激活码
      </button>
    </div>

    <div class="card">
      <h2><KeyRound :size="16" style="vertical-align: -2px" /> 激活码列表</h2>
      <div v-if="loading && !codes.length" class="empty">正在加载...</div>
      <div v-else-if="!codes.length" class="empty">还没有激活码</div>
      <div v-else class="table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>激活码</th>
              <th>档位</th>
              <th>时长</th>
              <th>状态</th>
              <th>使用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="code in codes" :key="code.id">
              <td><code>{{ code.code }}</code></td>
              <td>{{ tierNames[code.tier] || code.tier }}</td>
              <td>{{ code.days }} 天</td>
              <td>
                <span
                  class="badge"
                  :class="code.status === 'unused' ? 'badge-green' : 'badge-amber'"
                >
                  {{ code.status === 'unused' ? '未使用' : code.status === 'revoked' ? '已撤销' : '已使用' }}
                </span>
              </td>
              <td class="muted">{{ code.used_at ? code.used_at.slice(0, 10) : '—' }}</td>
              <td>
                <button
                  v-if="code.status === 'unused'"
                  class="btn btn-danger"
                  type="button"
                  @click="revoke(code)"
                >
                  撤销
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.text-success {
  color: #15803d;
}

.table-wrap {
  overflow-x: auto;
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  font-size: 13px;
}

.admin-table th,
.admin-table td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.admin-table th {
  background: #f8fafc;
  color: var(--text-2);
  font-weight: 600;
}
</style>
