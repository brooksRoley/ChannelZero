<template>
  <div class="min-h-screen bg-black text-lime-400 p-6 lg:p-10 font-mono">
    <header class="mb-10 border-b border-lime-800 pb-4 flex items-baseline justify-between gap-4">
      <div>
        <h1 class="text-2xl lg:text-3xl font-bold tracking-tighter uppercase">Psychological Profile</h1>
        <p class="text-lime-600 mt-1 text-xs tracking-widest uppercase">The architecture of your resonance</p>
      </div>
      <div v-if="oauthState" class="flex flex-wrap gap-2 justify-end">
        <span
          v-for="p in connectedProviders"
          :key="p"
          class="text-[9px] uppercase tracking-widest border border-lime-800 px-2 py-0.5 text-lime-600"
        >{{ p }}</span>
      </div>
    </header>

    <!-- ── Assessment Form ──────────────────────────────────────── -->
    <div v-if="!profile && !loading" class="max-w-2xl mx-auto">

      <!-- Microdose celebration -->
      <div v-if="tranceCount > 0 && !allItemsDone" class="mb-6 border border-purple-800/50 bg-purple-950/20 p-4">
        <p class="text-xs text-purple-400 leading-relaxed">
          Your trance sessions already captured some insights — let's fill in the rest.
        </p>
      </div>

      <!-- Progress header -->
      <div class="mb-8">
        <div class="flex justify-between mb-1 text-[10px] uppercase tracking-widest">
          <span class="text-lime-700">{{ totalAnswered }} / {{ TOTAL_ITEMS }} items completed</span>
          <span v-if="tranceCount > 0" class="text-purple-600">{{ tranceCount }} answered during trance</span>
        </div>
        <div
          class="h-1 bg-lime-950 rounded-full overflow-hidden"
          role="progressbar"
          :aria-valuenow="totalAnswered"
          aria-valuemin="0"
          :aria-valuemax="TOTAL_ITEMS"
          :aria-label="`Assessment progress: ${totalAnswered} of ${TOTAL_ITEMS} items completed`"
        >
          <div
            class="h-full rounded-full transition-all duration-700"
            :style="{ width: `${(totalAnswered / TOTAL_ITEMS) * 100}%`, background: 'linear-gradient(90deg, #a855f7, #a3e635)' }"
          />
        </div>
      </div>

      <!-- Step indicator -->
      <div class="mb-8">
        <div class="flex justify-between mb-2 text-[10px] text-lime-700 uppercase tracking-widest">
          <span>{{ STEP_LABELS[step] }}</span>
          <span>{{ step + 1 }} / {{ STEP_LABELS.length }}</span>
        </div>
        <div
          class="h-px bg-lime-900"
          role="progressbar"
          :aria-valuenow="step"
          aria-valuemin="0"
          :aria-valuemax="STEP_LABELS.length - 1"
          :aria-label="`Step ${step + 1} of ${STEP_LABELS.length}: ${STEP_LABELS[step]}`"
        >
          <div class="h-px bg-lime-500 transition-all duration-500" :style="{ width: `${(step / (STEP_LABELS.length - 1)) * 100}%` }" />
        </div>
      </div>

      <!-- Step 0 — OCEAN (Big Five) -------------------------------- -->
      <div v-if="step === 0" class="space-y-8">
        <!-- Collapsed state if all OCEAN items done -->
        <div v-if="oceanStepComplete" class="border border-lime-800/50 bg-lime-950/10 p-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-lime-500 text-sm">&#10003;</span>
              <span class="text-xs text-lime-500 uppercase tracking-widest">Personality — Completed</span>
            </div>
            <button class="text-[10px] text-lime-700 hover:text-lime-500 uppercase tracking-widest focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500" @click="expandOcean = !expandOcean">
              {{ expandOcean ? 'Collapse' : 'Review' }}
            </button>
          </div>
          <div v-if="expandOcean" class="mt-4 space-y-3">
            <div v-for="(item, i) in OCEAN_ITEMS" :key="i" class="flex items-center justify-between text-xs">
              <span class="text-lime-600">{{ item.text }}</span>
              <span class="text-lime-400 font-semibold ml-2 shrink-0">{{ oceanAnswers[i] }}</span>
            </div>
          </div>
        </div>

        <!-- Interactive state -->
        <template v-else>
          <p class="text-xs text-lime-600 italic">Rate how accurately each statement describes you. 1 = Not at all · 5 = Very much</p>
          <div v-for="(item, i) in OCEAN_ITEMS" :key="i" class="space-y-2">
            <!-- Pre-answered via microdose -->
            <div v-if="isOceanMicrodosed(i)" class="flex items-center gap-3 opacity-80">
              <span class="text-purple-500 text-sm shrink-0">&#10003;</span>
              <div class="flex-1">
                <p class="text-sm text-lime-500">{{ item.text }}</p>
                <p class="text-[9px] text-purple-600 mt-0.5">answered during trance — {{ oceanAnswers[i] }}/5</p>
              </div>
              <div class="flex gap-1">
                <span
                  v-for="n in 5"
                  :key="n"
                  :aria-label="`Rate ${n} of 5 — ${item.text}`"
                  :class="[
                    'w-7 h-7 flex items-center justify-center border text-[10px]',
                    oceanAnswers[i] === n
                      ? 'border-purple-500 bg-purple-900/40 text-purple-300'
                      : 'border-lime-950 text-lime-900'
                  ]"
                >{{ n }}</span>
              </div>
            </div>
            <!-- Normal interactive item -->
            <template v-else>
              <p class="text-sm text-lime-300">{{ item.text }}</p>
              <div class="flex gap-3">
                <button
                  v-for="n in 5"
                  :key="n"
                  :aria-label="`Rate ${n} of 5 — ${item.text}`"
                  :class="[
                    'w-9 h-9 border text-xs transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500',
                    oceanAnswers[i] === n
                      ? 'border-lime-400 bg-lime-900/60 text-lime-200'
                      : 'border-lime-900 text-lime-700 hover:border-lime-600 hover:text-lime-400'
                  ]"
                  @click="oceanAnswers[i] = n"
                >{{ n }}</button>
              </div>
            </template>
          </div>
        </template>
        <button
          :disabled="!oceanComplete"
          class="w-full border border-lime-600 p-3 text-xs uppercase tracking-widest transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:bg-lime-900/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500"
          @click="step++"
        >Continue &#8594;</button>
      </div>

      <!-- Step 1 — Attachment (ECR-R short form) ------------------ -->
      <div v-if="step === 1" class="space-y-8">
        <!-- Collapsed state if all attachment items done -->
        <div v-if="attachStepComplete" class="border border-lime-800/50 bg-lime-950/10 p-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-lime-500 text-sm">&#10003;</span>
              <span class="text-xs text-lime-500 uppercase tracking-widest">Attachment — Completed</span>
            </div>
            <button class="text-[10px] text-lime-700 hover:text-lime-500 uppercase tracking-widest focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500" @click="expandAttach = !expandAttach">
              {{ expandAttach ? 'Collapse' : 'Review' }}
            </button>
          </div>
          <div v-if="expandAttach" class="mt-4 space-y-3">
            <div v-for="(item, i) in ATTACHMENT_ITEMS" :key="i" class="flex items-center justify-between text-xs">
              <span class="text-lime-600">{{ item.text }}</span>
              <span class="text-lime-400 font-semibold ml-2 shrink-0">{{ attachAnswers[i] }}/7</span>
            </div>
          </div>
        </div>

        <!-- Interactive state -->
        <template v-else>
          <p class="text-xs text-lime-600 italic">Rate how much each statement describes your feelings in close relationships. 1 = Disagree strongly · 7 = Agree strongly</p>
          <div v-for="(item, i) in ATTACHMENT_ITEMS" :key="i" class="space-y-2">
            <!-- Pre-answered via microdose -->
            <div v-if="isAttachMicrodosed(i)" class="flex items-center gap-3 opacity-80">
              <span class="text-purple-500 text-sm shrink-0">&#10003;</span>
              <div class="flex-1">
                <p class="text-sm text-lime-500">{{ item.text }}</p>
                <p class="text-[9px] text-purple-600 mt-0.5">answered during trance — {{ attachAnswers[i] }}/7</p>
              </div>
              <div class="flex gap-1">
                <span
                  v-for="n in 7"
                  :key="n"
                  :aria-label="`Rate ${n} of 7 — ${item.text}`"
                  :class="[
                    'w-6 h-6 flex items-center justify-center border text-[9px]',
                    attachAnswers[i] === n
                      ? 'border-purple-500 bg-purple-900/40 text-purple-300'
                      : 'border-lime-950 text-lime-900'
                  ]"
                >{{ n }}</span>
              </div>
            </div>
            <!-- Normal interactive item -->
            <template v-else>
              <p class="text-sm text-lime-300">{{ item.text }}</p>
              <div class="flex gap-2">
                <button
                  v-for="n in 7"
                  :key="n"
                  :aria-label="`Rate ${n} of 7 — ${item.text}`"
                  :class="[
                    'w-9 h-9 border text-xs transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500',
                    attachAnswers[i] === n
                      ? 'border-lime-400 bg-lime-900/60 text-lime-200'
                      : 'border-lime-900 text-lime-700 hover:border-lime-600 hover:text-lime-400'
                  ]"
                  @click="attachAnswers[i] = n"
                >{{ n }}</button>
              </div>
            </template>
          </div>
        </template>
        <div class="flex gap-3">
          <button class="flex-1 border border-lime-900 p-3 text-xs uppercase tracking-widest hover:bg-lime-900/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500" @click="step--">&#8592; Back</button>
          <button
            :disabled="!attachmentComplete"
            class="flex-1 border border-lime-600 p-3 text-xs uppercase tracking-widest transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:bg-lime-900/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500"
            @click="step++"
          >Continue &#8594;</button>
        </div>
      </div>

      <!-- Step 2 — Identity --------------------------------------- -->
      <div v-if="step === 2" class="space-y-6">
        <!-- Collapsed state if all identity items done -->
        <div v-if="identityStepComplete && identityAllMicrodosed" class="border border-lime-800/50 bg-lime-950/10 p-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-lime-500 text-sm">&#10003;</span>
              <span class="text-xs text-lime-500 uppercase tracking-widest">Identity — Completed</span>
            </div>
            <button class="text-[10px] text-lime-700 hover:text-lime-500 uppercase tracking-widest focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500" @click="expandIdentity = !expandIdentity">
              {{ expandIdentity ? 'Collapse' : 'Review' }}
            </button>
          </div>
          <div v-if="expandIdentity" class="mt-4 space-y-2 text-xs">
            <div class="flex justify-between"><span class="text-lime-600">Love Language</span><span class="text-lime-400">{{ form.love_language }}</span></div>
            <div class="flex justify-between"><span class="text-lime-600">Values</span><span class="text-lime-400">{{ form.values_cluster }}</span></div>
            <div class="flex justify-between"><span class="text-lime-600">Sociosexual</span><span class="text-lime-400">{{ form.sociosexual }}</span></div>
          </div>
        </div>

        <!-- Interactive state -->
        <template v-else>
          <p class="text-xs text-lime-600 italic">Three signals that refine your compatibility coordinates.</p>

          <div>
            <div class="flex items-center gap-2 mb-2">
              <label class="text-xs text-lime-600 uppercase tracking-wider">Primary Love Language</label>
              <span v-if="microdosedItemIds.has('identity_love_language')" class="text-[9px] text-purple-600">&#10003; trance</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                v-for="ll in LOVE_LANGUAGES"
                :key="ll"
                :class="[
                  'p-3 border text-left text-xs transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500',
                  form.love_language === ll
                    ? (microdosedItemIds.has('identity_love_language') ? 'border-purple-500 bg-purple-900/30 text-purple-200' : 'border-lime-400 bg-lime-900/50 text-lime-200')
                    : 'border-lime-900 text-lime-600 hover:border-lime-700 hover:text-lime-400'
                ]"
                @click="form.love_language = ll"
              >{{ ll }}</button>
            </div>
          </div>

          <div>
            <div class="flex items-center gap-2 mb-2">
              <label class="text-xs text-lime-600 uppercase tracking-wider">Values Cluster</label>
              <span v-if="microdosedItemIds.has('identity_values')" class="text-[9px] text-purple-600">&#10003; trance</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                v-for="vc in VALUES_CLUSTERS"
                :key="vc"
                :class="[
                  'p-3 border text-left text-xs transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500',
                  form.values_cluster === vc
                    ? (microdosedItemIds.has('identity_values') ? 'border-purple-500 bg-purple-900/30 text-purple-200' : 'border-lime-400 bg-lime-900/50 text-lime-200')
                    : 'border-lime-900 text-lime-600 hover:border-lime-700 hover:text-lime-400'
                ]"
                @click="form.values_cluster = vc"
              >{{ vc }}</button>
            </div>
          </div>

          <div>
            <div class="flex items-center gap-2 mb-2">
              <label class="text-xs text-lime-600 uppercase tracking-wider">Sociosexual Orientation</label>
              <span v-if="microdosedItemIds.has('identity_sociosexual')" class="text-[9px] text-purple-600">&#10003; trance</span>
            </div>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="so in SOCIOSEXUAL_OPTIONS"
                :key="so.value"
                :class="[
                  'p-3 border text-xs transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500',
                  form.sociosexual === so.value
                    ? (microdosedItemIds.has('identity_sociosexual') ? 'border-purple-500 bg-purple-900/30 text-purple-200' : 'border-lime-400 bg-lime-900/50 text-lime-200')
                    : 'border-lime-900 text-lime-600 hover:border-lime-700 hover:text-lime-400'
                ]"
                @click="form.sociosexual = so.value"
              >
                <div class="font-semibold">{{ so.label }}</div>
                <div class="text-[9px] mt-0.5 opacity-70">{{ so.sub }}</div>
              </button>
            </div>
          </div>
        </template>

        <div class="flex gap-3 pt-2">
          <button class="flex-1 border border-lime-900 p-3 text-xs uppercase tracking-widest hover:bg-lime-900/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500" @click="step--">&#8592; Back</button>
          <button
            :disabled="!identityComplete"
            class="flex-1 border border-lime-600 p-3 text-xs uppercase tracking-widest transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:bg-lime-900/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500"
            @click="submitAssessment"
          >{{ submitting ? 'Synchronizing...' : 'Initialize Sync' }}</button>
        </div>
      </div>
    </div>

    <!-- ── Loading ─────────────────────────────────────────────── -->
    <div v-else-if="loading" class="flex items-center justify-center py-32">
      <div class="text-center space-y-3">
        <div class="w-px h-12 bg-lime-800 mx-auto animate-pulse" />
        <p class="text-xs text-lime-700 uppercase tracking-widest">Loading profile...</p>
      </div>
    </div>

    <!-- ── Dashboard ───────────────────────────────────────────── -->
    <div v-else-if="profile" class="grid grid-cols-1 lg:grid-cols-2 gap-8">

      <!-- Left column -->
      <div class="space-y-8">

        <!-- OCEAN Cosmic Radar (canvas) -->
        <section class="border border-lime-800 p-6 bg-black/30">
          <h2 class="text-lg mb-4 text-white uppercase tracking-widest text-center">Personality Observatory</h2>
          <div class="flex justify-center py-4">
            <div
              v-if="isLoadingScores"
              class="animate-pulse rounded-full bg-white/10"
              style="width: 320px; height: 320px;"
              role="status"
              aria-label="Loading personality scores"
            ></div>
            <RadarCanvas v-else :size="320" :scores="radarCanvasScores" />
          </div>
        </section>

        <!-- OCEAN Radar -->
        <section class="border border-lime-800 p-6 bg-black/30">
          <h2 class="text-lg mb-4 text-white uppercase tracking-widest text-center">OCEAN Signature</h2>
          <div class="flex justify-center py-4">
            <svg width="240" height="240" viewBox="0 0 200 200" class="overflow-visible">
              <polygon points="100,20 176,75 147,164 53,164 24,75" fill="none" stroke="#1a2e1a" stroke-width="1"/>
              <polygon points="100,60 138,87 123,132 77,132 62,87" fill="none" stroke="#1a2e1a" stroke-width="1"/>
              <line x1="100" y1="100" x2="100" y2="20" stroke="#1a2e1a"/>
              <line x1="100" y1="100" x2="176" y2="75" stroke="#1a2e1a"/>
              <line x1="100" y1="100" x2="147" y2="164" stroke="#1a2e1a"/>
              <line x1="100" y1="100" x2="53" y2="164" stroke="#1a2e1a"/>
              <line x1="100" y1="100" x2="24" y2="75" stroke="#1a2e1a"/>
              <polygon :points="radarPoints" fill="rgba(163,230,53,0.18)" stroke="#a3e635" stroke-width="1.5"/>
              <!-- Axis labels positioned outside the pentagon -->
              <text x="100" y="10" fill="#4d7c0f" font-size="7" text-anchor="middle" class="uppercase">Openness</text>
              <text x="186" y="78" fill="#4d7c0f" font-size="7" text-anchor="start" class="uppercase">Consci.</text>
              <text x="155" y="178" fill="#4d7c0f" font-size="7" text-anchor="middle" class="uppercase">Extra.</text>
              <text x="45" y="178" fill="#4d7c0f" font-size="7" text-anchor="middle" class="uppercase">Agree.</text>
              <text x="14" y="78" fill="#4d7c0f" font-size="7" text-anchor="end" class="uppercase">Neuro.</text>
            </svg>
          </div>
          <!-- Score bars with interpretations -->
          <div class="space-y-2 mt-2">
            <div v-for="trait in oceanTraits" :key="trait.key" class="space-y-0.5">
              <div class="flex justify-between text-xs">
                <span class="text-lime-600">{{ trait.label }}</span>
                <span class="text-white tabular-nums">{{ pct(trait.score) }}%</span>
              </div>
              <div class="h-px bg-lime-950">
                <div class="h-px bg-lime-500 transition-all duration-700" :style="{ width: pct(trait.score) + '%' }" />
              </div>
              <p class="text-[9px] text-lime-800 italic">{{ trait.interp }}</p>
            </div>
          </div>
        </section>

        <!-- What Your Profile Reveals -->
        <section class="border border-lime-800 p-6 bg-black/30">
          <h2 class="text-lg mb-3 text-white uppercase tracking-widest">What This Reveals</h2>
          <div class="space-y-4 text-xs text-lime-600 leading-relaxed">
            <div v-if="profile?.ocean_scores">
              <span class="text-lime-500 uppercase tracking-wider block mb-1">Your drive pattern</span>
              <p>{{ drivePatternSummary }}</p>
            </div>
            <div v-if="profile?.ecr_r_scores">
              <span class="text-lime-500 uppercase tracking-wider block mb-1">How you attach</span>
              <p>{{ attachmentSummary }}</p>
            </div>
            <div v-if="profile?.love_language">
              <span class="text-lime-500 uppercase tracking-wider block mb-1">How you receive care</span>
              <p>{{ profile.love_language }} — this shapes what feels like love to you, and what goes unnoticed.</p>
            </div>
          </div>
          <p class="mt-4 text-[10px] text-lime-800 italic leading-relaxed">
            Connect more data sources in Calibrate to deepen this read.
          </p>
        </section>
      </div>

      <!-- Right column -->
      <div class="space-y-8">

        <!-- Attachment Matrix -->
        <section class="border border-lime-800 p-6 bg-black/30">
          <h2 class="text-lg mb-2 text-white uppercase tracking-widest text-center">Attachment Matrix</h2>
          <p class="text-center text-[10px] text-lime-600 mb-4 uppercase tracking-widest">
            {{ attachmentStyleLabel }}
          </p>
          <div class="relative w-full aspect-square max-w-[260px] mx-auto border border-lime-900 bg-lime-950/10">
            <div class="absolute inset-y-0 left-1/2 w-px bg-lime-900"/>
            <div class="absolute inset-x-0 top-1/2 h-px bg-lime-900"/>
            <!-- Quadrant labels -->
            <span class="absolute top-2 left-2 text-[8px] text-lime-900 uppercase">Anxious-Preoccupied</span>
            <span class="absolute top-2 right-2 text-[8px] text-lime-900 uppercase text-right">Fearful-Avoidant</span>
            <span class="absolute bottom-2 left-2 text-[8px] text-lime-900 uppercase">Secure</span>
            <span class="absolute bottom-2 right-2 text-[8px] text-lime-900 uppercase text-right">Dismissive</span>
            <!-- Axis labels -->
            <span class="absolute top-1/2 left-1 -translate-y-1/2 text-[7px] text-lime-800 -rotate-90 origin-center whitespace-nowrap" style="transform: translateY(-50%) translateX(-28px) rotate(-90deg)">Anxiety &#8594;</span>
            <span class="absolute bottom-1 left-1/2 -translate-x-1/2 text-[7px] text-lime-800 whitespace-nowrap">Avoidance &#8594;</span>
            <!-- Plot point -->
            <div
              class="absolute w-3 h-3 bg-lime-400 rounded-full shadow-[0_0_10px_#a3e635] transition-all duration-1000"
              :style="{
                left: `${profile.ecr_r_scores.avoidance * 100}%`,
                top: `${(1 - profile.ecr_r_scores.anxiety) * 100}%`,
                transform: 'translate(-50%,-50%)'
              }"
            />
          </div>
          <!-- Numerical scores -->
          <div class="mt-4 grid grid-cols-2 gap-4 text-xs">
            <div>
              <span class="text-lime-600 uppercase tracking-wider block mb-0.5">Anxiety</span>
              <div class="h-px bg-lime-950 mt-1">
                <div class="h-px bg-blue-600 transition-all duration-700" :style="{ width: pct(profile.ecr_r_scores.anxiety) + '%' }"/>
              </div>
              <span class="text-white text-[10px]">{{ pct(profile.ecr_r_scores.anxiety) }}%</span>
            </div>
            <div>
              <span class="text-lime-600 uppercase tracking-wider block mb-0.5">Avoidance</span>
              <div class="h-px bg-lime-950 mt-1">
                <div class="h-px bg-purple-600 transition-all duration-700" :style="{ width: pct(profile.ecr_r_scores.avoidance) + '%' }"/>
              </div>
              <span class="text-white text-[10px]">{{ pct(profile.ecr_r_scores.avoidance) }}%</span>
            </div>
          </div>
        </section>

        <!-- Qualitative signals -->
        <section class="border border-lime-800 p-6 bg-black/30 grid grid-cols-2 gap-4 text-xs">
          <div>
            <span class="text-lime-600 uppercase tracking-wider block mb-1">Love Language</span>
            <span class="text-white font-semibold">{{ profile.love_language }}</span>
          </div>
          <div>
            <span class="text-lime-600 uppercase tracking-wider block mb-1">Values Cluster</span>
            <span class="text-white font-semibold">{{ profile.values_cluster }}</span>
          </div>
          <div class="col-span-2 pt-3 border-t border-lime-900/50">
            <span class="text-lime-600 uppercase tracking-wider block mb-1">Sociosexual Orientation</span>
            <span class="text-white font-semibold">{{ profile.sociosexual_orientation }}</span>
          </div>
        </section>

        <!-- Agent Synthesis -->
        <section class="border border-lime-800 p-6 bg-lime-900/5 relative overflow-hidden group">
          <div class="absolute inset-0 bg-lime-500/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"/>
          <div class="flex justify-between items-center mb-4 relative z-10">
            <h2 class="text-lg text-white uppercase tracking-widest">Agent Synthesis</h2>
            <button
              v-if="!profile.narrative && !generating"
              class="text-[10px] border border-lime-600 px-4 py-2 hover:bg-lime-900 text-lime-400 transition-all uppercase tracking-widest focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-500"
              @click="generateNarrative"
            >Initiate</button>
            <span v-else-if="generating" class="text-[10px] text-lime-500 animate-pulse uppercase tracking-widest">Synthesizing...</span>
          </div>

          <div v-if="profile.narrative" class="text-sm text-lime-300 leading-relaxed whitespace-pre-line relative z-10">
            {{ profile.narrative }}
          </div>
          <div v-else-if="generating" class="text-[10px] text-lime-800 font-mono italic space-y-1 relative z-10">
            <p>// Cross-referencing ECR-R vectors with OCEAN signatures</p>
            <p>// Injecting behavioral telemetry ({{ connectedProviders.join(', ') || 'none connected' }})</p>
            <p>// Awaiting Anthropic synthesis...</p>
          </div>
          <p v-else class="text-xs text-lime-800 italic relative z-10">
            No synthesis available. Click Initiate to construct a personalized narrative.
          </p>
          <p v-if="narrativeError" class="text-red-400 text-xs mt-2 font-mono italic">{{ narrativeError }}</p>
        </section>
      </div>
    </div>

    <!-- ── Continue your practice CTA ──────────────────────── -->
    <div class="mt-16 border-t border-lime-900/40 pt-12 max-w-2xl mx-auto">
      <p class="text-[10px] text-lime-800 uppercase tracking-widest text-center mb-8">Continue your practice</p>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <router-link
          to="/journal"
          class="block border border-lime-800/60 p-5 hover:border-lime-600 hover:bg-lime-900/20 transition-all group focus-visible:ring-2 focus-visible:ring-lime-500 focus-visible:outline-none"
        >
          <span class="text-xl mb-2 block">✍</span>
          <span class="text-xs uppercase tracking-widest text-lime-500 block group-hover:text-lime-300 transition-colors">Journal</span>
          <span class="text-[10px] text-lime-800 mt-1 block">Capture what's surfacing</span>
        </router-link>
        <router-link
          to="/zeromind"
          class="block border border-lime-800/60 p-5 hover:border-lime-600 hover:bg-lime-900/20 transition-all group focus-visible:ring-2 focus-visible:ring-lime-500 focus-visible:outline-none"
        >
          <span class="text-xl mb-2 block">◎</span>
          <span class="text-xs uppercase tracking-widest text-lime-500 block group-hover:text-lime-300 transition-colors">Zeromind</span>
          <span class="text-[10px] text-lime-800 mt-1 block">Enter trance — let this settle</span>
        </router-link>
        <!-- Portrait CTA when 2+ providers unlocked; Calibrate nudge otherwise -->
        <router-link
          v-if="connectedProviders.length >= 2"
          to="/portrait"
          class="block border border-indigo-800/60 p-5 hover:border-indigo-600 hover:bg-indigo-900/20 transition-all group focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
        >
          <span class="text-xl mb-2 block">◉</span>
          <span class="text-xs uppercase tracking-widest text-indigo-400 block group-hover:text-indigo-200 transition-colors">Your Portrait</span>
          <span class="text-[10px] text-indigo-800 mt-1 block">Read what your data reveals</span>
        </router-link>
        <router-link
          v-else
          to="/calibrate"
          class="block border border-lime-800/60 p-5 hover:border-lime-600 hover:bg-lime-900/20 transition-all group focus-visible:ring-2 focus-visible:ring-lime-500 focus-visible:outline-none"
        >
          <span class="text-xl mb-2 block">◈</span>
          <span class="text-xs uppercase tracking-widest text-lime-500 block group-hover:text-lime-300 transition-colors">Calibrate</span>
          <span class="text-[10px] text-lime-800 mt-1 block">Connect 2 sources to unlock your Portrait</span>
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useVibeStore } from '@/composables/useVibeStore'
import RadarCanvas from '@/components/RadarCanvas.vue'

