<template>
  <view class="page">
    <view v-if="pet" class="card pet-card">
      <view class="pet-stage">
        <image
          class="pet-image"
          src="/static/pets/airi/airi-idle.png"
          mode="aspectFit"
          :class="{ jumping: jumping }"
        />
        <view v-if="petSays" class="speech">{{ petSays }}</view>
        <text class="stage-badge">第 {{ pet.evolution_stage }} 阶段</text>
      </view>
      <text class="pet-name">{{ pet.name }} · Lv.{{ pet.level }}</text>
      <text v-if="pet.runaway" class="muted danger">离家出走，请使用寻回卷轴</text>
      <view class="stat">
        <text>经验 {{ pet.exp }}/{{ pet.level * 100 }}</text>
        <view class="track">
          <view class="bar primary" :style="{ width: `${expPercent}%` }" />
        </view>
      </view>
      <view class="stat">
        <text>心情 {{ pet.mood }}/100</text>
        <view class="track">
          <view class="bar mood" :style="{ width: `${moodPercent}%` }" />
        </view>
      </view>
      <view class="stat">
        <text>饱食度 {{ pet.hunger }}/100</text>
        <view class="track">
          <view class="bar hunger" :style="{ width: `${hungerPercent}%` }" />
        </view>
      </view>
      <view class="actions">
        <button class="btn teal small" @click="feed(10)">喂食 10</button>
        <button class="btn teal small" @click="feed(50)">喂食 50</button>
        <button class="btn outline small" @click="pat">摸摸</button>
        <button class="btn outline small" @click="play">玩耍</button>
        <button v-if="pet.runaway" class="btn danger small" @click="revive">
          寻回
        </button>
      </view>
    </view>

    <view class="card chat-card">
      <view class="chat-head">
        <text class="chat-title">{{ pet?.name || "小智" }}</text>
        <view class="online" />
      </view>
      <scroll-view
        scroll-y
        class="chat-body"
        :scroll-into-view="scrollIntoView"
        :scroll-with-animation="true"
      >
        <view v-if="!messages.length" class="empty">先打个招呼吧</view>
        <view
          v-for="msg in messages"
          :id="`msg-${msg.id}`"
          :key="msg.id"
          class="chat-line"
          :class="msg.role"
        >
          <text class="bubble">{{ msg.content }}</text>
        </view>
        <view v-if="sending" class="chat-line assistant">
          <text class="bubble muted">正在思考……</text>
        </view>
      </scroll-view>
      <view class="chat-form">
        <input
          v-model="chatInput"
          class="input"
          maxlength="500"
          :placeholder="`和${pet?.name || '小智'}聊聊今天的学习`"
          confirm-type="send"
          @confirm="sendMessage"
        />
        <button class="btn primary send" @click="sendMessage">发送</button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import { onLoad, onUnload } from "@dcloudio/uni-app";

import { api } from "@/api/request";
import type { Pet, PetMessage } from "@/types";

const pet = ref<Pet | null>(null);
const messages = ref<PetMessage[]>([]);
const chatInput = ref("");
const sending = ref(false);
const loading = ref(false);
const petSays = ref("");
const jumping = ref(false);
const scrollIntoView = ref("");
let speechTimer: ReturnType<typeof setTimeout> | undefined;
let jumpTimer: ReturnType<typeof setTimeout> | undefined;

const expPercent = computed(() => {
  if (!pet.value) return 0;
  return Math.min(100, Math.round((pet.value.exp / (pet.value.level * 100)) * 100));
});
const moodPercent = computed(() =>
  pet.value ? Math.min(100, pet.value.mood) : 0,
);
const hungerPercent = computed(() =>
  pet.value ? Math.min(100, pet.value.hunger) : 0,
);

async function scrollToBottom() {
  await nextTick();
  const last = messages.value[messages.value.length - 1];
  scrollIntoView.value = last ? `msg-${last.id}` : "";
}

function showSays(text: string) {
  petSays.value = text;
  if (speechTimer) clearTimeout(speechTimer);
  speechTimer = setTimeout(() => {
    petSays.value = "";
  }, 4000);
}

function bounce() {
  jumping.value = true;
  if (jumpTimer) clearTimeout(jumpTimer);
  jumpTimer = setTimeout(() => {
    jumping.value = false;
  }, 700);
}

async function load() {
  loading.value = true;
  try {
    pet.value = await api.pet();
    const history = await api.petMessages(pet.value.id);
    messages.value = history;
    if (!history.length) {
      const greeting = await api.greetPet(pet.value.id);
      pet.value = greeting.pet;
      messages.value = greeting.messages;
    }
    await scrollToBottom();
  } catch {
    pet.value = null;
    messages.value = [];
  } finally {
    loading.value = false;
  }
}

async function feed(amount: number) {
  if (!pet.value) return;
  try {
    pet.value = await api.feedPet(pet.value.id, amount);
    showSays("好吃，能量满满！");
    bounce();
  } catch {
    pet.value = null;
  }
}

