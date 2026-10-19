<template>
  <div class="min-h-screen bg-[#0a0a0a] text-slate-300 pt-20 pb-16 px-4">
    <div class="max-w-6xl mx-auto grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">

      <!-- ── Authoring ── -->
      <section class="space-y-4 min-w-0">
        <header>
          <h1 class="text-white/90 text-lg font-light tracking-[0.25em] uppercase">Story Studio</h1>
          <p class="text-slate-500 text-xs mt-1 leading-relaxed">
            The story is read aloud over warm music that deepens with it. You can follow along on a reading
            line while key phrases bloom as they're spoken — or switch to Bold for flashes and subliminals.
          </p>
        </header>

        <div class="flex gap-2 flex-wrap">
          <button
            v-for="s in STORY_SAMPLES"
            :key="s.id"
            class="chip"
            :class="{ 'chip--on': text === s.text }"
            @click="text = s.text"
          >{{ s.title }}</button>
        </div>

        <label class="block">
          <span class="sr-only">Story text</span>
          <textarea
            v-model="text"
            rows="16"
            spellcheck="true"
            class="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg p-3 text-sm leading-relaxed text-slate-200 font-mono focus:outline-none focus:border-white/20"
          />
        </label>
        <details class="text-[11px] text-slate-500 leading-relaxed">
          <summary class="cursor-pointer text-slate-400">Markup</summary>
          <ul class="mt-2 space-y-1">
            <li>Blank lines separate beats.</li>
            <li><code>*key phrase*</code> shows a phrase as it's spoken; <code>*flash:let go*</code> picks the effect —
              <code v-for="e in effectNames" :key="e" class="mx-0.5">{{ e }}</code>.</li>
            <li>Stage lines: <code v-for="m in markers" :key="m" class="mx-0.5">[{{ m }}]</code>. Without any, the arc is automatic.</li>
            <li><code>[subliminal calm, safe, deeper]</code> flashes those words for a frame or two from then on; <code>[subliminal off]</code> stops.</li>
            <li><code>[pause 6]</code> holds in silence.</li>
          </ul>
        </details>

        <div class="grid grid-cols-2 gap-3 text-xs">
          <div class="field">
            <span>Backdrops <span class="text-slate-600">· clips &amp; stills, chosen per beat below</span></span>
            <label class="relative block truncate px-3 py-2 rounded-md bg-white/[0.04] border border-white/[0.06] cursor-pointer hover:bg-white/[0.07]">
              {{ media.size ? `Add more (${media.size} loaded)` : 'Add video or image…' }}
              <input type="file" accept="video/*,image/*" multiple class="absolute inset-0 opacity-0 cursor-pointer" @change="onMediaPick" />
            </label>
            <div v-if="media.size" class="flex gap-1.5 flex-wrap">
              <span v-for="m in media.values()" :key="m.id" class="inline-flex items-center gap-1.5 text-[10px] pl-1 pr-1.5 py-0.5 rounded bg-white/[0.05] text-slate-400 max-w-full">
                <span class="w-3 h-3 rounded-sm shrink-0" :style="swatch({ kind: 'media', mediaId: m.id })" />
                <span class="truncate">{{ m.name }}</span>
                <button class="text-slate-600 hover:text-rose-300" :aria-label="`Remove ${m.name}`" @click="removeMedia(m.id)">×</button>
              </span>
            </div>
          </div>
          <label class="field">
            <span>Reading pace (unvoiced beats) · {{ wpm }} wpm</span>
            <input v-model.number="wpm" type="range" min="90" max="220" step="5" />
          </label>
          <div class="field">
            <span>Look</span>
            <div class="flex gap-2" role="radiogroup" aria-label="Look">
              <button v-for="l in looks" :key="l.id" class="chip flex-1" role="radio" :aria-checked="look === l.id" :class="{ 'chip--on': look === l.id }" :title="l.hint" @click="look = l.id">{{ l.label }}</button>
            </div>
          </div>
          <label class="flex items-center gap-2 text-slate-400 self-end pb-2">
            <input v-model="captions" type="checkbox" /> Show the story as a reading line
          </label>
        </div>

        <!-- Sound design -->
        <fieldset class="space-y-3 rounded-lg border border-white/[0.06] p-3 text-xs">
          <legend class="px-1 text-slate-400">Sound design</legend>
          <div class="flex gap-1.5 flex-wrap items-center" role="radiogroup" aria-label="Mix preset">
            <button
              v-for="p in MIX_PRESETS"
              :key="p.name"
              class="chip"
              role="radio"
              :aria-checked="activePreset === p.name"
              :class="{ 'chip--on': activePreset === p.name }"
              @click="applyPreset(p)"
            >{{ p.name }}</button>
            <span v-for="p in customPresets" :key="p.name" class="inline-flex items-center">
              <button class="chip" role="radio" :aria-checked="activePreset === p.name" :class="{ 'chip--on': activePreset === p.name }" @click="applyPreset(p)">{{ p.name }}</button>
              <button class="text-slate-600 hover:text-rose-300 px-1" :aria-label="`Delete preset ${p.name}`" @click="removePreset(p.name)">×</button>
            </span>
          </div>
          <div class="flex gap-2 items-center">
            <input v-model="presetName" class="select flex-1" placeholder="Name this mix…" aria-label="Preset name" @keydown.enter="savePreset" />
            <button class="chip" @click="savePreset">Save mix</button>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <label class="field">
              <span>Key</span>
              <select v-model.number="design.key" class="select">
                <option v-for="k in KEYS" :key="k.semis" :value="k.semis">{{ k.label }} major</option>
              </select>
            </label>
            <label class="field" title="How open the pad sounds — darker is more lulling">
              <span>Warmth · {{ design.warmth < 0.35 ? 'dark' : design.warmth > 0.65 ? 'open' : 'warm' }}</span>
              <input v-model.number="design.warmth" type="range" min="0" max="1" step="0.05" />
            </label>
            <div class="field col-span-2">
              <span>Entrainment</span>
              <div class="flex gap-1.5" role="radiogroup" aria-label="Entrainment">
                <button v-for="e in entrainments" :key="e.id" class="chip flex-1 !px-2" role="radio" :aria-checked="design.entrainment === e.id" :class="{ 'chip--on': design.entrainment === e.id }" :title="e.hint" @click="design.entrainment = e.id">{{ e.label }}</button>
              </div>
            </div>
            <label class="field col-span-2" title="The voice's room. It still moves closer as the stages deepen.">
              <span>Voice room · {{ Math.round(design.room * 100) }}</span>
              <input v-model.number="design.room" type="range" min="0" max="1" step="0.05" />
            </label>
          </div>
          <div class="flex items-center gap-3 flex-wrap">
            <label class="flex items-center gap-2 text-slate-400" title="Caps entrainment level and pulse depth, and softens every attack">
              <input v-model="design.comfort" type="checkbox" /> Comfort mode
            </label>
            <button class="chip" :disabled="!!headphoneSide" @click="checkHeadphones">
              {{ headphoneSide === 'left' ? '◀ Left ear…' : headphoneSide === 'right' ? 'Right ear… ▶' : 'Check headphones' }}
            </button>
          </div>
          <p class="text-[11px] text-slate-600 leading-relaxed">
            The beds dip while the voice speaks. Going down, waves and heartbeat fill in and the voice draws closer;
            a bowl marks each deepening and a shimmer lifts into emerge and wake. Changes apply as you play.
          </p>
        </fieldset>

        <!-- Voice -->
        <fieldset class="space-y-3 rounded-lg border border-white/[0.06] p-3">
          <legend class="px-1 text-xs text-slate-400">Voice</legend>
          <div class="flex gap-2 flex-wrap" role="radiogroup" aria-label="Voice source">
            <button v-for="v in voiceModes" :key="v.id" class="chip" role="radio" :aria-checked="voiceMode === v.id" :class="{ 'chip--on': voiceMode === v.id }" @click="setVoiceMode(v.id)">
              {{ v.label }}
            </button>
          </div>

          <template v-if="voiceMode === 'pack'">
            <ol class="text-[11px] text-slate-500 leading-relaxed list-decimal pl-4 space-y-1">
              <li><button class="link" @click="downloadVoiceScript">Download the voice script</button> ({{ scriptChars }} characters ≈ {{ scriptChars }} credits on Multilingual v2, half on Flash).</li>
              <li>Run <code class="text-slate-400">node tools/voice/elevenlabs.mjs {{ scriptFileName }} --voice &lt;id&gt;</code> with <code>ELEVENLABS_API_KEY</code> set.</li>
              <li>
                <label class="link relative cursor-pointer">Load the pack folder
                  <input type="file" multiple webkitdirectory class="absolute inset-0 opacity-0 cursor-pointer w-full" @change="onPackPick" />
                </label>
                — or attach an mp3 to any beat in the list.
              </li>
            </ol>
            <p class="text-[11px]" :class="voicedCount === voiceableCount ? 'text-emerald-400/80' : 'text-slate-400'">
              {{ voicedCount }} of {{ voiceableCount }} beats have audio · {{ alignedCount }} with exact word timing
              <span v-if="packMeta?.voice_name" class="text-slate-600">· {{ packMeta.voice_name }}</span>
            </p>
            <p v-if="packSkipped.length" class="text-[11px] text-amber-400/70">Skipped {{ packSkipped.length }} file(s) that aren't beat audio: {{ packSkipped.slice(0, 3).join(', ') }}</p>
            <label class="flex items-center gap-2 text-[11px] text-slate-400">
              <input v-model="credit" type="checkbox" /> Credit “Voice: ElevenLabs” at the end (required on the free plan)
            </label>
          </template>

          <p v-else-if="voiceMode === 'local'" class="text-[11px] text-slate-500">
            {{ kokoroStatus === 'downloading' ? 'Downloading the on-device voice (~90 MB, once)…' : kokoroStatus === 'error' ? "The on-device voice couldn't load — beats will be silent." : 'On-device neural voice. No account needed; less expressive than ElevenLabs.' }}
          </p>
          <p v-else class="text-[11px] text-slate-500">Silent: key phrases are paced by reading speed.</p>
        </fieldset>

        <button
          class="w-full px-6 py-3 rounded-full border text-sm tracking-wider transition-all"
          :class="stale ? 'bg-white/10 border-white/20 text-white/90 hover:bg-white/15' : 'bg-white/[0.03] border-white/10 text-white/50'"
          :disabled="building || !parsed.length || player.state.value !== 'idle'"
          @click="build"
        >
          {{ building ? buildStep : timeline ? (stale ? 'Rebuild timeline' : 'Timeline is up to date') : 'Build timeline' }}
        </button>
        <p v-if="buildError" class="text-[11px] text-rose-400/80">{{ buildError }}</p>
      </section>

      <!-- ── Preview + timeline ── -->
      <section class="space-y-4 min-w-0">
        <div class="relative rounded-lg overflow-hidden bg-black border border-white/[0.05]">
          <canvas ref="canvasRef" class="block w-full h-auto" aria-hidden="true" />
          <div v-if="!timeline" class="absolute inset-0 flex items-center justify-center text-slate-600 text-xs tracking-[0.2em] uppercase">
            Build the timeline to preview
          </div>
          <div v-if="isRecording" class="absolute top-3 left-3 flex items-center gap-2 text-[10px] uppercase tracking-widest text-rose-300">
            <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse" /> Recording
          </div>
        </div>
        <div ref="mediaHost" class="absolute w-px h-px overflow-hidden opacity-0 pointer-events-none" aria-hidden="true" />

        <template v-if="timeline">
          <!-- Scene strip: each beat's backdrop -->
          <div class="flex h-5 rounded overflow-hidden bg-white/[0.04]" aria-label="Backdrops by beat">
            <div :style="{ width: pct(timeline.leadInMs), ...swatch(scenes[0]?.backdrop) }" class="opacity-60" />
            <button
              v-for="b in timeline.beats"
              :key="b.index"
              class="h-full border-r border-black/50 transition-[filter] hover:brightness-150"
              :class="{ 'ring-1 ring-inset ring-white/80': selected === b.index }"
              :style="{ width: pct(b.endMs - b.startMs), ...swatch(scenes[b.index]?.backdrop) }"
              :title="`Beat ${b.index + 1} · ${backdropLabel(scenes[b.index]?.backdrop)}`"
              :aria-label="`Edit beat ${b.index + 1}`"
              @click="selectBeat(b.index)"
            />
          </div>

          <!-- Stage bar with key-phrase ticks -->
          <div
            class="relative flex h-3 rounded-full overflow-hidden bg-white/[0.04] cursor-pointer"
            role="slider"
            tabindex="0"
            aria-label="Story position"
            :aria-valuenow="Math.round(cursorMs / 1000)"
            aria-valuemin="0"
            :aria-valuemax="Math.round(timeline.durationMs / 1000)"
            :aria-valuetext="formatClock(cursorMs)"
            @click="onBarClick"
            @keydown.left.prevent="seek(cursorMs - 5000)"
            @keydown.right.prevent="seek(cursorMs + 5000)"
          >
            <div :style="{ width: pct(timeline.leadInMs) }" />
            <div
              v-for="b in timeline.beats"
              :key="b.index"
              :class="`stage-${b.stage}`"
              class="h-full border-r border-black/40 opacity-70"
              :style="{ width: pct(b.endMs - b.startMs) }"
              :title="`${b.stage} · ${formatClock(b.startMs)}`"
            />
            <div v-for="(k, i) in timeline.keys" :key="`k${i}`" class="absolute top-0 bottom-0 w-px bg-white/70" :style="{ left: pct(k.spokenStartMs) }" />
            <div class="absolute top-0 bottom-0 w-0.5 bg-white" :style="{ left: pct(cursorMs) }" />
          </div>

          <!-- Level lanes: each bed across the story (stage arc × beat balance × fader) -->
          <div class="relative -mt-1">
            <svg :viewBox="`0 0 1000 ${LANE_H * lanes.length}`" preserveAspectRatio="none" class="w-full h-20 rounded bg-white/[0.02]" aria-label="Sound levels across the story" role="img">
              <g v-for="l in lanes" :key="l.id">
                <path :d="l.area" :fill="l.color" fill-opacity="0.18" />
                <path :d="l.line" :stroke="l.color" stroke-width="1.25" fill="none" vector-effect="non-scaling-stroke" opacity="0.85" />
              </g>
              <line :x1="(cursorMs / timeline.durationMs) * 1000" :x2="(cursorMs / timeline.durationMs) * 1000" y1="0" :y2="LANE_H * lanes.length" stroke="white" stroke-width="1" vector-effect="non-scaling-stroke" opacity="0.6" />
            </svg>
            <div class="absolute inset-y-0 left-1 flex flex-col justify-around pointer-events-none" aria-hidden="true">
              <span v-for="l in lanes" :key="l.id" class="text-[8px] leading-none uppercase tracking-wider" :style="{ color: l.color, opacity: 0.7 }">{{ stemLabel[l.id] }}</span>
            </div>
          </div>

          <div class="flex items-center gap-3 text-xs flex-wrap">
            <button class="chip" :disabled="isRecording" @click="togglePlay">{{ isPlaying ? 'Pause' : 'Play' }}</button>
            <span class="font-mono text-slate-500">{{ formatClock(cursorMs) }} / {{ formatClock(timeline.durationMs) }}</span>
            <span class="text-slate-600">{{ beatHzLabel }}</span>
            <span class="text-slate-600" :title="'Most flashes in any one second (WCAG 2.3.1 limit is 3)'">peak {{ flashRate }} flash/s</span>
            <span class="flex-1" />
            <button class="chip" :disabled="stale || isRecording || exportingWav" title="Render the mix to a WAV file (faster than real time)" @click="exportWav">{{ exportingWav ? 'Rendering…' : 'Export audio' }}</button>
            <button v-if="!isRecording" class="chip chip--rec" :disabled="stale || isPlaying" @click="record">Export video</button>
            <button v-else class="chip" @click="player.stop()">Cancel export</button>
          </div>
          <p class="text-[11px] text-slate-600 leading-relaxed">
            Export records in real time ({{ formatClock(timeline.durationMs) }}) and saves an {{ exportExt }} file.
            Keep this tab in front while it runs. Headphones carry the binaural beat.
            <span v-if="stale" class="text-amber-400/70">The story or voice changed — rebuild before exporting.</span>
          </p>

          <!-- Trance mixer -->
          <section class="rounded-lg border border-white/[0.06] p-3 space-y-2" aria-label="Mixer">
            <div class="flex items-baseline justify-between gap-3 flex-wrap text-[11px]">
              <span class="text-slate-400 uppercase tracking-widest">Mixer</span>
              <span class="text-slate-600">Faders move the live mix. The lanes above show each bed across the story.</span>
            </div>
            <div v-for="st in STEMS" :key="st.id" class="grid grid-cols-[6.5rem_auto_1fr_2.5rem] gap-2 items-center text-xs" :title="st.hint">
              <span class="flex items-center gap-1.5 truncate" :class="mix.muted[st.id] || (mix.solo && mix.solo !== st.id) ? 'text-slate-600' : 'text-slate-300'">
                <span class="w-2 h-2 rounded-full shrink-0" :style="{ background: STEM_COLORS[st.id] }" />{{ st.label }}
              </span>
              <span class="flex gap-1">
                <button class="ms" :class="{ 'ms--mute': mix.muted[st.id] }" :aria-pressed="mix.muted[st.id]" :aria-label="`Mute ${st.label}`" @click="toggleMute(st.id)">M</button>
                <button class="ms" :class="{ 'ms--solo': mix.solo === st.id }" :aria-pressed="mix.solo === st.id" :aria-label="`Solo ${st.label}`" @click="toggleSolo(st.id)">S</button>
              </span>
              <span class="relative h-5 flex items-center">
                <span class="absolute left-0 right-0 bottom-0 h-0.5 rounded bg-white/[0.04] overflow-hidden" aria-hidden="true">
                  <span class="block h-full transition-[width] duration-75" :style="{ width: `${(player.meters.value[st.id] ?? 0) * 100}%`, background: STEM_COLORS[st.id] }" />
                </span>
                <input
                  v-model.number="mix.faders[st.id]"
                  type="range" min="0" max="1" step="0.01"
                  class="w-full"
                  :style="{ accentColor: STEM_COLORS[st.id] }"
                  :aria-label="`${st.label} level`"
                />
              </span>
              <span class="font-mono text-[10px] text-right" :class="st.id === 'binaural' && design.comfort && mix.faders.binaural > COMFORT_ENTRAINMENT_MAX ? 'text-amber-400/70' : 'text-slate-500'" :title="st.id === 'binaural' && design.comfort ? `Comfort mode caps this at ${COMFORT_ENTRAINMENT_MAX * 100}` : ''">
                {{ Math.round(mix.faders[st.id] * 100) }}
              </span>
            </div>
          </section>

        </template>

        <!-- Beat list + per-beat editor -->
        <div v-if="parsed.length" class="flex items-baseline justify-between text-[11px] text-slate-500">
          <span>Beats — select one to style it</span>
          <span v-if="stale && timeline" class="text-amber-400/70">times update on rebuild</span>
        </div>
        <ol class="space-y-1 max-h-[56vh] overflow-y-auto pr-1" aria-label="Beats">
          <li
            v-for="(b, i) in parsed"
            :key="i"
            class="rounded-md border"
            :class="selected === i ? 'border-white/15 bg-white/[0.04]' : currentBeat === i && timeline && !stale ? 'border-transparent bg-white/[0.06]' : 'border-transparent'"
          >
            <div class="flex gap-3 items-center px-2 pt-1.5">
              <button class="font-mono text-[10px] text-slate-600 w-9 shrink-0 text-left hover:text-slate-300" :disabled="!freshBeat(i)" @click="seek(freshBeat(i)!.startMs)">
                {{ freshBeat(i) ? formatClock(freshBeat(i)!.startMs) : '–:––' }}
              </button>
              <span class="w-4 h-4 rounded-sm shrink-0 border border-white/10" :style="swatch(scenes[i]?.backdrop)" :title="backdropLabel(scenes[i]?.backdrop)" />
              <span class="stage-chip shrink-0" :class="`stage-${b.stage}`">{{ b.stage }}</span>
              <button class="text-xs text-slate-400 text-left truncate flex-1 hover:text-slate-200" :aria-expanded="selected === i" @click="selectBeat(i)">
                {{ b.text || `— silence ${Math.round((b.pauseMs ?? 0) / 1000)}s —` }}
              </button>
              <span v-if="styles[i]" class="text-[10px] text-sky-300/60 shrink-0" title="This beat has its own style">styled</span>
              <template v-if="b.text && voiceMode === 'pack'">
                <span v-if="clips.get(b.id)" class="text-[10px] shrink-0" :class="clips.get(b.id)?.alignment ? 'text-emerald-400/70' : 'text-slate-500'" :title="clips.get(b.id)?.name">
                  ♪{{ clips.get(b.id)?.alignment ? ' timed' : '' }}
                </span>
                <button class="text-[10px] text-slate-600 hover:text-slate-300 shrink-0" title="Copy the line to paste into ElevenLabs" @click="copyLine(b.text)">copy</button>
                <label class="relative text-[10px] text-slate-600 hover:text-slate-300 shrink-0 cursor-pointer" :title="`Attach an mp3 for this beat (${b.id})`">
                  {{ clips.get(b.id) ? 'replace' : 'attach' }}
                  <input type="file" accept="audio/*" class="absolute inset-0 opacity-0 cursor-pointer w-full" @change="onBeatAudio(b.id, $event)" />
                </label>
              </template>
              <span v-else-if="freshBeat(i)?.voiced" class="text-[10px] text-slate-600 shrink-0">♪</span>
            </div>
            <div v-if="keysByBeat.get(i)?.length && !stale" class="flex gap-1.5 flex-wrap pl-[4.75rem] pt-1">
              <button
                v-for="(k, j) in keysByBeat.get(i)"
                :key="j"
                class="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-400 hover:bg-white/10"
                @click="seek(k.startMs)"
              >
                <span class="text-slate-600">{{ k.effect }}</span> {{ k.text }}
              </button>
            </div>

            <!-- Inspector -->
            <div v-if="selected === i" class="grid grid-cols-2 gap-3 px-3 pt-3 pb-1 text-xs">
              <label class="field col-span-2 sm:col-span-1">
                <span>Backdrop</span>
                <select class="select" :value="backdropValue(styles[i])" @change="onBackdropSelect(i, ($event.target as HTMLSelectElement).value)">
                  <option value="continue">{{ i === 0 ? 'Default' : 'Continue' }} — {{ backdropLabel(i === 0 ? baseBackdrop : scenes[i - 1]?.backdrop) }}</option>
                  <option value="field">Breathing field</option>
                  <option value="solid">Colour</option>
                  <option value="gradient">Gradient</option>
                  <option v-for="m in media.values()" :key="m.id" :value="`media:${m.id}`">{{ m.kind === 'image' ? 'Still' : 'Clip' }}: {{ m.name }}</option>
                </select>
              </label>
              <div class="field col-span-2 sm:col-span-1">
                <span>Palette</span>
                <div class="flex gap-1.5">
                  <button
                    v-for="p in PALETTE"
                    :key="p.label"
                    class="w-6 h-6 rounded border border-white/10 hover:border-white/50"
                    :style="swatch(p.backdrop)"
                    :title="p.label"
                    :aria-label="`${p.label} backdrop`"
                    @click="setStyle(i, { backdrop: { ...p.backdrop } })"
                  />
                </div>
              </div>
              <div v-if="styles[i]?.backdrop?.kind === 'solid'" class="field col-span-2">
                <span>Colour</span>
                <input type="color" class="color" :value="(styles[i]!.backdrop as { color: string }).color" @input="setStyle(i, { backdrop: { kind: 'solid', color: ($event.target as HTMLInputElement).value } })" />
              </div>
              <div v-else-if="styles[i]?.backdrop?.kind === 'gradient'" class="field col-span-2">
                <span>Gradient · top → bottom</span>
                <div class="flex gap-2 items-center">
                  <input type="color" class="color" :value="(styles[i]!.backdrop as { from: string }).from" @input="setStyle(i, { backdrop: { ...(styles[i]!.backdrop as Extract<Backdrop, { kind: 'gradient' }>), from: ($event.target as HTMLInputElement).value } })" />
                  <span class="text-slate-600">→</span>
                  <input type="color" class="color" :value="(styles[i]!.backdrop as { to: string }).to" @input="setStyle(i, { backdrop: { ...(styles[i]!.backdrop as Extract<Backdrop, { kind: 'gradient' }>), to: ($event.target as HTMLInputElement).value } })" />
                </div>
              </div>

              <div v-if="b.text" class="field col-span-2 sm:col-span-1">
                <span>Reading line</span>
                <div class="flex gap-1.5" role="radiogroup" aria-label="Reading line position">
                  <button
                    v-for="pl in places"
                    :key="pl.id"
                    class="chip flex-1 !px-2"
                    role="radio"
                    :aria-checked="scenes[i]?.place === pl.id"
                    :class="{ 'chip--on': scenes[i]?.place === pl.id, 'chip--inherited': scenes[i]?.place === pl.id && !styles[i]?.place }"
                    @click="setStyle(i, { place: styles[i]?.place === pl.id ? undefined : pl.id })"
                  >{{ pl.label }}</button>
                </div>
              </div>
              <label v-if="b.keys.length" class="field col-span-2 sm:col-span-1">
                <span>Key phrase effect</span>
                <select class="select" :value="styles[i]?.effect ?? ''" @change="setStyle(i, { effect: (($event.target as HTMLSelectElement).value || undefined) as Effect | undefined })">
                  <option value="">Auto — rotate by stage</option>
                  <option v-for="e in effectNames" :key="e" :value="e">
                    {{ EFFECTS[e].label }}{{ look === 'gentle' && GENTLE_EFFECT[e] !== e ? ' (softens to Bloom in Gentle)' : '' }}
                  </option>
                </select>
              </label>
              <fieldset class="col-span-2 grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-2 rounded-md border border-white/[0.06] p-2">
                <legend class="px-1 text-slate-500">Sound from this beat on <span class="text-slate-600">· on top of the stage arc</span></legend>
                <label v-for="id in BED_STEMS" :key="id" class="field">
                  <span class="flex justify-between">
                    <span :class="styles[i]?.sound?.[id] != null ? 'text-slate-300' : ''">{{ stemLabel[id] }} · {{ Math.round((beatSoundResolved[i]?.[id] ?? 1) * 100) }}%</span>
                    <button v-if="styles[i]?.sound?.[id] != null" class="text-slate-600 hover:text-slate-300" :aria-label="`Reset ${stemLabel[id]} for this beat`" @click="setBeatSound(i, id, undefined)">↺</button>
                  </span>
                  <input type="range" min="0" max="1.5" step="0.05" :value="beatSoundResolved[i]?.[id] ?? 1" @input="setBeatSound(i, id, Number(($event.target as HTMLInputElement).value))" />
                </label>
              </fieldset>
              <label class="field col-span-2">
                <span>Hold after the beat · +{{ ((styles[i]?.holdMs ?? 0) / 1000).toFixed(1) }} s</span>
                <input type="range" min="0" :max="MAX_HOLD_MS" step="500" :value="styles[i]?.holdMs ?? 0" @input="setStyle(i, { holdMs: Number(($event.target as HTMLInputElement).value) })" />
              </label>
              <div class="col-span-2 flex items-center justify-between text-[11px] text-slate-600">
                <span>Backdrop, placement and sound apply now; effect and hold on rebuild.</span>
                <button v-if="styles[i]" class="link" @click="setStyle(i, { backdrop: undefined, place: undefined, effect: undefined, holdMs: undefined, sound: undefined })">Clear style</button>
              </div>
            </div>
            <div class="pb-1.5" />
          </li>
        </ol>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, shallowRef, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { STORY_SAMPLES } from '@/data/storySamples'