// ── Constants ──────────────────────────────────────────────────────
const STEP_LABELS = ['Personality', 'Attachment', 'Identity']
const TOTAL_ITEMS = 17

// Big Five: 2 items per trait, scored 1–5
const OCEAN_ITEMS = [
  { text: 'I have a rich imagination and love exploring abstract ideas.', trait: 'O' },
  { text: 'I am quick to understand new concepts and enjoy intellectual challenges.', trait: 'O' },
  { text: 'I am always prepared and like to plan things in advance.', trait: 'C' },
  { text: 'I pay attention to detail and follow through on commitments.', trait: 'C' },
  { text: 'I love being around people and am the life of the party.', trait: 'E' },
  { text: 'I feel energized after spending time in social settings.', trait: 'E' },
  { text: 'I feel empathy for others and make people feel at ease.', trait: 'A' },
  { text: 'I try to understand others\' perspectives before forming opinions.', trait: 'A' },
  { text: 'I am easily stressed and often feel anxious or unsettled.', trait: 'N' },
  { text: 'My mood fluctuates frequently and I can be easily upset.', trait: 'N' },
]

// ECR-R short form: 2 anxiety + 2 avoidance
const ATTACHMENT_ITEMS = [
  { text: 'I worry about being abandoned by the people I am close to.', subscale: 'anxiety' },
  { text: 'I need a lot of reassurance that I am loved.', subscale: 'anxiety' },
  { text: 'I prefer not to share my feelings or problems with partners.', subscale: 'avoidance' },
  { text: 'I feel comfortable depending on others for emotional support.', subscale: 'avoidance', reverse: true },
]