async function pat() {
  if (!pet.value) return;
  try {
    const result = await api.patPet(pet.value.id);
    pet.value = result.pet;
    showSays(result.reply);
  } catch {
    pet.value = null;
  }
}

async function play() {
  if (!pet.value) return;
  try {
    const result = await api.playPet(pet.value.id);
    pet.value = result.pet;
    showSays(result.reply);
    bounce();
  } catch {
    pet.value = null;
  }
}

async function revive() {
  if (!pet.value) return;
  try {
    const result = await api.revivePet(pet.value.id);
    pet.value = result.pet;
    showSays(result.reply);
    bounce();
  } catch {
    pet.value = null;
  }
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!pet.value || !text || sending.value) return;
  sending.value = true;
  try {
    const result = await api.chatPet(pet.value.id, text);
    pet.value = result.pet;
    messages.value = result.messages;
    chatInput.value = "";
    await scrollToBottom();
  } finally {
    sending.value = false;
  }
}

onLoad(load);
onUnload(() => {
  if (speechTimer) clearTimeout(speechTimer);
  if (jumpTimer) clearTimeout(jumpTimer);
});
</script>

<style scoped>
.page {
  padding: 20rpx;
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx;
}

.pet-stage {
  position: relative;
  height: 320rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
  border-radius: 16rpx;
  overflow: hidden;
}

.pet-image {
  width: 240rpx;
  height: 260rpx;
}

.pet-image.jumping {
  animation: jump 0.7s ease-in-out;
}

@keyframes jump {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-24rpx);
  }
}

.speech {
  position: absolute;
  left: 16rpx;
  top: 16rpx;
  max-width: 340rpx;
  background: #fff;
  border: 1px solid #dde3e8;
  border-radius: 12rpx 12rpx 12rpx 4rpx;
  padding: 12rpx 16rpx;
  color: #1d2733;
  font-size: 24rpx;
  line-height: 1.5;
}

.stage-badge {
  position: absolute;
  right: 16rpx;
  top: 16rpx;
  background: #fff;
  border: 1px solid #dde3e8;
  border-radius: 999rpx;
  padding: 6rpx 14rpx;
  color: #5b6b7a;
  font-size: 22rpx;
}

.pet-name {
  display: block;
  text-align: center;
  font-size: 34rpx;
  font-weight: 700;
  margin: 18rpx 0 8rpx;
}

.muted {
  color: #5b6b7a;
  font-size: 24rpx;
}

.danger {
  color: #dc2626;
  text-align: center;
  display: block;
  margin-bottom: 8rpx;
}

.stat {
  margin-top: 14rpx;
}

.stat text {
  display: block;
  color: #5b6b7a;
  font-size: 24rpx;
  margin-bottom: 6rpx;
}

.track {
  height: 12rpx;
  border-radius: 999rpx;
  background: #edf1f5;
  overflow: hidden;
}

.bar {
  height: 100%;
  border-radius: 999rpx;
  background: #2563eb;
}

.bar.mood {
  background: #d97706;
}

.bar.hunger {
  background: #0f766e;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 18rpx;
}

.btn {
  border-radius: 12rpx;
  padding: 12rpx 18rpx;
  font-size: 26rpx;
  font-weight: 600;
  line-height: 1;
}

.btn.small {
  padding: 10rpx 16rpx;
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

.btn.danger {
  background: #fee2e2;
  color: #dc2626;
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
  gap: 10rpx;
  padding: 20rpx 24rpx;
  border-bottom: 1px solid #dde3e8;
}

.chat-title {
  font-size: 30rpx;
  font-weight: 700;
}

.online {
  width: 14rpx;
  height: 14rpx;
  border-radius: 50%;
  background: #16a34a;
  margin-left: auto;
}

.chat-body {
  height: 640rpx;
  padding: 20rpx 24rpx;
  box-sizing: border-box;
}

.empty {
  color: #5b6b7a;
  font-size: 24rpx;
  text-align: center;
  padding: 120rpx 0;
}

.chat-line {
  display: flex;
  margin-bottom: 16rpx;
}

.chat-line.assistant {
  justify-content: flex-start;
}

.chat-line.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 520rpx;
  padding: 14rpx 18rpx;
  border-radius: 16rpx 16rpx 16rpx 4rpx;
  background: #eef3f8;
  color: #1d2733;
  font-size: 26rpx;
  line-height: 1.5;
}

.chat-line.user .bubble {
  background: #2563eb;
  color: #fff;
  border-radius: 16rpx 16rpx 4rpx 16rpx;
}

.bubble.muted {
  color: #5b6b7a;
}

.chat-form {
  display: flex;
  gap: 12rpx;
  padding: 16rpx 24rpx;
  border-top: 1px solid #dde3e8;
  background: #fbfcfd;
}

.input {
  flex: 1;
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 12rpx 16rpx;
  font-size: 26rpx;
}

.send {
  flex-shrink: 0;
}
</style>
