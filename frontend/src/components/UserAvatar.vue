<script setup lang="ts">
import { UserRound } from "@lucide/vue";
import { ref, watch } from "vue";

const props = defineProps<{ src?: string | null; size: number }>();
const failed = ref(false);
watch(() => props.src, () => { failed.value = false; });
</script>

<template>
  <v-avatar tag="span" :size="size" class="user-avatar" aria-hidden="true">
    <img v-if="src && !failed" :src="src" alt="" @error="failed = true" />
    <UserRound v-else :size="Math.min(32, Math.round(size * 0.78))" />
  </v-avatar>
</template>

<style scoped>
.user-avatar { flex-shrink: 0; }
.user-avatar img { width: 100%; height: 100%; object-fit: cover; }
</style>