const LOVE_LANGUAGES = ['Words of Affirmation', 'Quality Time', 'Receiving Gifts', 'Acts of Service', 'Physical Touch']

const VALUES_CLUSTERS = [
  'Traditional / Family-oriented',
  'Career / Achievement-driven',
  'Creative / Artistic',
  'Progressive / Activist',
  'Adventure / Freedom-seeking',
  'Spiritual / Mindful',
]

const SOCIOSEXUAL_OPTIONS = [
  { value: 'Restricted',   label: 'Restricted',   sub: 'Seeking long-term' },
  { value: 'Moderate',     label: 'Moderate',      sub: 'Context-dependent' },
  { value: 'Unrestricted', label: 'Unrestricted',  sub: 'Open to short-term' },
]

// Mapping from OCEAN_ITEMS index to microdose item_id
// The question_pool.py OCEAN items have a different order than the view's OCEAN_ITEMS.
// Pool order: O, C, E, A, N, O, C, E, A, N (by trait, one per index)
// View order: O, O, C, C, E, E, A, A, N, N (grouped by trait)
// Map view index -> pool item_id based on matching text
const OCEAN_POOL_MAP: Record<number, string> = {
  0: 'ipip_neo_0',  // rich imagination
  1: 'ipip_neo_5',  // quick to understand
  2: 'ipip_neo_1',  // always prepared
  3: 'ipip_neo_6',  // pay attention to detail
  4: 'ipip_neo_2',  // life of the party
  5: 'ipip_neo_7',  // energized after social
  6: 'ipip_neo_3',  // empathy
  7: 'ipip_neo_8',  // understand perspectives
  8: 'ipip_neo_4',  // easily stressed
  9: 'ipip_neo_9',  // mood fluctuates
}

