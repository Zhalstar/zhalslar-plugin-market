<script setup lang="ts">
import { Bot, GitBranch, MessagesSquare, Star, Tag } from "@lucide/vue";
import { language, t } from "../preferences";
import type { Plugin } from "../types";
import UserAvatar from "./UserAvatar.vue";

defineProps<{ plugin: Plugin; showIdentity?: boolean }>();
</script>

<template>
  <div class="facts">
    <span v-if="showIdentity" :title="plugin.author"><UserAvatar :src="plugin.publisher_avatar_url" :size="16" /><span>{{ plugin.author }}</span></span>
    <span v-if="showIdentity && plugin.version" :title="t('versions')"><GitBranch :size="13" /><span>{{ plugin.version }}</span></span>
    <span v-if="plugin.stars != null" :title="t('stars', { count: plugin.stars })"><Star :size="13" /><span>{{ plugin.stars.toLocaleString(language) }}</span></span>
    <span v-if="plugin.astrbot_version" :title="`${t('astrbotVersion')} ${plugin.astrbot_version}`"><Bot :size="13" /><span>{{ plugin.astrbot_version }}</span></span>
    <span v-if="plugin.support_platforms.length" :title="`${t('platforms')} ${plugin.support_platforms.join(' · ')}`">
      <MessagesSquare :size="13" /><span>{{ plugin.support_platforms[0] }}</span><small v-if="plugin.support_platforms.length > 1">+{{ plugin.support_platforms.length - 1 }}</small>
    </span>
    <span v-if="plugin.tags.length" :title="`${t('tags')} ${plugin.tags.join(' · ')}`">
      <Tag :size="13" /><span>{{ plugin.tags[0] }}</span><small v-if="plugin.tags.length > 1">+{{ plugin.tags.length - 1 }}</small>
    </span>
  </div>
</template>

<style scoped>
.facts { display: flex; flex-wrap: wrap; align-items: center; gap: 5px 11px; color: var(--muted); font-size: 12px; }
.facts:empty { display: none; }
.facts > span { display: inline-flex; align-items: center; gap: 4px; min-width: 0; max-width: 100%; white-space: nowrap; }
.facts > span > span:not(.v-avatar) { max-width: var(--fact-value-width, 24ch); overflow: hidden; text-overflow: ellipsis; }
.facts svg, .facts small { flex-shrink: 0; }
</style>