import {
  parseStory, buildTimeline, beatIndexAt, entrainmentAt, formatClock, STAGES,
  type Timeline, type TimedKey, type StoryStage, type Alignment,
} from '@/story/storyBeats'
import { EFFECTS, GENTLE_EFFECT, maxFlashesPerSecond, type Effect, type Look } from '@/story/effects'
import { loadEffectFonts } from '@/story/drawEffects'
import { voiceBuffer } from '@/story/score'
import { renderMixdown, encodeWav } from '@/story/mixer'
import {
  STEMS, BED_STEMS, KEYS, MIX_PRESETS, COMFORT_ENTRAINMENT_MAX, DEFAULT_DESIGN, defaultMix, stemGain,
  buildAutomation, resolveBeatSound, autoValueAt,
  type MixState, type SoundDesign, type StemId, type BedStem, type Entrainment, type MixPreset,
} from '@/story/trance'
import { readPack, decodeAudioFile, voiceScript, type VoiceClip, type PackMeta } from '@/story/voicePack'
import { useStoryPlayer, headphoneCheck, drawStoryFrame, canvasSizeFor, STORY_FADE_S, type FrameOptions, type StoryMedia, type SceneInput } from '@/story/useStoryPlayer'
import { resolveScenes, remapStyles, cleanStyle, MAX_HOLD_MS, type Backdrop, type BeatStyle, type TextPlace } from '@/story/beatStyle'
import { pickMime } from '@/composables/useGlassExport'
import { useVoice } from '@/composables/useVoice'