const ATTACH_POOL_MAP: Record<number, string> = {
  0: 'ecr_r_0',
  1: 'ecr_r_1',
  2: 'ecr_r_2',
  3: 'ecr_r_3',
}

// Mapping for identity categorical items — pool options differ slightly from view options
const IDENTITY_LOVE_LANG_MAP: Record<number, string> = {
  0: 'Words of Affirmation',
  1: 'Quality Time',
  2: 'Receiving Gifts',  // pool says "Gifts" but we map to view's label
  3: 'Acts of Service',
  4: 'Physical Touch',
}

const IDENTITY_VALUES_MAP: Record<number, string> = {
  0: 'Traditional / Family-oriented',
  1: 'Career / Achievement-driven',
  2: 'Creative / Artistic',
  3: 'Progressive / Activist',
  4: 'Adventure / Freedom-seeking',
  5: 'Spiritual / Mindful',
}

const IDENTITY_SOCIO_MAP: Record<number, string> = {
  0: 'Restricted',
  1: 'Moderate',
  2: 'Unrestricted',
}

// OCEAN interpretation thresholds
function oceanInterp(trait: string, score: number): string {
  const high = score >= 0.65
  const low  = score < 0.4
  const map: Record<string, [string, string, string]> = {
    O: ['Practical and concrete in thinking',       'Balanced pragmatism and curiosity',          'Highly imaginative, open to novel experiences'],
    C: ['Spontaneous, flexible, adaptive',           'Blends structure and adaptability',          'Organized, disciplined, follows through'],
    E: ['Introspective, gains energy from solitude', 'Comfortable in both social and solo contexts', 'Energized by people, thrives in company'],
    A: ['Direct and competitive, prioritizes logic', 'Cooperative but holds firm on key values',    'Empathic, harmonious, trusts others readily'],
    N: ['Emotionally stable, rarely rattled',        'Moderate emotional reactivity',              'Emotionally sensitive, internalizes stress'],
  }
  const [lo, mid, hi] = map[trait] ?? ['', '', '']
  return low ? lo : high ? hi : mid
}

