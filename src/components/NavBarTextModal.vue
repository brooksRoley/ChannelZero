<script setup lang="ts">
import { ref, watch } from 'vue'
import { useStoryStore } from '@/composables/useStoryStore'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { storyText, setStoryText, play } = useStoryStore()

const textInputValue = ref('')
const fileName = ref('')

watch(() => props.modelValue, (visible) => {
  if (visible) {
    textInputValue.value = storyText.value
    fileName.value = ''
  }
})

function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = (e) => { textInputValue.value = e.target?.result as string }
  reader.readAsText(file)
}

function loadText() {
  if (!textInputValue.value.trim()) return
  setStoryText(textInputValue.value)
  emit('update:modelValue', false)
  play()
}
</script>

<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="emit('update:modelValue', false)">
      <div class="modal">
        <h2>Enter Text</h2>

        <label class="modal-file-upload">
          <input type="file" accept=".txt,.md" @change="handleFileUpload" />
          <span class="modal-upload-btn">Choose File</span>
          <span v-if="fileName" class="modal-file-name">{{ fileName }}</span>
        </label>

        <div class="modal-divider">or</div>

        <textarea
          v-model="textInputValue"
          placeholder="Paste your text here..."
          class="modal-textarea"
          rows="10"
        ></textarea>

        <div class="modal-actions">
          <button
            class="modal-btn modal-btn--primary"
            :disabled="!textInputValue.trim()"
            @click="loadText"
          >
            Start Reading
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
.modal-file-name { color: #94a3b8; font-size: 0.875rem; }
.modal-divider { color: #64748b; font-size: 0.875rem; text-align: center; }
.modal-textarea {
  width: 100%;
  padding: 1rem;
  background: rgba(30, 30, 50, 0.9);
  border: 1px solid rgba(100, 100, 255, 0.3);
  color: #e2e8f0;
  border-radius: 0.5rem;
  font-family: inherit;
  font-size: 1rem;
  resize: vertical;
}
.modal-textarea::placeholder { color: #64748b; }
.modal-textarea:focus { border-color: #6366f1; }
.modal-textarea:focus:not(:focus-visible) { outline: none; }
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
.modal-btn--primary { background: #6366f1; }
.modal-btn--primary:hover:not(:disabled) { background: #4f46e5; }
.modal-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