const markers = Object.keys(STAGES) as StoryStage[]
const effectNames = Object.keys(EFFECTS) as Effect[]

const text = ref(STORY_SAMPLES[0].text)
const wpm = ref(140)
const captions = ref(true)
const credit = ref(true)

const look = ref<Look>('gentle')
const looks: { id: Look; label: string; hint: string }[] = [
  { id: 'gentle', label: 'Gentle', hint: 'Readable story line, key phrases bloom softly one at a time' },
  { id: 'bold', label: 'Bold', hint: 'Flash, slam, scatter and visible subliminals' },
]

// ── Trance mixer + sound design ──
// Both apply live: faders move the running mix; design changes restart the
// score from the cursor (no rebuild — the score is scheduled, not rendered).
const mix = reactive<MixState>(defaultMix())
const design = reactive<SoundDesign>({ ...DEFAULT_DESIGN })
const entrainments: { id: Entrainment; label: string; hint: string }[] = [
  { id: 'binaural', label: 'Binaural', hint: 'Two tones, one per ear — needs headphones' },
  { id: 'isochronic', label: 'Pulse', hint: 'A soft swell at the beat rate — works on speakers' },
  { id: 'both', label: 'Both', hint: 'Binaural plus the soft swell' },
]
const stemLabel = Object.fromEntries(STEMS.map((s) => [s.id, s.label])) as Record<StemId, string>
const STEM_COLORS: Record<StemId, string> = {
  voice: '#f7f1e6', music: '#fcd34d', waves: '#7dd3fc', binaural: '#a78bfa', heart: '#fb7185', cues: '#86efac',
}