// ── State ──────────────────────────────────────────────────────────
const step = ref(0)
const oceanAnswers  = ref<(number | undefined)[]>(Array(OCEAN_ITEMS.length).fill(undefined))
const attachAnswers = ref<(number | undefined)[]>(Array(ATTACHMENT_ITEMS.length).fill(undefined))

const form = ref({
  love_language:  LOVE_LANGUAGES[1],
  values_cluster: VALUES_CLUSTERS[0],
  sociosexual:    'Moderate',
})

const profile    = ref<any>(null)
const loading    = ref(true)
const submitting = ref(false)
const generating = ref(false)
const narrativeError = ref<string | null>(null)

// Progress tracking from backend
const microdosedItems = ref<Record<string, { value: number; from_trance: boolean }>>({})
const microdosedItemIds = computed(() => {
  const ids = new Set<string>()
  for (const [id, info] of Object.entries(microdosedItems.value)) {
    if (info.from_trance) ids.add(id)
  }
  return ids
})

// Expand/collapse toggles for completed steps
const expandOcean = ref(false)
const expandAttach = ref(false)
const expandIdentity = ref(false)

const { oauthState } = useVibeStore()

// ── Derived ────────────────────────────────────────────────────────
const oceanComplete     = computed(() => oceanAnswers.value.every(v => v !== undefined))
const attachmentComplete = computed(() => attachAnswers.value.every(v => v !== undefined))
const identityComplete  = computed(() => !!form.value.love_language && !!form.value.values_cluster && !!form.value.sociosexual)

