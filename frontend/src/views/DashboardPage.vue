<script setup lang="ts">
import { PackagePlus, RefreshCw, Undo2, Upload } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { api } from "../api";
import ClaimPluginsDialog from "../components/ClaimPluginsDialog.vue";
import PluginCard from "../components/PluginCard.vue";
import { t } from "../preferences";
import type { Plugin } from "../types";

const plugins = ref<Plugin[]>([]);
const loading = ref(true);
const action = ref<{ id: string; kind: "update" | "unpublish" }>();
const error = ref("");
const notice = ref("");

const load = async () => {
  loading.value = true;
  try {
    plugins.value = await api.myPlugins();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    loading.value = false;
  }
};

const checkUpdate = async (plugin: Plugin) => {
  if (action.value) return;
  action.value = { id: plugin.id, kind: "update" };
  error.value = "";
  notice.value = "";
  try {
    const updated = await api.checkUpdate(plugin.id);
    const index = plugins.value.findIndex((item) => item.id === plugin.id);
    if (index >= 0) plugins.value[index] = updated;
    notice.value = t("updated", { name: updated.display_name || updated.name, version: updated.version });
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    action.value = undefined;
  }
};

const unpublish = async (plugin: Plugin) => {
  if (action.value) return;
  action.value = { id: plugin.id, kind: "unpublish" };
  error.value = "";
  notice.value = "";
  try {
    await api.unpublish(plugin.id);
    plugin.status = "unpublished";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    action.value = undefined;
  }
};

onMounted(load);
</script>

<template>
  <main class="page-shell dashboard-page">
    <div class="dashboard-heading">
      <div>
        <h1 class="page-heading">{{ t('myPlugins') }}</h1>
        <p class="page-subtitle">{{ loading ? t('loading') : t('count', { count: plugins.length }) }}</p>
      </div>
      <div class="dashboard-actions">
        <ClaimPluginsDialog @claimed="notice = t('pluginsClaimed', { count: $event.length }); load()" />
        <v-btn to="/publish" color="primary">
          <span class="action-content"><PackagePlus :size="17" />{{ t('publishPlugin') }}</span>
        </v-btn>
      </div>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" closable class="mt-5" @click:close="error = ''">
      {{ error }}
    </v-alert>
    <v-alert v-if="notice" type="success" variant="tonal" closable class="mt-5" @click:close="notice = ''">
      {{ notice }}
    </v-alert>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mt-6" />

    <div v-else-if="plugins.length" class="plugin-grid mt-6">
      <PluginCard v-for="plugin in plugins" :key="plugin.id" :plugin="plugin">
        <template #actions>
          <span class="plugin-status" :class="{ 'plugin-status--published': plugin.status === 'published' }">{{ t(plugin.status) }}</span>
          <v-btn
            icon
            variant="text"
            size="small"
            :title="t('checkUpdate')"
            :aria-label="t('checkUpdate')"
            :disabled="!!action"
            :loading="action?.id === plugin.id && action.kind === 'update'"
            @click="checkUpdate(plugin)"
          >
            <RefreshCw :size="16" />
          </v-btn>
          <v-btn
            v-if="plugin.status === 'published'"
            icon
            color="error"
            variant="text"
            size="small"
            :title="t('unpublish')"
            :aria-label="t('unpublish')"
            :disabled="!!action"
            :loading="action?.id === plugin.id && action.kind === 'unpublish'"
            @click="unpublish(plugin)"
          >
            <Undo2 :size="16" />
          </v-btn>
          <v-btn v-else to="/publish" color="primary" variant="text" size="small">
            <span class="action-content"><Upload :size="15" />{{ t('republish') }}</span>
          </v-btn>
        </template>
      </PluginCard>
    </div>
    <div v-else class="empty-state mt-6">
      <div>
        <PackagePlus :size="32" />
        <p>{{ t('noPublished') }}</p>
        <v-btn to="/publish" color="primary" variant="tonal">{{ t('publishPlugin') }}</v-btn>
      </div>
    </div>
  </main>
</template>

<style scoped>
.dashboard-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.dashboard-actions { display: flex; flex-wrap: wrap; gap: 8px; }

.plugin-status {
  margin-inline-end: auto;
  color: var(--muted);
  font-size: 12px;
}

.plugin-status--published {
  color: rgb(var(--v-theme-secondary));
}
</style>