const PRESET_KEY = 'cz-story-mix-presets'
function loadCustomPresets(): MixPreset[] {
  try { return JSON.parse(localStorage.getItem(PRESET_KEY) ?? '[]') as MixPreset[] } catch { return [] }
}
const customPresets = ref<MixPreset[]>(loadCustomPresets())
const activePreset = ref('Balanced')

function applyPreset(p: MixPreset) {
  Object.assign(mix.faders, p.faders)
  Object.assign(design, p.design)
  activePreset.value = p.name
}

const presetName = ref('')
function savePreset() {
  const taken = new Set([...MIX_PRESETS, ...customPresets.value].map((p) => p.name))
  let name = presetName.value.trim() || `My mix ${customPresets.value.length + 1}`
  while (taken.has(name)) name += ' ·'
  presetName.value = ''
  const preset: MixPreset = { name, faders: { ...mix.faders }, design: { ...design } }
  customPresets.value = [...customPresets.value, preset]
  activePreset.value = name
  try { localStorage.setItem(PRESET_KEY, JSON.stringify(customPresets.value)) } catch { /* storage blocked */ }
}

function removePreset(name: string) {
  customPresets.value = customPresets.value.filter((p) => p.name !== name)
  try { localStorage.setItem(PRESET_KEY, JSON.stringify(customPresets.value)) } catch { /* storage blocked */ }
}