// Step-level completion checks
const oceanStepComplete = computed(() => oceanComplete.value && Object.keys(OCEAN_POOL_MAP).every(i => microdosedItemIds.value.has(OCEAN_POOL_MAP[Number(i)])))
const attachStepComplete = computed(() => attachmentComplete.value && Object.keys(ATTACH_POOL_MAP).every(i => microdosedItemIds.value.has(ATTACH_POOL_MAP[Number(i)])))
const identityAllMicrodosed = computed(() =>
  microdosedItemIds.value.has('identity_love_language') &&
  microdosedItemIds.value.has('identity_values') &&
  microdosedItemIds.value.has('identity_sociosexual')
)
const identityStepComplete = computed(() => identityComplete.value)

const allItemsDone = computed(() => totalAnswered.value >= TOTAL_ITEMS)

const totalAnswered = computed(() => {
  let count = 0
  // Count answered OCEAN items
  for (let i = 0; i < OCEAN_ITEMS.length; i++) {
    if (oceanAnswers.value[i] !== undefined) count++
  }
  // Count answered attachment items
  for (let i = 0; i < ATTACHMENT_ITEMS.length; i++) {
    if (attachAnswers.value[i] !== undefined) count++
  }
  // Count identity items
  if (form.value.love_language) count++
  if (form.value.values_cluster) count++
  if (form.value.sociosexual) count++
  return count
})

