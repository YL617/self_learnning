<template>
  <view class="page">
    <view v-if="!loggedIn" class="card">
      <text class="card-title">登录 / 注册</text>
      <view class="field">
        <text>邮箱或用户名</text>
        <input v-model="account" class="input" />
      </view>
      <view class="field">
        <text>密码</text>
        <input v-model="password" class="input" type="password" />
      </view>
      <button class="btn primary" @click="login">登录</button>
      <text v-if="message" class="message">{{ message }}</text>
    </view>

    <template v-else>
      <view class="card">
        <text class="card-title">{{ username }} 的学习空间</text>
        <view v-if="pet" class="pet">
          <text class="pet-name">{{ pet.name }} · Lv.{{ pet.level }}</text>
          <text class="muted">经验 {{ pet.exp }}/{{ pet.level * 100 }} · 心情 {{ pet.mood }}</text>
          <button class="btn teal" @click="feed">喂食 10 智学币</button>
        </view>
        <view class="balance">
          <text class="stat-value">{{ balance }}</text>
          <text class="stat-label">智学币余额</text>
        </view>
      </view>
      <button class="btn outline" @click="goOnboarding">完善学情</button>
      <button class="btn outline" @click="logout">退出登录</button>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import { api, clearToken, setToken } from "@/api/request";
import type { CoinTransaction, Pet } from "@/types";

const account = ref("");
const password = ref("");
const username = ref(uni.getStorageSync("ai_study_user") as string || "");
const loggedIn = ref(Boolean(username.value));
const pet = ref<Pet | null>(null);
const transactions = ref<CoinTransaction[]>([]);
const message = ref("");

const balance = computed(() =>
  transactions.value.reduce((sum, tx) => sum + tx.amount, 0),
);

async function login() {
  try {
    const result = await api.login(account.value, password.value);
    setToken(result.access_token);
    username.value = result.user.username;
    uni.setStorageSync("ai_study_user", username.value);
    loggedIn.value = true;
    await load();
  } catch (err: any) {
    message.value = err?.detail || "登录失败";
  }
}

async function load() {
  try {
    pet.value = await api.pet();
    transactions.value = await api.transactions();
  } catch {
    pet.value = null;
    transactions.value = [];
  }
}

async function feed() {
  if (!pet.value) return;
  pet.value = await api.feedPet(pet.value.id, 10);
  transactions.value = await api.transactions();
}

function logout() {
  clearToken();
  username.value = "";
  loggedIn.value = false;
  pet.value = null;
  transactions.value = [];
}

function goOnboarding() {
  uni.navigateTo({ url: "/pages/onboarding/onboarding" });
}
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

.card-title {
  font-size: 30rpx;
  font-weight: 700;
  display: block;
  margin-bottom: 20rpx;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  margin-bottom: 16rpx;
  color: #5b6b7a;
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

.btn.teal {
  background: #0f766e;
  color: #fff;
}

.btn.outline {
  border: 1px solid #dde3e8;
  color: #5b6b7a;
  background: #fff;
}

.message {
  display: block;
  margin-top: 12rpx;
  color: #dc2626;
  font-size: 24rpx;
}

.pet {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  margin-bottom: 20rpx;
}

.pet-name {
  font-size: 32rpx;
  font-weight: 700;
}

.muted {
  color: #5b6b7a;
  font-size: 24rpx;
}

.balance {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 44rpx;
  font-weight: 700;
}

.stat-label {
  color: #5b6b7a;
  font-size: 22rpx;
}
</style>