function toggleMute(id: StemId) { mix.muted[id] = !mix.muted[id] }
function toggleSolo(id: StemId) { mix.solo = mix.solo === id ? null : id }

const headphoneSide = ref<'left' | 'right' | null>(null)
function checkHeadphones() {
  if (headphoneSide.value) return
  void headphoneCheck((side) => { headphoneSide.value = side })
}

const parsed = computed(() => parseStory(text.value))

// ── Voice source ──
type VoiceMode = 'none' | 'local' | 'pack'
const voiceModes: { id: VoiceMode; label: string }[] = [
  { id: 'none', label: 'Silent' },
  { id: 'local', label: 'On-device voice' },
  { id: 'pack', label: 'ElevenLabs pack' },
]
const voiceMode = ref<VoiceMode>('pack')
const { synthesize, kokoroStatus, enableKokoro } = useVoice()

async function setVoiceMode(mode: VoiceMode) {
  voiceMode.value = mode
  if (mode === 'local' && kokoroStatus.value !== 'ready') await enableKokoro()
}

/** Pack audio by beat id. Survives story edits — unchanged lines keep their audio. */
const clips = shallowRef(new Map<string, VoiceClip>())
const packMeta = ref<PackMeta | null>(null)
const packSkipped = ref<string[]>([])
/** Bumped whenever clips change, so the timeline goes stale. */
const clipsVersion = ref(0)