const tranceCount = computed(() => microdosedItemIds.value.size)

function isOceanMicrodosed(index: number): boolean {
  const poolId = OCEAN_POOL_MAP[index]
  return poolId ? microdosedItemIds.value.has(poolId) : false
}

function isAttachMicrodosed(index: number): boolean {
  const poolId = ATTACH_POOL_MAP[index]
  return poolId ? microdosedItemIds.value.has(poolId) : false
}

const connectedProviders = computed(() => {
  if (!oauthState.value) return []
  return (Object.keys(oauthState.value) as (keyof typeof oauthState.value)[])
    .filter(k => oauthState.value[k].connected)
})

// Compute normalized OCEAN scores from Likert items
const computedScores = computed(() => {
  const scores: Record<string, number[]> = { O: [], C: [], E: [], A: [], N: [] }
  OCEAN_ITEMS.forEach((item, i) => {
    const v = oceanAnswers.value[i]
    if (v !== undefined) scores[item.trait].push((v - 1) / 4)
  })
  const avg = (arr: number[]) => arr.length ? arr.reduce((s, n) => s + n, 0) / arr.length : 0.5
  return { O: avg(scores.O), C: avg(scores.C), E: avg(scores.E), A: avg(scores.A), N: avg(scores.N) }
})

// Radar polygon — pentagon, radius 80, center 100,100
const radarPoints = computed(() => {
  const s = profile.value?.ipip_neo_scores ?? computedScores.value
  const pts = [
    [s.O, 270], [s.C, 342], [s.E, 54], [s.A, 126], [s.N, 198],
  ].map(([score, deg]) => {
    const r = (score as number) * 80
    const rad = ((deg as number) * Math.PI) / 180
    return `${100 + r * Math.cos(rad)},${100 + r * Math.sin(rad)}`
  })
  return pts.join(' ')
})

// True while we don't yet have norm-scored IPIP-NEO data — drives the
// observatory loading placeholder so the radar canvas isn't blank.
const isLoadingScores = computed(() => loading.value || !profile.value?.ipip_neo_scores)

const radarCanvasScores = computed(() => {
  const s = profile.value?.ipip_neo_scores
  if (!s) return undefined
  return {
    O: Math.round((s.O ?? 0) * 100),
    C: Math.round((s.C ?? 0) * 100),
    E: Math.round((s.E ?? 0) * 100),
    A: Math.round((s.A ?? 0) * 100),
    N: Math.round((s.N ?? 0) * 100),
  }
})

const oceanTraits = computed(() => {
  const s = profile.value?.ipip_neo_scores ?? {}
  return [
    { key: 'O', label: 'Openness',          score: s.O ?? 0, interp: oceanInterp('O', s.O ?? 0) },
    { key: 'C', label: 'Conscientiousness', score: s.C ?? 0, interp: oceanInterp('C', s.C ?? 0) },
    { key: 'E', label: 'Extraversion',      score: s.E ?? 0, interp: oceanInterp('E', s.E ?? 0) },
    { key: 'A', label: 'Agreeableness',     score: s.A ?? 0, interp: oceanInterp('A', s.A ?? 0) },
    { key: 'N', label: 'Neuroticism',       score: s.N ?? 0, interp: oceanInterp('N', s.N ?? 0) },
  ]
})

const attachmentStyleLabel = computed(() => {
  const ecr = profile.value?.ecr_r_scores
  if (!ecr) return ''
  const { anxiety, avoidance } = ecr
  if (anxiety < 0.5 && avoidance < 0.5) return 'Secure — comfortable with closeness and interdependence'
  if (anxiety >= 0.5 && avoidance < 0.5) return 'Anxious-Preoccupied — craves closeness, fears abandonment'
  if (anxiety < 0.5 && avoidance >= 0.5) return 'Dismissive-Avoidant — values independence, suppresses need'
  return 'Fearful-Avoidant — desires closeness but fears vulnerability'
})

const drivePatternSummary = computed(() => {
  const s = profile.value?.ocean_scores
  if (!s) return ''
  const high = (v: number) => v > 0.6
  const parts: string[] = []
  if (high(s.O)) parts.push('curious and drawn to novelty')
  else parts.push('grounded in the concrete and familiar')
  if (high(s.C)) parts.push('structured and self-directed')
  else parts.push('flexible and adaptive')
  if (high(s.E)) parts.push('energized by people and activity')
  else parts.push('recharged by solitude and reflection')
  return parts.join(', ') + '.'
})

