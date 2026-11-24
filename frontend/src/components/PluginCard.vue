<script setup lang="ts">
import { ExternalLink } from "@lucide/vue";
import { ref, watch } from "vue";
import { RouterLink, type LocationQuery } from "vue-router";
import type { Plugin } from "../types";
import PluginFacts from "./PluginFacts.vue";

const props = defineProps<{ plugin: Plugin; marketQuery?: LocationQuery }>();
const logoFailed = ref(false);

watch(
  () => props.plugin.logo,
  () => {
    logoFailed.value = false;
  },
);
</script>

<template>
  <article class="plugin-card panel">
    <component :is="plugin.status === 'published' ? RouterLink : 'div'" class="plugin-card__body"
      v-bind="plugin.status === 'published' ? { to: { path: `/plugins/${plugin.id}`, query: marketQuery } } : {}">
    <div class="plugin-card__top">
      <img
        :src="logoFailed || !plugin.logo ? '/favicon.svg' : plugin.logo"
        :alt="plugin.display_name || plugin.name"
        class="plugin-card__logo"
        loading="lazy"
        decoding="async"
        @error="logoFailed = true"
      />
      <div class="plugin-card__title-wrap">
        <h2>{{ plugin.display_name || plugin.name }}</h2>
        <span>{{ plugin.name }}</span>
      </div>
      <ExternalLink v-if="plugin.status === 'published'" :size="17" class="plugin-card__arrow" />
    </div>
    <p class="plugin-card__description">{{ plugin.short_desc || plugin.desc }}</p>
    <PluginFacts :plugin="plugin" show-identity class="plugin-card__footer" />
    </component>
    <div v-if="$slots.actions" class="plugin-card__actions"><slot name="actions" /></div>
  </article>
</template>

<style scoped>
.plugin-card {
  display: flex;
  min-width: 0;
  min-height: 164px;
  flex-direction: column;
  transition:
    border-color 150ms ease,
    box-shadow 150ms ease,
    transform 150ms ease;
}

.plugin-card:hover,
.plugin-card:focus-within {
  border-color: var(--accent);
  box-shadow: 0 7px 20px rgba(31, 45, 61, 0.08);
  transform: translateY(-2px);
}

.plugin-card__body {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  padding: 20px;
  color: inherit;
}

.plugin-card__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-inline: 20px;
  padding-block: 7px;
  border-top: 1px solid var(--line);
}

.plugin-card__top {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 13px;
}

.plugin-card__logo {
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  border-radius: 6px;
  object-fit: contain;
}

.plugin-card__title-wrap {
  min-width: 0;
}

.plugin-card__title-wrap h2 {
  overflow: hidden;
  margin: 0 0 3px;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plugin-card__title-wrap span {
  display: block;
  overflow: hidden;
  color: var(--muted);
  font-family: ui-monospace, "Cascadia Code", monospace;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plugin-card__arrow {
  flex: 0 0 auto;
  margin-left: auto;
  color: var(--muted);
}

.plugin-card__description {
  display: -webkit-box;
  overflow: hidden;
  min-height: 44px;
  margin: 13px 0 9px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.plugin-card__footer {
  --fact-value-width: 13ch;
  margin-top: auto;
}
</style>