const voiceable = computed(() => [...new Set(parsed.value.filter((b) => b.text).map((b) => b.id))])
const voiceableCount = computed(() => voiceable.value.length)
const voicedCount = computed(() => (clipsVersion.value, voiceable.value.filter((id) => clips.value.has(id)).length))
const alignedCount = computed(() => (clipsVersion.value, voiceable.value.filter((id) => clips.value.get(id)?.alignment).length))
const scriptChars = computed(() => voiceScript(parsed.value).beats.reduce((n, b) => n + b.text.length, 0))
const scriptFileName = 'story-voice-script.json'

function downloadVoiceScript() {
  const blob = new Blob([JSON.stringify(voiceScript(parsed.value), null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = scriptFileName
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

async function onPackPick(e: Event) {
  const files = [...((e.target as HTMLInputElement).files ?? [])]
  if (!files.length) return
  const { clips: loaded, meta, skipped } = await readPack(files)
  const next = new Map(clips.value)
  loaded.forEach((c, id) => next.set(id, c))
  clips.value = next
  packMeta.value = meta ?? packMeta.value
  packSkipped.value = skipped
  clipsVersion.value++
}

async function onBeatAudio(id: string, e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const next = new Map(clips.value)
    next.set(id, { buffer: await decodeAudioFile(file), alignment: null, name: file.name })
    clips.value = next
    clipsVersion.value++
  } catch {
    buildError.value = `Couldn't decode ${file.name}.`
  }
}

function copyLine(line: string) {
  void navigator.clipboard?.writeText(line).catch(() => { /* clipboard blocked */ })
}

// ── Backdrop library ──
const canvasRef = ref<HTMLCanvasElement>()
const mediaHost = ref<HTMLDivElement>()
const media = shallowRef(new Map<string, StoryMedia>())
let mediaSeq = 0

function onMediaPick(e: Event) {
  const input = e.target as HTMLInputElement
  const files = [...(input.files ?? [])]
  input.value = ''
  if (!files.length) return
  player.stop()
  const next = new Map(media.value)
  for (const file of files) {
    const id = `m${++mediaSeq}`
    const url = URL.createObjectURL(file)
    const item: StoryMedia = file.type.startsWith('image/')
      ? { id, name: file.name, kind: 'image', el: new Image() }
      : { id, name: file.name, kind: 'video', el: document.createElement('video') }
    if (item.el instanceof HTMLVideoElement) {
      const v = item.el
      Object.assign(v, { muted: true, playsInline: true, preload: 'auto', loop: true })
      // Seek a hair in so the first frame decodes for the still preview.
      v.addEventListener('loadedmetadata', () => { v.currentTime = 0.01 }, { once: true })
      v.addEventListener('seeked', () => { sizeCanvas(); drawStill() }, { once: true })
    } else {
      item.el.addEventListener('load', () => { sizeCanvas(); drawStill() }, { once: true })
    }
    item.el.src = url
    mediaHost.value?.appendChild(item.el)
    next.set(id, item)
  }
  media.value = next
}

function removeMedia(id: string) {
  const item = media.value.get(id)
  if (!item) return
  player.stop()
  URL.revokeObjectURL(item.el.src)
  item.el.remove()
  const next = new Map(media.value)
  next.delete(id)
  media.value = next
  styles.value = styles.value.map((st) =>
    st?.backdrop?.kind === 'media' && st.backdrop.mediaId === id ? cleanStyle({ ...st, backdrop: undefined }) : st)
  sizeCanvas()
  drawStill()
}

function sizeCanvas() {
  const c = canvasRef.value
  if (!c) return
  const { w, h } = canvasSizeFor(media.value.values().next().value ?? null)
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h }
}

// ── Beat styles (the per-beat editor) ──
const styles = ref<(BeatStyle | undefined)[]>([])
const selected = ref<number | null>(null)
watch(parsed, (next, prev) => {
  styles.value = remapStyles(prev ?? [], next, styles.value)
  if (selected.value != null && selected.value >= next.length) selected.value = null
})

/** The opening backdrop until a beat picks one: the first library item, else the field. */
const baseBackdrop = computed<Backdrop>(() => {
  const first = media.value.keys().next().value
  return first ? { kind: 'media', mediaId: first } : { kind: 'field' }
})
const scenes = computed(() => resolveScenes(styles.value, parsed.value.length, baseBackdrop.value))
const sceneInput = computed<SceneInput>(() => ({ scenes: scenes.value, media: media.value }))

function setStyle(i: number, patch: Partial<BeatStyle>) {
  const next = [...styles.value]
  next[i] = cleanStyle({ ...next[i], ...patch })
  styles.value = next
}

const PALETTE: { label: string; backdrop: Backdrop }[] = [
  { label: 'Dusk', backdrop: { kind: 'gradient', from: '#2a1a4a', to: '#06050d' } },
  { label: 'Deep sea', backdrop: { kind: 'gradient', from: '#0d3346', to: '#02070d' } },
  { label: 'Ember', backdrop: { kind: 'gradient', from: '#3a160c', to: '#080303' } },
  { label: 'Moss', backdrop: { kind: 'gradient', from: '#123020', to: '#030806' } },
  { label: 'Rose', backdrop: { kind: 'gradient', from: '#3d1834', to: '#0a0410' } },
  { label: 'Night', backdrop: { kind: 'solid', color: '#05050a' } },
]

const places: { id: TextPlace; label: string }[] = [
  { id: 'high', label: 'Top' }, { id: 'middle', label: 'Middle' }, { id: 'low', label: 'Bottom' },
]

/** <select> value for a beat's backdrop. */
function backdropValue(st: BeatStyle | undefined): string {
  const bd = st?.backdrop
  if (!bd) return 'continue'
  return bd.kind === 'media' ? `media:${bd.mediaId}` : bd.kind
}

function onBackdropSelect(i: number, value: string) {
  const current = scenes.value[i]?.backdrop
  let backdrop: Backdrop | undefined
  if (value === 'field') backdrop = { kind: 'field' }
  else if (value === 'solid') backdrop = { kind: 'solid', color: current?.kind === 'gradient' ? current.from : '#120c24' }
  else if (value === 'gradient') backdrop = current?.kind === 'solid' ? { kind: 'gradient', from: current.color, to: '#05050a' } : { ...(PALETTE[0].backdrop as Extract<Backdrop, { kind: 'gradient' }>) }
  else if (value.startsWith('media:')) backdrop = { kind: 'media', mediaId: value.slice(6) }
  setStyle(i, { backdrop })
}

/** CSS background for a backdrop swatch. */
function swatch(bd: Backdrop | undefined): Record<string, string> {
  if (!bd || bd.kind === 'field') return { background: 'radial-gradient(circle, rgba(88,70,160,0.8), #07070c 70%)' }
  if (bd.kind === 'solid') return { background: bd.color }
  if (bd.kind === 'gradient') return { background: `linear-gradient(${bd.from}, ${bd.to})` }
  const m = media.value.get(bd.mediaId)
  return m?.kind === 'image'
    ? { background: `center / cover url("${m.el.src}")` }
    : { background: 'repeating-linear-gradient(135deg, #1e293b 0 6px, #0f172a 6px 12px)' }
}

function backdropLabel(bd: Backdrop | undefined): string {
  if (!bd || bd.kind === 'field') return 'Breathing field'
  if (bd.kind === 'solid') return 'Colour'
  if (bd.kind === 'gradient') return 'Gradient'
  return media.value.get(bd.mediaId)?.name ?? 'Missing clip'
}

function selectBeat(i: number) {
  selected.value = selected.value === i ? null : i
  const tb = freshBeat(i)
  if (tb && selected.value === i) seek(tb.startMs + Math.min(1500, (tb.endMs - tb.startMs) / 3))
}

/** The built beat at index i, only while the timeline matches the story. */
function freshBeat(i: number) {
  return !stale.value ? timeline.value?.beats[i] ?? null : null
}

// ── Build: parse → voice → timeline (the score is scheduled at play time) ──
const timeline = shallowRef<Timeline | null>(null)
const voices = shallowRef<(AudioBuffer | null)[]>([])
const building = ref(false)
const buildStep = ref('')
const buildError = ref('')
const builtKey = ref('')
/** The style fields that change timing (draw-only ones preview without a rebuild). */
const timingStyles = computed(() => parsed.value.map((_, i) => [styles.value[i]?.effect, styles.value[i]?.holdMs]))
const inputKey = computed(() => JSON.stringify([text.value, wpm.value, voiceMode.value, clipsVersion.value, kokoroStatus.value, look.value, timingStyles.value]))
const stale = computed(() => !timeline.value || builtKey.value !== inputKey.value)

async function build() {
  building.value = true
  buildError.value = ''
  const key = inputKey.value
  try {
    await loadEffectFonts()
    const beats = parseStory(text.value)
    const voiced: (AudioBuffer | null)[] = beats.map(() => null)
    const alignments: (Alignment | null)[] = beats.map(() => null)
    if (voiceMode.value === 'pack') {
      beats.forEach((b, i) => {
        const clip = b.text ? clips.value.get(b.id) : undefined
        if (clip) { voiced[i] = clip.buffer; alignments[i] = clip.alignment }
      })
    } else if (voiceMode.value === 'local' && kokoroStatus.value === 'ready') {
      for (let i = 0; i < beats.length; i++) {
        if (!beats[i].text) continue
        buildStep.value = `Voicing beat ${i + 1} of ${beats.length}…`
        const raw = await synthesize(beats[i].text)
        if (raw) voiced[i] = voiceBuffer(raw.audio, raw.sampling_rate)
      }
    }
    const tl = buildTimeline(beats, {
      wpm: wpm.value,
      look: look.value,
      effects: beats.map((_, i) => styles.value[i]?.effect),
      holdMs: beats.map((_, i) => styles.value[i]?.holdMs),
      voiceMs: voiced.map((v) => (v ? v.duration * 1000 : null)),
      alignments,
    })
    voices.value = voiced
    timeline.value = tl
    builtKey.value = key
    cursorMs.value = Math.min(cursorMs.value, tl.durationMs)
    await nextTick()
    sizeCanvas()
    drawStill()
  } catch (err) {
    console.error('[story] build failed', err)
    buildError.value = 'Building the timeline failed. Try a shorter story, or a different voice source.'
  } finally {
    building.value = false
  }
}

// ── Playback ──
const player = useStoryPlayer()
const isPlaying = computed(() => player.state.value === 'playing')
const isRecording = computed(() => player.state.value === 'recording')
const cursorMs = ref(0)

const frameOptions = computed<FrameOptions>(() => ({
  captions: captions.value,
  credit: voiceMode.value === 'pack' && credit.value && voicedCount.value > 0 ? 'Voice: ElevenLabs' : undefined,
}))

watch(player.clockMs, (t) => { if (player.state.value !== 'idle') cursorMs.value = t })
watch([frameOptions, sceneInput], () => drawStill())

// ── Audio-only export ──
const exportingWav = ref(false)
async function exportWav() {
  if (!timeline.value || !automation.value || exportingWav.value) return
  exportingWav.value = true
  try {
    const buf = await renderMixdown({
      timeline: timeline.value, voices: voices.value, design: snapshot(design), mix: snapshot(mix),
      automation: automation.value, fadeS: STORY_FADE_S,
    })
    const url = URL.createObjectURL(encodeWav(buf))
    const a = document.createElement('a')
    a.href = url
    a.download = 'channelzero-story.wav'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch (err) {
    console.error('[story] wav export failed', err)
    buildError.value = 'The audio export failed.'
  } finally {
    exportingWav.value = false
  }
}

// ── Level lanes: what each bed actually does across the story ──
/** One stacked lane per bed: its level (stage arc × beat balance × fader) as a filled curve. */
const LANE_H = 10
const lanes = computed(() => {
  const tl = timeline.value
  const auto = automation.value
  if (!tl || !auto) return []
  const W = 1000
  return BED_STEMS.map((id, row) => {
    const g = stemGain(mix, id, design.comfort)
    const pts = auto[id]
    const base = (row + 1) * LANE_H
    const xs = [...new Set([0, tl.durationMs, ...pts.map((p) => p.tMs)])].sort((a, b) => a - b)
    const coords = xs.map((t) => {
      const v = Math.min(1, autoValueAt(pts, t) * g)
      return `${((t / tl.durationMs) * W).toFixed(1)},${(base - v * (LANE_H - 1)).toFixed(2)}`
    })
    const line = `M${coords.join(' L')}`
    return { id, line, area: `${line} L${W},${base} L0,${base} Z`, color: STEM_COLORS[id] }
  })
})

function setBeatSound(i: number, id: BedStem, value: number | undefined) {
  const sound = { ...styles.value[i]?.sound }
  if (value == null) delete sound[id]
  else sound[id] = value
  setStyle(i, { sound })
}
const beatSoundResolved = computed(() => resolveBeatSound(styles.value.map((s) => s?.sound), parsed.value.length))

function drawStill() {
  const c = canvasRef.value
  const tl = timeline.value
  const ctx = c?.getContext('2d')
  if (!ctx || !tl || player.state.value !== 'idle') return
  drawStoryFrame(ctx, tl, cursorMs.value, sceneInput.value, frameOptions.value)
}

/** Stage × beat level curves for the beds, from the built timeline and the beat editor. */
const automation = computed(() => {
  const tl = timeline.value
  if (!tl) return null
  return buildAutomation(tl, resolveBeatSound(tl.beats.map((_, i) => styles.value[i]?.sound), tl.beats.length))
})

const snapshot = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

// Faders, mute and solo move the running mix; design and automation changes
// re-schedule the score from where it is.
watch(mix, () => player.setMix(snapshot(mix), design.comfort), { deep: true })
watch([() => JSON.stringify(design), automation], () => {
  if (isPlaying.value) start({ record: false })
})
watch(() => design.comfort, (on) => {
  if (on && mix.faders.binaural > COMFORT_ENTRAINMENT_MAX) mix.faders.binaural = COMFORT_ENTRAINMENT_MAX
})

function start(opts: { record: boolean }) {
  if (!timeline.value || !automation.value || !canvasRef.value) return
  void player.play({
    canvas: canvasRef.value,
    scene: sceneInput.value,
    timeline: timeline.value,
    voices: voices.value,
    design: snapshot(design),
    mix: snapshot(mix),
    automation: automation.value,
    frame: frameOptions.value,
    record: opts.record,
    fromMs: cursorMs.value >= timeline.value.durationMs - 500 ? 0 : cursorMs.value,
  })
}

function togglePlay() {
  if (isPlaying.value) { player.stop(); drawStill() }
  else start({ record: false })
}

function record() {
  cursorMs.value = 0
  start({ record: true })
}

function seek(ms: number) {
  if (!timeline.value || isRecording.value) return
  cursorMs.value = Math.max(0, Math.min(ms, timeline.value.durationMs))
  if (isPlaying.value) start({ record: false })
  else drawStill()
}

function onBarClick(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  seek(((e.clientX - r.left) / r.width) * (timeline.value?.durationMs ?? 0))
}

const currentBeat = computed(() => (timeline.value ? beatIndexAt(timeline.value, cursorMs.value) : -1))
const beatHzLabel = computed(() => {
  if (!timeline.value) return ''
  return `${entrainmentAt(timeline.value, cursorMs.value).beatHz.toFixed(1)} Hz beat`
})
const keysByBeat = computed(() => {
  const m = new Map<number, TimedKey[]>()
  for (const k of timeline.value?.keys ?? []) m.set(k.beat, [...(m.get(k.beat) ?? []), k])
  return m
})
const flashRate = computed(() => (timeline.value ? maxFlashesPerSecond(timeline.value.keys, timeline.value.subliminals) : 0))

const pct = (ms: number) => `${(ms / (timeline.value?.durationMs || 1)) * 100}%`
const exportExt = typeof MediaRecorder !== 'undefined' && pickMime().startsWith('video/mp4') ? 'MP4' : 'WebM'

onMounted(() => { void loadEffectFonts() })
onUnmounted(() => {
  player.stop()
  media.value.forEach((m) => URL.revokeObjectURL(m.el.src))
})
</script>

<style scoped>
.chip {
  @apply px-3 py-1.5 rounded-full border border-white/10 bg-white/[0.03] text-slate-400 text-xs tracking-wide transition-colors;
}
.chip:hover:not(:disabled) { @apply bg-white/[0.08] text-slate-200; }
.chip:disabled { @apply opacity-40 cursor-not-allowed; }
.chip--on { @apply bg-white/10 border-white/25 text-white/90; }
.chip--rec { @apply border-rose-400/30 text-rose-200/80; }

.link { @apply text-slate-300 underline decoration-white/20 underline-offset-2 hover:decoration-white/60; }

.field { @apply flex flex-col gap-1.5 text-slate-500; }
.select { @apply w-full px-2 py-1.5 rounded-md bg-white/[0.04] border border-white/[0.08] text-slate-300 text-xs focus:outline-none focus:border-white/25; }
.select option { background: #111; }
.color { @apply w-10 h-7 rounded border border-white/10 bg-transparent cursor-pointer; }
.chip--inherited { @apply border-dashed; }
.ms { @apply w-5 h-5 rounded text-[10px] border border-white/10 text-slate-500 hover:text-slate-200; }
.ms--mute { @apply bg-rose-500/30 border-rose-400/40 text-rose-100; }
.ms--solo { @apply bg-amber-400/30 border-amber-300/40 text-amber-100; }

.stage-chip { @apply text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded text-black/80; }
.stage-induce   { background: #7dd3fc; }
.stage-deepen   { background: #818cf8; }
.stage-emerge   { background: #fcd34d; }
.stage-reinduce { background: #a78bfa; }
.stage-final    { background: #4c1d95; color: #e9d5ff; }
.stage-wake     { background: #86efac; }
</style>
