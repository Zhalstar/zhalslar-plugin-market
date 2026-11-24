<script setup lang="ts">
import { ArrowLeft } from "@lucide/vue";
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api";
import PluginCard from "../components/PluginCard.vue";
import UserAvatar from "../components/UserAvatar.vue";
import { t } from "../preferences";
import type { PublicProfile } from "../types";

const route = useRoute();
const profile = ref<PublicProfile>();
const loading = ref(true);
const error = ref("");

watch(() => String(route.params.id), async (id, _, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  loading.value = true;
  error.value = "";
  try {
    const item = await api.profile(id);
    if (current) profile.value = item;
  } catch (reason) {
    if (current) error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    if (current) loading.value = false;
  }
}, { immediate: true });
</script>

<template>
  <main class="page-shell">
    <router-link to="/market" class="action-content text-primary"><ArrowLeft :size="17" />{{ t('back') }}</router-link>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mt-6" />
    <v-alert v-else-if="error" type="error" variant="tonal" class="mt-6">{{ error }}</v-alert>
    <template v-else-if="profile">
      <section class="profile-header">
        <UserAvatar :src="profile.avatar_url" :size="70" />
        <div class="profile-title">
          <h1 class="page-heading">{{ profile.display_name || t('guest') }}</h1>
          <p class="page-subtitle">{{ t('count', { count: profile.plugins.length }) }}</p>
        </div>
      </section>
      <div v-if="profile.plugins.length" class="plugin-grid">
        <PluginCard v-for="plugin in profile.plugins" :key="plugin.id" :plugin="plugin" />
      </div>
      <div v-else class="empty-state">{{ t('noPublished') }}</div>
    </template>
  </main>
</template>

<style scoped>
.profile-header { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; padding: 24px 0; }
.profile-title { flex: 1; min-width: 0; overflow-wrap: anywhere; }
</style>
