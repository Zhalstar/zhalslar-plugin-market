<script setup lang="ts">
import { CircleHelp, Clipboard, Check } from "@lucide/vue";
import { ref, watch } from "vue";
import { t } from "../preferences";

const storageKey = "zhalhub-market-guide-dismissed";
const open = ref(localStorage.getItem(storageKey) !== "1");
const sourceUrl = new URL("/market.json", window.location.origin).href;
const copyState = ref<"idle" | "copied" | "failed">("idle");

watch(open, (value) => {
  if (!value) localStorage.setItem(storageKey, "1");
  copyState.value = "idle";
});

async function copySource() {
  try {
    await navigator.clipboard.writeText(sourceUrl);
    if (open.value) copyState.value = "copied";
  } catch {
    if (open.value) copyState.value = "failed";
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="500" aria-labelledby="market-welcome-title">
    <template #activator="{ props }">
      <v-btn v-bind="props" variant="text" size="small" class="guide-trigger">
        <span class="action-content"><CircleHelp :size="15" />{{ t('marketGuide') }}</span>
      </v-btn>
    </template>

    <v-card>
      <v-card-title id="market-welcome-title" class="text-h3 pa-4 pb-0 pl-6 welcome-title">{{ t('marketWelcome') }}</v-card-title>
      <v-card-text class="welcome-body">
        <ol class="welcome-steps">
          <li>{{ t('marketGuideOpen') }}</li>
          <li>{{ t('marketGuideAdd') }}</li>
          <li>{{ t('marketGuideSelect') }}</li>
        </ol>
        <div class="welcome-source">
          <code>{{ sourceUrl }}</code>
          <v-btn color="primary" variant="tonal" size="small" @click="copySource">
            <span class="action-content"><component :is="copyState === 'copied' ? Check : Clipboard" :size="15" />{{ t(copyState === 'copied' ? 'sourceCopied' : 'copySource') }}</span>
          </v-btn>
        </div>
        <p v-if="copyState === 'failed'" class="copy-error" role="status">{{ t('sourceCopyFailed') }}</p>
      </v-card-text>
      <v-card-actions class="justify-end px-6 pb-4">
        <v-btn variant="text" color="primary" @click="open = false">{{ t('marketGuideDone') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.guide-trigger { margin-inline-start: auto; color: var(--muted); }
.welcome-title { font-size: 22px !important; white-space: normal; }
.welcome-steps { padding-inline-start: 20px; margin-bottom: 14px; }
.welcome-steps li + li { margin-top: 5px; }
.welcome-source { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 10px; background: var(--soft); border-radius: 8px; }
.welcome-source code { overflow-wrap: anywhere; user-select: all; font-size: 12px; }
.copy-error { margin-top: 6px; color: var(--muted); font-size: 12px; }
</style>