const attachmentSummary = computed(() => {
  const ecr = profile.value?.ecr_r_scores
  if (!ecr) return ''
  const { anxiety, avoidance } = ecr
  if (anxiety < 0.5 && avoidance < 0.5)
    return 'You tend to feel safe in close relationships and are comfortable depending on others.'
  if (anxiety >= 0.5 && avoidance < 0.5)
    return 'You crave closeness and are sensitive to signs of distance — connection is high-stakes for you.'
  if (anxiety < 0.5 && avoidance >= 0.5)
    return 'You value independence and may pull away when others press for closeness.'
  return 'You want deep connection but closeness also triggers fear — the push-pull is the signal.'
})

// ── Helpers ────────────────────────────────────────────────────────
function pct(v: number) { return Math.round(v * 100) }

const getHeaders = () => {
  const token = localStorage.getItem('channelzero-jwt')
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

// ── Hydrate form from microdose progress ──────────────────────────
function hydrateFromProgress(answered: Record<string, { value: number; from_trance: boolean }>) {
  microdosedItems.value = answered

  // Hydrate OCEAN answers
  for (let i = 0; i < OCEAN_ITEMS.length; i++) {
    const poolId = OCEAN_POOL_MAP[i]
    if (poolId && answered[poolId]) {
      oceanAnswers.value[i] = answered[poolId].value
    }
  }

  // Hydrate attachment answers
  for (let i = 0; i < ATTACHMENT_ITEMS.length; i++) {
    const poolId = ATTACH_POOL_MAP[i]
    if (poolId && answered[poolId]) {
      attachAnswers.value[i] = answered[poolId].value
    }
  }

  // Hydrate identity items
  if (answered['identity_love_language']) {
    const idx = answered['identity_love_language'].value
    const mapped = IDENTITY_LOVE_LANG_MAP[idx]
    if (mapped) form.value.love_language = mapped
  }
  if (answered['identity_values']) {
    const idx = answered['identity_values'].value
    const mapped = IDENTITY_VALUES_MAP[idx]
    if (mapped) form.value.values_cluster = mapped
  }
  if (answered['identity_sociosexual']) {
    const idx = answered['identity_sociosexual'].value
    const mapped = IDENTITY_SOCIO_MAP[idx]
    if (mapped) form.value.sociosexual = mapped
  }
}

// ── Smart step navigation ─────────────────────────────────────────
function advanceToFirstIncomplete() {
  if (!oceanComplete.value) { step.value = 0; return }
  if (!attachmentComplete.value) { step.value = 1; return }
  step.value = 2
}

// ── Lifecycle ──────────────────────────────────────────────────────
onMounted(async () => {
  const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  try {
    // Check for existing profile first
    const profileRes = await fetch(`${API}/api/psychometrics/profile`, {
      headers: getHeaders(),
    })
    if (profileRes.ok) {
      profile.value = await profileRes.json()
      loading.value = false
      return
    }
  } catch { /* no profile yet */ }

  // No profile — check for microdose progress
  try {
    const progressRes = await fetch(`${API}/api/psychometrics/progress`, {
      headers: getHeaders(),
    })
    if (progressRes.ok) {
      const data = await progressRes.json()
      if (data.answered && Object.keys(data.answered).length > 0) {
        hydrateFromProgress(data.answered)
        // If all items answered via microdose, auto-submit
        if (data.completed >= TOTAL_ITEMS) {
          loading.value = false
          await submitAssessment()
          return
        }
        // Otherwise advance to first incomplete step
        advanceToFirstIncomplete()
      }
    }
  } catch { /* no progress data */ }

  loading.value = false
})

// ── Actions ────────────────────────────────────────────────────────
const submitAssessment = async () => {
  submitting.value = true
  // Compute attachment scores from Likert responses
  const anxietyItems  = ATTACHMENT_ITEMS.map((item, i) => ({ ...item, answer: attachAnswers.value[i]! }))
    .filter(item => item.subscale === 'anxiety')
  const avoidanceItems = ATTACHMENT_ITEMS.map((item, i) => ({ ...item, answer: attachAnswers.value[i]! }))
    .filter(item => item.subscale === 'avoidance')

  const anxScore = anxietyItems.reduce((s, item) => s + (item.answer - 1) / 6, 0) / anxietyItems.length
  const avoScore = avoidanceItems.reduce((s, item) => {
    const v = (item as any).reverse ? (8 - item.answer - 1) / 6 : (item.answer - 1) / 6
    return s + v
  }, 0) / avoidanceItems.length

  const s = computedScores.value
  try {
    const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const res = await fetch(`${API}/api/psychometrics/submit`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        responses: {
          O_score: s.O, C_score: s.C, E_score: s.E, A_score: s.A, N_score: s.N,
          anxiety_score: anxScore,
          avoidance_score: avoScore,
          love_language: form.value.love_language,
          values_cluster: form.value.values_cluster,
          sociosexual: form.value.sociosexual,
        },
      }),
    })
    if (res.ok) {
      const data = await res.json()
      profile.value = data.profile
    }
  } catch { /* noop */ } finally {
    submitting.value = false
  }
}

const generateNarrative = async () => {
  generating.value = true
  narrativeError.value = null
  try {
    const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const res = await fetch(`${API}/api/psychometrics/narrative`, {
      method: 'POST',
      headers: getHeaders(),
    })
    if (res.ok) {
      const data = await res.json()
      profile.value.narrative = data.narrative
    } else {
      const err = await res.json().catch(() => ({}))
      narrativeError.value = err.detail || 'Error generating narrative. Check your API key.'
    }
  } catch { /* noop */ } finally {
    generating.value = false
  }
}
</script>

<style scoped>
/* Hide number spinner */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
input[type="number"] { -moz-appearance: textfield; }
</style>
