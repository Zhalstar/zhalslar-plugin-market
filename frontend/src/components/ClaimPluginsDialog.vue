<script setup lang="ts">
import { ShieldCheck } from "@lucide/vue";
import { ref, watch } from "vue";
import { api } from "../api";
import { t } from "../preferences";
import type { Plugin } from "../types";

const emit = defineEmits<{ claimed: [plugins: Plugin[]] }>();
const open = ref(false);
const loading = ref(false);
const submitting = ref(false);
const candidates = ref<Plugin[]>([]);
const selected = ref<string[]>([]);
const error = ref("");

watch(open, async (value, _, onCleanup) => {
  if (!value) return;
  let current = true;
  onCleanup(() => { current = false; });
  candidates.value = [];
  selected.value = [];
  error.value = "";
  loading.value = true;
  try {
    const items = await api.claimablePlugins();
    if (current) candidates.value = items;
  } catch (reason) {
    if (current) error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    if (current) loading.value = false;
  }
});

async function claim() {
  if (submitting.value || !selected.value.length) return;
  submitting.value = true;
  error.value = "";
  try {
    emit("claimed", await api.claimPlugins(selected.value));
    open.value = false;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="560" scrollable :persistent="submitting" aria-labelledby="claim-dialog-title">
    <template #activator="{ props }">
      <v-btn v-bind="props" color="primary" variant="tonal">
        <span class="action-content"><ShieldCheck :size="17" />{{ t('claimPlugins') }}</span>
      </v-btn>
    </template>
    <v-card>
      <v-card-title id="claim-dialog-title" class="text-h3 pa-4 pb-0 pl-6 claim-title">{{ t('claimPlugins') }}</v-card-title>
      <v-card-text>
        <v-progress-linear v-if="loading" indeterminate color="primary" />
        <v-alert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</v-alert>
        <template v-if="!loading && candidates.length">
          <v-checkbox-btn
            :model-value="selected.length === candidates.length"
            :indeterminate="selected.length > 0 && selected.length < candidates.length"
            :label="t('selectAll')" :disabled="submitting" color="primary" density="compact"
            @update:model-value="selected = $event ? candidates.map(item => item.id) : []"
          />
          <v-divider />
          <v-checkbox-btn v-for="item in candidates" :key="item.id" v-model="selected" :value="item.id"
            :disabled="submitting" color="primary" density="compact" class="claim-option">
            <template #label>
              <span class="claim-repo"><strong>{{ item.display_name || item.name }}</strong><small>{{ item.repo.replace(/^https:\/\//, '') }}</small></span>
            </template>
          </v-checkbox-btn>
        </template>
        <template v-else-if="!loading && !error">
          <p class="claim-empty">{{ t('noClaimablePlugins') }}</p>
          <v-btn to="/settings/accounts" variant="text" color="primary" class="px-0">{{ t('accounts') }}</v-btn>
        </template>
      </v-card-text>
      <v-card-actions class="justify-end px-6 pb-4">
        <v-btn variant="text" :disabled="submitting" @click="open = false">{{ t('cancel') }}</v-btn>
        <v-btn v-if="candidates.length" color="primary" variant="tonal" :loading="submitting"
          :disabled="!selected.length" @click="claim">{{ t('confirmClaim', { count: selected.length }) }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.claim-title { font-size: 22px !important; }
.claim-option { padding-block: 5px; }
.claim-repo { display: grid; min-width: 0; line-height: 1.35; overflow-wrap: anywhere; }
.claim-repo small, .claim-empty { color: var(--muted); }
</style>
