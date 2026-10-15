<script setup lang="ts">
import { useStoryStore } from '@/composables/useStoryStore'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { backgroundMedia, isBackgroundVideo, setBackgroundMedia, clearBackgroundMedia } = useStoryStore()

function handleBgUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const url = URL.createObjectURL(file)
  setBackgroundMedia(url, file.type.startsWith('video/'))
  emit('update:modelValue', false)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="emit('update:modelValue', false)">
      <div class="modal">
        <h2>Set Background</h2>

        <div v-if="backgroundMedia" class="bg-preview">
          <video
            v-if="isBackgroundVideo"
            :src="backgroundMedia"
            autoplay
            loop
            muted
            playsinline
            class="bg-preview-media"
          ></video>
          <img v-else :src="backgroundMedia" class="bg-preview-media" alt="background preview" />
        </div>

        <label class="modal-file-upload">
          <input type="file" accept="image/gif,video/mp4,video/webm" @change="handleBgUpload" />
          <span class="modal-upload-btn">{{ backgroundMedia ? 'Change File' : 'Choose File' }}</span>
        </label>

        <div class="modal-actions">
          <button
            v-if="backgroundMedia"
            class="modal-btn modal-btn--danger"
            @click="clearBackgroundMedia(), emit('update:modelValue', false)"
          >
            Clear Background
          </button>
          <button class="modal-btn" @click="emit('update:modelValue', false)">Close</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}
.modal {
  background: rgba(20, 20, 40, 0.95);
  padding: 2rem;
  border-radius: 1rem;
  border: 1px solid rgba(100, 100, 255, 0.3);
  max-width: 600px;
  width: 90%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.modal h2 { color: #e2e8f0; font-size: 1.25rem; margin: 0; }
.modal-file-upload { display: flex; align-items: center; gap: 1rem; cursor: pointer; }
.modal-file-upload input { display: none; }
.modal-upload-btn {
  background-color: #374151;
  color: #e2e8f0;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  transition: background-color 0.2s;
}
.modal-upload-btn:hover { background-color: #4b5563; }
.modal-actions { display: flex; gap: 0.75rem; }
.modal-btn {
  background: #374151;
  border: none;
  color: #e2e8f0;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.9rem;
  transition: background-color 0.2s;
}
.modal-btn:hover { background: #4b5563; }
.modal-btn--danger { background: #991b1b; color: #fecaca; }
.modal-btn--danger:hover { background: #b91c1c; }
.bg-preview { border-radius: 0.5rem; overflow: hidden; max-height: 200px; }
.bg-preview-media { width: 100%; max-height: 200px; object-fit: contain; }
</style>
