<template>
  <view class="page">
    <view class="card center">
      <text class="timer">{{ displayTime }}</text>
      <view v-if="!active" class="row">
        <view class="field half">
          <text>任务</text>
          <input v-model="taskLabel" class="input" />
        </view>
        <view class="field half">
          <text>分钟</text>
          <picker :range="durations" @change="onDurationChange">
            <view class="input">{{ duration }} 分钟</view>
          </picker>
        </view>
      </view>
      <button v-if="!active" class="btn primary" @click="start">开始专注</button>
      <button v-else class="btn danger" @click="complete">完成并记录</button>
      <text v-if="message" class="message">{{ message }}</text>
    </view>

    <view class="card">
      <text class="card-title">今日统计</text>
      <view class="stat-row">
        <view class="stat-item">
          <text class="stat-value">{{ stats.today_minutes }}</text>
          <text class="stat-label">今日分钟</text>
        </view>
        <view class="stat-item">
          <text class="stat-value">{{ stats.total_minutes }}</text>
          <text class="stat-label">累计分钟</text>
        </view>
        <view class="stat-item">
          <text class="stat-value">{{ stats.session_count }}</text>
          <text class="stat-label">完成次数</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";

import { api } from "@/api/request";
import type { FocusStats } from "@/types";

const durations = [25, 45, 60, 90];
const taskLabel = ref("专注学习");
const duration = ref(25);
const active = ref(false);
const sessionId = ref(0);
const remaining = ref(0);
const timerHandle = ref<number | null>(null);
const stats = ref<FocusStats>({ total_minutes: 0, session_count: 0, today_minutes: 0 });
const message = ref("");

const displayTime = computed(() => {
  const minutes = Math.floor(remaining.value / 60);
  const seconds = remaining.value % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
});

function onDurationChange(event: { detail: { value: string } }) {
  duration.value = durations[Number(event.detail.value)];
}

async function loadStats() {
  try {
    stats.value = await api.stats();
  } catch {
    stats.value = { total_minutes: 0, session_count: 0, today_minutes: 0 };
  }
}

async function start() {
  const session = await api.startFocus(taskLabel.value, duration.value);
  sessionId.value = session.id;
  remaining.value = duration.value * 60;
  active.value = true;
  timerHandle.value = setInterval(() => {
    remaining.value -= 1;
    if (remaining.value <= 0) complete();
  }, 1000);
}

async function complete() {
  if (timerHandle.value !== null) clearInterval(timerHandle.value);
  timerHandle.value = null;
  try {
    await api.completeFocus(sessionId.value);
    message.value = "已完成并记录";
    await loadStats();
  } catch (err: any) {
    message.value = err?.detail || "记录失败";
  } finally {
    active.value = false;
  }
}

onBeforeUnmount(() => {
  if (timerHandle.value !== null) clearInterval(timerHandle.value);
});

loadStats();
</script>

<style scoped>
.page {
  padding: 20rpx;
}

.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;
}

.center {
  text-align: center;
}

.timer {
  display: block;
  font-size: 96rpx;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-bottom: 20rpx;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  color: #5b6b7a;
  text-align: left;
}

.half {
  flex: 1;
}

.row {
  display: flex;
  gap: 16rpx;
  margin-bottom: 16rpx;
}

.input {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 14rpx;
  font-size: 26rpx;
}

.btn {
  width: 100%;
  border-radius: 12rpx;
  padding: 16rpx;
  font-size: 28rpx;
  font-weight: 600;
}

.btn.primary {
  background: #2563eb;
  color: #fff;
}

.btn.danger {
  background: #fee2e2;
  color: #dc2626;
}

.message {
  display: block;
  margin-top: 12rpx;
  color: #15803d;
  font-size: 24rpx;
}

.card-title {
  font-size: 30rpx;
  font-weight: 700;
  display: block;
  margin-bottom: 20rpx;
}

.stat-row {
  display: flex;
  gap: 16rpx;
}

.stat-item {
  flex: 1;
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 40rpx;
  font-weight: 700;
}

.stat-label {
  color: #5b6b7a;
  font-size: 22rpx;
}
</style>
