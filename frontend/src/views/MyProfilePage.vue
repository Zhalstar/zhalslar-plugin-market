<script setup lang="ts">
import { Trash2, Upload } from "@lucide/vue";
import { ref } from "vue";
import { api } from "../api";
import UserAvatar from "../components/UserAvatar.vue";
import { t } from "../preferences";
import { useAuthStore } from "../stores/auth";
import type { User } from "../types";

const auth = useAuthStore();
const name = ref(auth.user?.display_name || "");
const picker = ref<HTMLInputElement>();
const busy = ref(false);
const saved = ref(false);
const error = ref("");

async function update(action: () => Promise<User>) {
  if (busy.value) return;
  busy.value = true;
  saved.value = false;
  error.value = "";
  try {
    auth.user = await action();
    saved.value = true;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    busy.value = false;
  }
}

function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) void update(() => api.uploadAvatar(file));
  input.value = "";
}
</script>

<template>
  <main v-if="auth.user" class="page-shell my-profile">
    <h1 class="page-heading">{{ t('profile') }}</h1>
    <section class="profile-section" aria-labelledby="profile-info-heading">
      <h2 id="profile-info-heading">{{ t('profileInfo') }}</h2>
      <div class="avatar-actions">
        <UserAvatar :src="auth.user.avatar_url" :size="64" />
        <input ref="picker" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="upload" />
        <v-btn variant="tonal" color="primary" size="small" :disabled="busy" @click="picker?.click()">
          <span class="action-content"><Upload :size="15" />{{ t('uploadAvatar') }}</span>
        </v-btn>
        <v-btn v-if="auth.user.avatar_url" icon variant="text" size="small" :disabled="busy"
          :title="t('removeAvatar')" :aria-label="t('removeAvatar')" @click="update(api.removeAvatar)">
          <Trash2 :size="16" />
        </v-btn>
      </div>
      <dl class="profile-email">
        <dt>{{ t('email') }}</dt>
        <dd>{{ auth.user.email }}</dd>
      </dl>
      <form class="profile-form" @submit.prevent="update(() => api.editProfile(name.trim()))">
        <v-text-field v-model="name" :label="t('displayName')" maxlength="100" density="compact" variant="outlined" hide-details />
        <v-btn color="primary" type="submit" :disabled="busy || name.trim() === auth.user.display_name" :loading="busy">{{ t('save') }}</v-btn>
      </form>
      <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mt-4">{{ error }}</v-alert>
      <v-alert v-else-if="saved" type="success" variant="tonal" density="compact" class="mt-4">{{ t('saved') }}</v-alert>
    </section>
  </main>
</template>

<style scoped>
.my-profile { max-width: 700px; }
.profile-section { margin-top: 24px; }
.profile-section h2 { margin: 0; font-size: 17px; }
.avatar-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.profile-email { margin: 0 0 16px; }
.profile-email dt { color: var(--muted); font-size: 12px; }
.profile-email dd { margin: 2px 0 0; font-size: 14px; overflow-wrap: anywhere; }
.profile-form { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.profile-form :deep(.v-input) { flex: 1 1 200px; }
</style>
