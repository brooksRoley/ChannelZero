<template>
  <div class="min-h-screen calibrate-bg text-gray-100 p-4 sm:p-8 flex flex-col items-center relative">

    <!-- Oracle synthesis overlay -->
    <div
      v-if="oracleSynthesizing"
      class="fixed inset-0 z-50 oracle-overlay backdrop-blur-sm flex flex-col items-center justify-center px-6"
      role="dialog"
      aria-live="polite"
      aria-label="Oracle synthesis in progress"
    >
      <!-- Expanding ring pulse -->
      <div class="relative w-72 h-72 flex items-center justify-center mb-10">
        <div
          v-for="i in 3"
          :key="i"
          class="absolute inset-0 rounded-full border border-purple-400/40 animate-ping oracle-ping"
          :style="{ animationDuration: '2s', animationDelay: `${(i - 1) * 0.5}s` }"
        ></div>
        <div class="relative w-24 h-24 rounded-full bg-purple-500/20 border border-purple-400/60 backdrop-blur-md flex items-center justify-center text-purple-200 font-mono uppercase">
          <span v-if="synthStage >= 3" class="text-3xl tracking-tight tabular-nums">{{ synthCount }}</span>
          <span v-else class="text-xs tracking-widest">Oracle</span>
        </div>

        <!-- Coordinates locked flash -->
        <div
          v-if="coordinatesLocked"
          class="absolute inset-0 flex items-center justify-center pointer-events-none animate-fade-in"
        >
          <span class="text-lg font-mono uppercase tracking-[0.25em] text-center" style="color: #22c55e">Coordinates locked</span>
        </div>
      </div>

      <!-- Connected provider chips, sequential pulse -->
      <div class="flex flex-wrap justify-center gap-x-3 gap-y-4 mb-10 max-w-xl">
        <div
          v-for="(key, idx) in synthProviderKeys"
          :key="key"
          class="flex flex-col items-center gap-1"
        >
          <span
            class="text-xs px-3 py-1 rounded-full border border-purple-500/40 text-purple-200 bg-purple-500/10 transition-all duration-700"
            :class="synthStage >= 2 ? 'opacity-100' : 'opacity-30'"
            :style="{
              animation: synthStage >= 2 ? `synth-card-pulse 1.4s ease-out ${idx * 0.25}s 1` : 'none',
            }"
          >
            {{ PROVIDER_LABELS[key as string] || key }}
          </span>
          <span
            class="text-[0.625rem] font-mono uppercase tracking-wider text-purple-300/60 transition-opacity duration-500"
            :class="synthStage >= 2 ? 'opacity-100' : 'opacity-0'"
            :style="{ transitionDelay: `${idx * 0.25 + 0.2}s` }"
          >
            {{ SIGNAL_LABELS[key as string] || '' }}
          </span>
        </div>
      </div>

      <!-- Dimension labels staggered -->
      <div class="flex flex-col items-center gap-3 mb-10 min-h-[6rem]">
        <p class="text-xs text-gray-500 uppercase tracking-[0.3em] mb-2">Synthesizing your coordinate</p>
        <div class="flex flex-wrap justify-center gap-3">
          <span
            v-for="(dim, i) in ORACLE_DIMENSIONS"
            :key="dim.key"
            class="text-sm text-purple-100 font-mono tracking-wide transition-all duration-700"
            :class="synthStage >= 3 ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'"
            :style="{ transitionDelay: `${i * 250}ms` }"
          >
            · {{ dim.label }} ·
          </span>
        </div>
      </div>

      <!-- CTA -->
      <button
        v-if="synthStage >= 4"
        @click="goToUniverse"
        class="bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 px-8 rounded-full shadow-[0_0_30px_rgba(147,51,234,0.5)] transition-all animate-fade-in"
      >
        See your signal &rarr;
      </button>
    </div>

    <div class="max-w-3xl w-full space-y-12">

      <div class="text-center space-y-4">
        <div class="flex items-center justify-center gap-4 mb-2">
          <RadarIcon />
          <h1 class="text-4xl font-extrabold tracking-tight text-white">Calibrate Your Signal</h1>
          <SignalIcon />
        </div>
        <p class="text-gray-400 text-lg">
          We don't care what you look like. We care about what you listen to, what you laugh at, and how you spend your time.
          Connect the accounts that matter — each one sharpens the signal.
        </p>
      </div>

      <!-- One-stream progress nudge — visible when exactly 1 stream is connected -->
      <div
        v-if="synthProviderKeys.length === 1 && showProgressNudge"
        class="flex items-start justify-between gap-4 rounded-2xl border border-indigo-400/30 bg-indigo-500/5 px-5 py-4"
        role="status"
      >
        <p class="text-sm text-indigo-300/80 font-mono leading-relaxed">
          One stream connected — connect one more to unlock your Integrated Portrait.
        </p>
        <button
          @click="showProgressNudge = false"
          class="shrink-0 text-gray-600 hover:text-gray-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 rounded"
          aria-label="Dismiss"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Integrated Portrait invitation — unlocked at 2+ connected streams -->
      <RouterLink
        v-if="synthProviderKeys.length >= 2"
        to="/portrait"
        class="block rounded-2xl border border-indigo-400/40 bg-indigo-500/5 p-6 hover:bg-indigo-500/10 hover:border-indigo-400/60 transition-colors group"
      >
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="text-lg font-bold text-indigo-200 mb-1">Your Integrated Portrait</h2>
            <p class="text-sm text-gray-400">
              {{ synthProviderKeys.length }} streams connected — enough for one reading across all of them.
              A mirror earned from your own data.
            </p>
          </div>
          <span class="text-indigo-300 text-2xl group-hover:translate-x-1 transition-transform shrink-0" aria-hidden="true">&rarr;</span>
        </div>
      </RouterLink>

      <div class="grid grid-cols-1 gap-8">

        <!-- Spotify -->
        <div v-if="oauthState.spotify.connected"
             class="ccard-active border border-green-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-green-400">Spotify</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Sonic Blueprint</h3>
            </div>
            <router-link to="/calibrate/spotify" class="text-xs font-medium text-green-400 bg-green-400/10 border border-green-500/30 rounded-full px-3 py-1 hover:bg-green-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <!-- Loading skeleton -->
          <div v-if="spotifyLoading || !spotifyProfile" class="space-y-3 animate-pulse">
            <div class="h-4 skel-line rounded w-3/4"></div>
            <div class="h-4 skel-line rounded w-1/2"></div>
            <div class="h-4 skel-line rounded w-2/3"></div>
          </div>
          <!-- Data mirror -->
          <div v-else class="space-y-4">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-2">Top Genres</p>
              <div class="flex flex-wrap gap-2">
                <span v-for="(genre, i) in spotifyProfile.genres.slice(0, 3)" :key="genre"
                      class="text-xs px-3 py-1 rounded-full border"
                      :class="GENRE_COLORS[i % GENRE_COLORS.length]">{{ genre }}</span>
              </div>
            </div>
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Top Artists</p>
              <p class="text-sm text-gray-300">{{ spotifyProfile.top_artists.slice(0, 3).join(' · ') }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Mood</p>
              <span class="text-sm font-semibold"
                    :class="{
                      'text-blue-400': spotifyProfile.audio_avg.valence < 0.3,
                      'text-amber-400': spotifyProfile.audio_avg.valence >= 0.3 && spotifyProfile.audio_avg.valence <= 0.5,
                      'text-yellow-300': spotifyProfile.audio_avg.valence > 0.5 && spotifyProfile.audio_avg.valence <= 0.7,
                      'text-green-300': spotifyProfile.audio_avg.valence > 0.7,
                    }">{{ valenceLabel(spotifyProfile.audio_avg.valence) }}</span>
              <span class="text-xs text-gray-600 ml-2">({{ (spotifyProfile.audio_avg.valence * 100).toFixed(0) }}% valence)</span>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Energy</p>
                <div class="w-full bar-track rounded-full h-2">
                  <div class="bg-green-400 h-2 rounded-full transition-all" :style="{ width: (spotifyProfile.audio_avg.energy * 100) + '%' }"></div>
                </div>
                <p class="text-xs text-gray-500 mt-1">{{ (spotifyProfile.audio_avg.energy * 100).toFixed(0) }}%</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Danceability</p>
                <div class="w-full bar-track rounded-full h-2">
                  <div class="bg-green-400 h-2 rounded-full transition-all" :style="{ width: (spotifyProfile.audio_avg.danceability * 100) + '%' }"></div>
                </div>
                <p class="text-xs text-gray-500 mt-1">{{ (spotifyProfile.audio_avg.danceability * 100).toFixed(0) }}%</p>
              </div>
            </div>
          </div>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-green-400">Spotify</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Sonic Blueprint</h3>
            </div>
            <SpotifyConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Top artists, heavy-rotation tracks, acoustic properties (danceability, valence, tempo).</p>
            <p><strong>Correlation Engine:</strong> The sonic aesthetic is the core match catalyst. Shared obsessions with obscure 90s shoegaze or high-tempo hyperpop bump compatibility scores — the audio fingerprint becomes part of your psychological coordinate.</p>
          </div>
        </div>

        <!-- Twitter / X -->
        <div v-if="oauthState.twitter.connected"
             class="ccard-active border border-blue-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-blue-400">X / Twitter</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Neurotic Imprint</h3>
            </div>
            <router-link to="/calibrate/twitter" class="text-xs font-medium text-blue-400 bg-blue-400/10 border border-blue-500/30 rounded-full px-3 py-1 hover:bg-blue-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div v-if="twitterLoading || !twitterProfile" class="space-y-3 animate-pulse">
            <div class="h-4 skel-line rounded w-3/4"></div>
            <div class="h-4 skel-line rounded w-1/2"></div>
            <div class="h-4 skel-line rounded w-2/3"></div>
          </div>
          <div v-else class="space-y-4">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Username</p>
              <p class="text-sm text-blue-300 font-semibold">@{{ twitterProfile.username }}</p>
            </div>
            <div v-if="twitterProfile.bio">
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Bio</p>
              <p class="text-sm text-gray-300 line-clamp-2">{{ twitterProfile.bio }}</p>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Followers</p>
                <p class="text-lg font-bold text-blue-300">{{ twitterProfile.followers_count.toLocaleString() }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Following</p>
                <p class="text-lg font-bold text-blue-300">{{ twitterProfile.following_count.toLocaleString() }}</p>
              </div>
            </div>
          </div>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-blue-400">X / Twitter</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Neurotic Imprint</h3>
            </div>
            <TwitterConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Followed accounts, liked tweets, linguistic patterns, chronological posting habits.</p>
            <p><strong>Correlation Engine:</strong> Humor register and ideological signature. The LLM extracts dominance, neuroticism, and dark humor scores from your public graph to build a neurotic-output narrative.</p>
          </div>
        </div>

        <!-- Strava -->
        <div v-if="oauthState.strava.connected"
             class="ccard-active border border-orange-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-orange-400">Strava</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Somatic Ledger</h3>
            </div>
            <router-link to="/calibrate/strava" class="text-xs font-medium text-orange-400 bg-orange-400/10 border border-orange-500/30 rounded-full px-3 py-1 hover:bg-orange-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <!-- Loading skeleton -->
          <div v-if="stravaLoading || !stravaProfile" class="space-y-3 animate-pulse">
            <div class="h-4 skel-line rounded w-3/4"></div>
            <div class="h-4 skel-line rounded w-1/2"></div>
            <div class="h-4 skel-line rounded w-2/3"></div>
          </div>
          <!-- Data mirror -->
          <div v-else class="space-y-4">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Activity Breakdown</p>
              <p class="text-sm text-gray-300">
                <span v-for="(count, type, i) in stravaProfile.activity_types" :key="type">
                  <span v-if="i > 0"> · </span>{{ count }} {{ type }}{{ count !== 1 ? 's' : '' }}
                </span>
              </p>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Distance</p>
                <p class="text-lg font-bold text-orange-300">{{ stravaProfile.total_distance_km.toLocaleString(undefined, { maximumFractionDigits: 0 }) }} <span class="text-xs text-gray-500 font-normal">km</span></p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Elevation</p>
                <p class="text-lg font-bold text-orange-300">{{ stravaProfile.total_elevation_m.toLocaleString(undefined, { maximumFractionDigits: 0 }) }} <span class="text-xs text-gray-500 font-normal">m</span></p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Moving Hours</p>
                <p class="text-lg font-bold text-orange-300">{{ stravaProfile.total_moving_hours.toLocaleString(undefined, { maximumFractionDigits: 1 }) }} <span class="text-xs text-gray-500 font-normal">hrs</span></p>
              </div>
              <div v-if="stravaProfile.avg_heartrate">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Avg Heart Rate</p>
                <p class="text-lg font-bold text-orange-300">{{ Math.round(stravaProfile.avg_heartrate) }} <span class="text-xs text-gray-500 font-normal">bpm</span></p>
              </div>
            </div>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Since your body holds the tension your mind ignores.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-orange-400">Strava</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Somatic Ledger</h3>
            </div>
            <StravaConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Heart-rate exertion curves, elevation masochism, routing patterns, recovery windows.</p>
            <p><strong>Correlation Engine:</strong> Maps your body's behavioral signature — exertion cadence, elevation obsessions, recovery windows — into a somatic narrative the Oracle reads as psychological data.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Since your body holds the tension your mind ignores.</p>
        </div>

        <!-- Google Calendar -->
        <div v-if="oauthState.google.connected"
             class="ccard-active border border-red-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-red-400">Google Calendar</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">Time as Behavior</h3>
            </div>
            <router-link to="/calibrate/google" class="text-xs font-medium text-red-400 bg-red-400/10 border border-red-500/30 rounded-full px-3 py-1 hover:bg-red-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <!-- Loading skeleton -->
          <div v-if="gcalLoading || !gcalProfile" class="space-y-3 animate-pulse">
            <div class="h-4 skel-line rounded w-3/4"></div>
            <div class="h-4 skel-line rounded w-1/2"></div>
            <div class="h-4 skel-line rounded w-2/3"></div>
          </div>
          <!-- Data mirror -->
          <div v-else class="space-y-4">
            <div v-if="gcalProfile.peak_hours.length">
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Peak Scheduling Window</p>
              <p class="text-sm text-gray-300">{{ gcalProfile.peak_hours.map(h => `${h % 12 || 12}${h < 12 ? 'am' : 'pm'}`).join(' · ') }}</p>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Overcommitment Ratio</p>
                <div class="w-full bar-track rounded-full h-2">
                  <div class="bg-red-400 h-2 rounded-full transition-all" :style="{ width: (gcalProfile.overcommitment_ratio * 100) + '%' }"></div>
                </div>
                <p class="text-xs text-gray-500 mt-1">{{ (gcalProfile.overcommitment_ratio * 100).toFixed(0) }}%</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Avg Events / Week</p>
                <p class="text-lg font-bold text-red-300">{{ gcalProfile.avg_events_per_week.toFixed(1) }}</p>
              </div>
            </div>
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Meeting Density</p>
              <p class="text-sm font-semibold" :class="{
                'text-green-400': gcalProfile.meeting_density === 'sparse',
                'text-amber-400': gcalProfile.meeting_density === 'moderate',
                'text-red-400': gcalProfile.meeting_density === 'dense',
                'text-red-300': gcalProfile.meeting_density === 'overwhelming',
              }">{{ gcalProfile.meeting_density.charAt(0).toUpperCase() + gcalProfile.meeting_density.slice(1) }}</p>
            </div>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your schedule is a confession you write every morning.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-red-400">Google Calendar</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">Time as Behavior</h3>
            </div>
            <GCalConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Event density, free/busy windows, recurring rituals, peak scheduling hours, evening overcommitment ratio.</p>
            <p><strong>Correlation Engine:</strong> Maps your <span class="text-red-400 font-semibold">Temporal Anxiety</span> — when you overbook, when you leave white space, and whether your calendar reflects intention or dread. The Oracle uses this to predict burnout compatibility and co-regulation windows.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your schedule is a confession you write every morning.</p>
        </div>

        <!-- Co-Star -->
        <div v-if="oauthState.costar.connected"
             class="ccard-active border border-indigo-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-indigo-400">Co&#8239;&#8212;&#8239;Star</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Fatalistic Mirror</h3>
            </div>
            <router-link to="/calibrate/costar" class="text-xs font-medium text-indigo-400 bg-indigo-400/10 border border-indigo-500/30 rounded-full px-3 py-1 hover:bg-indigo-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div class="space-y-3 text-gray-300">
            <p>Your natal chart has been ingested. Sun, Moon, Rising, Mars, Venus — the Oracle is reading your cosmic wiring to predict friction points and structure daily challenges.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Since you already look to the void for answers.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-indigo-400">Co&#8239;&#8212;&#8239;Star</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Fatalistic Mirror</h3>
            </div>
            <CoStarConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Full natal chart (Sun, Moon, Rising, Mars, Venus), check-in frequency, transit anxiety correlation.</p>
            <p><strong>Correlation Engine:</strong> The Oracle uses your chart to predict friction points and structure daily challenges. Pseudo-science becomes an engine for genuine generosity.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Since you already look to the void for answers.</p>
        </div>

        <!-- Letterboxd -->
        <div v-if="oauthState.letterboxd.connected"
             class="ccard-active border border-emerald-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-emerald-400">Letterboxd</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Empathy Simulator</h3>
            </div>
            <router-link to="/calibrate/letterboxd" class="text-xs font-medium text-emerald-400 bg-emerald-400/10 border border-emerald-500/30 rounded-full px-3 py-1 hover:bg-emerald-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div class="space-y-3 text-gray-300">
            <p>Your watchlist and diary entries are being analyzed. Aesthetic pretension markers and star-rating patterns feed the empathy-simulator narrative.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">We already know you cried during that one.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-emerald-400">Letterboxd</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Empathy Simulator</h3>
            </div>
            <LetterboxdConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Watchlist, diary entries, star ratings, aesthetic pretension markers.</p>
            <p><strong>Correlation Engine:</strong> Decodes your empathy architecture — which narratives you choose, how harshly you judge them, and what your genre obsessions reveal about your interior life.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">We already know you cried during that one.</p>
        </div>

        <!-- Steam -->
        <div v-if="oauthState.steam.connected"
             class="ccard-active border border-slate-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-slate-400">Steam</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Isolation Metric</h3>
            </div>
            <router-link to="/calibrate/steam" class="text-xs font-medium text-slate-400 bg-slate-400/10 border border-slate-500/30 rounded-full px-3 py-1 hover:bg-slate-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div class="space-y-3 text-gray-300">
            <p>Your game library has been ingested. Playtime patterns, genre obsessions, and late-night session clusters feed the Oracle's understanding of your escapism architecture.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your Steam library is a map of every world you chose over this one.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-slate-400">Steam</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Isolation Metric</h3>
            </div>
            <SteamConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Game library, total playtime, recent sessions, genre distribution, late-night activity patterns.</p>
            <p><strong>Correlation Engine:</strong> Maps your <span class="text-slate-400 font-semibold">Isolation Metric</span> — which worlds you retreat to, how long you stay, and what that says about what you're avoiding.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your Steam library is a map of every world you chose over this one.</p>
        </div>

        <!-- GitHub -->
        <div v-if="oauthState.github.connected"
             class="ccard-active border border-purple-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-purple-400">GitHub</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Builder's Ledger</h3>
            </div>
            <router-link to="/calibrate/github" class="text-xs font-medium text-purple-400 bg-purple-400/10 border border-purple-500/30 rounded-full px-3 py-1 hover:bg-purple-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div v-if="githubLoading || !githubProfile" class="space-y-3 animate-pulse">
            <div class="h-4 skel-line rounded w-3/4"></div>
            <div class="h-4 skel-line rounded w-1/2"></div>
            <div class="h-4 skel-line rounded w-2/3"></div>
          </div>
          <div v-else class="space-y-4">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Username</p>
              <p class="text-sm text-purple-300 font-semibold">{{ githubProfile.username }}</p>
            </div>
            <div v-if="githubProfile.top_languages?.length">
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-2">Top Languages</p>
              <div class="flex flex-wrap gap-2">
                <span v-for="lang in githubProfile.top_languages.slice(0, 3)" :key="lang"
                      class="text-xs px-3 py-1 rounded-full border bg-purple-500/20 text-purple-300 border-purple-500/40">
                  {{ lang }}
                </span>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Public Repos</p>
                <p class="text-lg font-bold text-purple-300">{{ githubProfile.public_repos }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Stars</p>
                <p class="text-lg font-bold text-purple-300">{{ githubProfile.stars.toLocaleString() }}</p>
              </div>
            </div>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your commit history is a diary you forgot you were writing.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-purple-400">GitHub</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Builder's Ledger</h3>
            </div>
            <GitHubConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Top languages, public repos, star count, contribution patterns, topic interests.</p>
            <p><strong>Correlation Engine:</strong> Maps your builder identity — what you create, how obsessively, and in which languages. The Oracle reads your repos like a therapist reads a journal.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your commit history is a diary you forgot you were writing.</p>
        </div>

        <!-- YouTube -->
        <div v-if="oauthState.youtube.connected"
             class="ccard-active border border-red-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-red-400">YouTube</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Attention Archive</h3>
            </div>
            <router-link to="/calibrate/youtube" class="text-xs font-medium text-red-400 bg-red-400/10 border border-red-500/30 rounded-full px-3 py-1 hover:bg-red-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div v-if="youtubeLoading || !youtubeProfile" class="space-y-3 animate-pulse">
            <div class="h-4 skel-line rounded w-3/4"></div>
            <div class="h-4 skel-line rounded w-1/2"></div>
            <div class="h-4 skel-line rounded w-2/3"></div>
          </div>
          <div v-else class="space-y-4">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Channel</p>
              <p class="text-sm text-red-300 font-semibold">{{ youtubeProfile.channel_name }}</p>
            </div>
            <div class="grid grid-cols-3 gap-4">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Subscribers</p>
                <p class="text-lg font-bold text-red-300">{{ youtubeProfile.subscriber_count.toLocaleString() }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Videos</p>
                <p class="text-lg font-bold text-red-300">{{ youtubeProfile.video_count.toLocaleString() }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Views</p>
                <p class="text-lg font-bold text-red-300">{{ youtubeProfile.view_count.toLocaleString() }}</p>
              </div>
            </div>
            <div v-if="Object.keys(youtubeProfile.subscription_categories || {}).length">
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-2">Top Categories</p>
              <div class="flex flex-wrap gap-2">
                <span v-for="cat in Object.keys(youtubeProfile.subscription_categories).slice(0, 4)" :key="cat"
                      class="text-xs px-3 py-1 rounded-full border bg-red-500/20 text-red-300 border-red-500/40">
                  {{ cat }}
                </span>
              </div>
            </div>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your algorithm knows you better than your friends do.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-red-400">YouTube</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Attention Archive</h3>
            </div>
            <YouTubeConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Subscriptions, watch categories, channel engagement patterns, content appetite.</p>
            <p><strong>Correlation Engine:</strong> Maps your attention economy — what you watch reveals what you crave. The Oracle correlates subscription categories with personality vectors.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your algorithm knows you better than your friends do.</p>
        </div>

        <!-- Reddit -->
        <div v-if="oauthState.reddit.connected"
             class="ccard-active border border-orange-600/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-orange-600">Reddit</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Anonymous Confessional</h3>
            </div>
            <router-link to="/calibrate/reddit" class="text-xs font-medium text-orange-600 bg-orange-600/10 border border-orange-600/30 rounded-full px-3 py-1 hover:bg-orange-600/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div v-if="redditLoading || !redditProfile" class="space-y-3 animate-pulse">
            <div class="h-4 skel-line rounded w-3/4"></div>
            <div class="h-4 skel-line rounded w-1/2"></div>
            <div class="h-4 skel-line rounded w-2/3"></div>
          </div>
          <div v-else class="space-y-4">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Username</p>
              <p class="text-sm text-orange-400 font-semibold">u/{{ redditProfile.username }}</p>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Karma</p>
                <p class="text-lg font-bold text-orange-400">{{ redditProfile.total_karma.toLocaleString() }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Lurker Ratio</p>
                <p class="text-lg font-bold text-orange-400">{{ (redditProfile.lurker_ratio * 100).toFixed(0) }}<span class="text-xs text-gray-500 font-normal">%</span></p>
              </div>
            </div>
            <div v-if="redditProfile.subreddits?.length">
              <p class="text-xs text-gray-500 uppercase tracking-wider mb-2">Top Subreddits</p>
              <div class="flex flex-wrap gap-2">
                <span v-for="sub in redditProfile.subreddits.slice(0, 3)" :key="sub"
                      class="text-xs px-3 py-1 rounded-full border bg-orange-600/20 text-orange-300 border-orange-600/40">
                  r/{{ sub }}
                </span>
              </div>
            </div>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">The things you upvote when no one's watching say everything.</p>
        </div>
        <div v-else
             class="ccard-idle border rounded-2xl p-6 shadow-xl transition-transform hover:-translate-y-1">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-orange-600">Reddit</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Anonymous Confessional</h3>
            </div>
            <RedditConnect />
          </div>
          <div class="space-y-3 text-gray-300">
            <p><strong>Data Collected:</strong> Subreddit activity, karma breakdown, lurker ratio, active hours, behavioral patterns.</p>
            <p><strong>Correlation Engine:</strong> Your anonymous browsing habits reveal your true interests. The Oracle maps community affiliation and engagement depth to find your ideological kin.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">The things you upvote when no one's watching say everything.</p>
        </div>

        <!-- Instagram -->
        <div v-if="oauthState.instagram.connected"
             class="ccard-active border border-pink-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-pink-400">Instagram</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Curated Self</h3>
            </div>
            <router-link to="/calibrate/instagram" class="text-xs font-medium text-pink-400 bg-pink-400/10 border border-pink-500/30 rounded-full px-3 py-1 hover:bg-pink-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div class="space-y-3 text-gray-300">
            <p>Your visual identity is being analyzed. The Oracle reads the gap between your grid and your reality.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">The grid is a mirror, not a window.</p>
        </div>
        <div v-else
             class="ccard-coming border rounded-2xl p-6 shadow-xl opacity-60 cursor-not-allowed select-none"
             aria-disabled="true">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-pink-400/70">Instagram</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Curated Self</h3>
            </div>
            <span class="text-xs font-medium text-gray-400 bg-gray-700/40 border border-gray-600/40 rounded-full px-3 py-1 whitespace-nowrap">Coming soon</span>
          </div>
          <div class="space-y-3 text-gray-400">
            <p>Instagram isn't a live connection yet. The Oracle will soon read the gap between your curated grid and your signal fingerprint.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">The grid is a mirror, not a window.</p>
        </div>

        <!-- TikTok -->
        <div v-if="oauthState.tiktok.connected"
             class="ccard-active border border-cyan-500/50 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-cyan-400">TikTok</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Dopamine Map</h3>
            </div>
            <router-link to="/calibrate/tiktok" class="text-xs font-medium text-cyan-400 bg-cyan-400/10 border border-cyan-500/30 rounded-full px-3 py-1 hover:bg-cyan-400/20 transition-colors">View Signal &rarr;</router-link>
          </div>
          <div class="space-y-3 text-gray-300">
            <p>Your For You Page is being decoded. Scroll patterns and content affinity feed the Oracle's understanding of your attention architecture.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your FYP is a Rorschach test you take every night.</p>
        </div>
        <div v-else
             class="ccard-coming border rounded-2xl p-6 shadow-xl opacity-60 cursor-not-allowed select-none"
             aria-disabled="true">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h2 class="text-2xl font-bold text-cyan-400/70">TikTok</h2>
              <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">The Dopamine Map</h3>
            </div>
            <span class="text-xs font-medium text-gray-400 bg-gray-700/40 border border-gray-600/40 rounded-full px-3 py-1 whitespace-nowrap">Coming soon</span>
          </div>
          <div class="space-y-3 text-gray-400">
            <p>TikTok isn't a live connection yet. The Oracle will soon map the dopamine architecture behind what makes you stop scrolling.</p>
          </div>
          <p class="mt-4 text-xs text-gray-600 font-mono italic">Your FYP is a Rorschach test you take every night.</p>
        </div>

      </div>

      <!-- Connected sources + feedback -->
      <div v-if="connectedSources.length > 0" class="mt-8 ccard-sources border border-green-500/20 rounded-2xl p-5 space-y-4">
        <h3 class="text-sm font-medium text-green-400 uppercase tracking-wider">Connected</h3>
        <div class="space-y-4">
          <div v-for="src in connectedSources" :key="src.key">
            <div class="flex items-center gap-2 text-sm text-gray-400 mb-2">
              <span class="w-2 h-2 rounded-full bg-green-500"></span>
              <router-link :to="`/calibrate/${src.key}`" class="hover:text-green-400 transition-colors">
                {{ src.label }}
                <span class="text-xs opacity-60 ml-1">&rarr;</span>
              </router-link>
              <span v-if="src.lastSync" class="text-gray-600 text-xs">{{ new Date(src.lastSync).toLocaleDateString() }}</span>
            </div>

            <div v-if="!feedbackGiven[src.key]" class="ml-4 flex flex-col gap-2">
              <p class="text-xs text-gray-500">How useful does this feel for finding your match?</p>
              <div class="flex items-center gap-1">
                <button
                  v-for="n in 5"
                  :key="n"
                  @click="setRating(src.key, n)"
                  :aria-label="`Rate ${src.label} ${n} out of 5 stars`"
                  class="text-xl transition-transform hover:scale-110"
                  :class="(pendingRating[src.key] || 0) >= n ? 'text-yellow-400' : 'text-gray-700'"
                >★</button>
              </div>
              <div v-if="pendingRating[src.key]" class="flex flex-wrap gap-2">
                <button
                  v-for="tag in FEEDBACK_TAGS"
                  :key="tag"
                  @click="toggleTag(src.key, tag)"
                  :aria-label="`Select feedback tag: ${tag.replace(/_/g, ' ')}`"
                  class="text-xs px-2.5 py-1 rounded-full border transition-colors"
                  :class="selectedTags[src.key]?.includes(tag)
                    ? 'border-purple-500 text-purple-400 bg-purple-900/20'
                    : 'border-gray-700 text-gray-500 hover:border-gray-500'"
                >{{ tag.replace(/_/g, ' ') }}</button>
                <button
                  @click="submitFeedback(src.key)"
                  class="text-xs px-3 py-1 rounded-full bg-purple-700 text-white hover:bg-purple-600 transition-colors ml-auto"
                >Submit</button>
              </div>
            </div>
            <div v-else class="ml-4 text-xs text-gray-600">Feedback recorded ✓</div>
          </div>
        </div>
      </div>

      <!-- CTA -->
      <div class="flex flex-col items-center gap-4 pt-6">
        <button
          @click="proceed"
          class="bg-purple-600 hover:bg-purple-700 text-white font-extrabold text-xl py-4 px-12 rounded-full shadow-[0_0_20px_rgba(147,51,234,0.4)] transition-all"
        >
          Enter the Field
        </button>
        <p class="text-gray-600 text-sm font-mono text-center max-w-sm">
          Connections deepen the signal over time — you can always return here to add more.
        </p>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useVibeStore } from '@/composables/useVibeStore'
import { useAuthStore } from '@/composables/useAuthStore'
import { useAdminStore } from '@/composables/useAdminStore'
import RadarIcon from '@/components/icons/RadarIcon.vue'
import SignalIcon from '@/components/icons/SignalIcon.vue'
import SpotifyConnect from '@/components/SpotifyConnect.vue'
import TwitterConnect from '@/components/TwitterConnect.vue'
import StravaConnect from '@/components/StravaConnect.vue'
import CoStarConnect from '@/components/CoStarConnect.vue'
import LetterboxdConnect from '@/components/LetterboxdConnect.vue'
import SteamConnect from '@/components/SteamConnect.vue'
import GCalConnect from '@/components/GCalConnect.vue'
import GitHubConnect from '@/components/GitHubConnect.vue'
import YouTubeConnect from '@/components/YouTubeConnect.vue'
import RedditConnect from '@/components/RedditConnect.vue'

const FEEDBACK_TAGS = ['felt_relevant', 'didnt_add_value', 'surprised_me', 'want_more_like_this']

const router = useRouter()
const route = useRoute()
const { oauthState, markConnected, oracleSynthesizing, dismissOracleSynthesis } = useVibeStore()

// Stagger reveals for the synthesis overlay
const synthStage = ref(0) // 0 hidden, 1 ring, 2 cards pulsing, 3 dims revealed, 4 cta
const synthCount = ref(0) // center-orb counter, animates 0 -> connected provider count
const coordinatesLocked = ref(false) // green "Coordinates locked" flash before dismiss
const showProgressNudge = ref(true)
let synthTimers: number[] = []
let synthCountRaf = 0

function clearSynthTimers() {
  synthTimers.forEach((t) => window.clearTimeout(t))
  synthTimers = []
  if (synthCountRaf) cancelAnimationFrame(synthCountRaf)
  synthCountRaf = 0
}

// Ramp the orb counter 0 -> N over 1.2s with a mono readout.
function animateSynthCount() {
  const target = synthProviderKeys.value.length
  const duration = 1200
  const start = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / duration)
    synthCount.value = Math.round(t * target)
    if (t < 1) synthCountRaf = requestAnimationFrame(step)
  }
  synthCountRaf = requestAnimationFrame(step)
}

watch(oracleSynthesizing, (active) => {
  clearSynthTimers()
  if (active) {
    synthStage.value = 1
    synthCount.value = 0
    coordinatesLocked.value = false
    synthTimers.push(window.setTimeout(() => (synthStage.value = 2), 1200))
    synthTimers.push(window.setTimeout(() => {
      synthStage.value = 3
      animateSynthCount()
    }, 3500))
    synthTimers.push(window.setTimeout(() => (synthStage.value = 4), 7800))
  } else {
    synthStage.value = 0
    synthCount.value = 0
    coordinatesLocked.value = false
  }
})

const ORACLE_DIMENSIONS = [
  { key: 'empathy', label: 'Empathy Index' },
  { key: 'isolation', label: 'Isolation Metric' },
  { key: 'fatalism', label: 'Fatalism Score' },
  { key: 'masochism', label: 'Masochism Curve' },
]

const synthProviderKeys = computed(() =>
  (Object.keys(oauthState.value) as (keyof typeof oauthState.value)[])
    .filter((k) => oauthState.value[k].connected),
)

const PROVIDER_LABELS: Record<string, string> = {
  spotify: 'Spotify',
  twitter: 'X / Twitter',
  google: 'Google Calendar',
  strava: 'Strava',
  costar: 'Co-Star',
  letterboxd: 'Letterboxd',
  steam: 'Steam',
  github: 'GitHub',
  youtube: 'YouTube',
  reddit: 'Reddit',
  instagram: 'Instagram',
  tiktok: 'TikTok',
}

function goToUniverse() {
  // Flash "Coordinates locked" for 500ms before dismissing the overlay.
  coordinatesLocked.value = true
  window.setTimeout(() => {
    dismissOracleSynthesis()
    router.push('/universe')
  }, 500)
}
const { apiFetch } = useAuthStore()
const { submitConnectorFeedback } = useAdminStore()

interface SpotifyProfile {
  top_artists: string[]
  genres: string[]
  audio_avg: { valence: number; danceability: number; energy: number; acousticness: number; tempo: number }
}

interface StravaProfile {
  athlete_name: string
  activity_types: Record<string, number>
  recent_count: number
  total_elevation_m: number
  total_distance_km: number
  total_moving_hours: number
  avg_heartrate: number | null
  max_heartrate: number | null
  all_time_runs: number
  all_time_run_distance_km: number
  all_time_rides: number
  all_time_ride_distance_km: number
}

interface TwitterProfile {
  username: string
  bio: string
  followers_count: number
  following_count: number
}

// interface SteamProfile {
//   recent_games: { name: string; playtime_2weeks: number }[]
//   total_games: number
//   total_hours: number
// }

interface GitHubProfile {
  username: string
  bio: string
  top_languages: string[]
  public_repos: number
  stars: number
  owned_ratio: number
  account_age_years: number
  topics: string[]
}

interface YouTubeProfile {
  channel_name: string
  subscriber_count: number
  video_count: number
  view_count: number
  top_subscriptions: string[]
  subscription_categories: Record<string, number>
}

interface GCalProfile {
  peak_hours: number[]
  overcommitment_ratio: number
  meeting_density: string
  avg_events_per_week: number
}

interface RedditProfile {
  username: string
  total_karma: number
  comment_karma: number
  link_karma: number
  subreddits: string[]
  active_hours: number[]
  lurker_ratio: number
}

const spotifyProfile = ref<SpotifyProfile | null>(null)
const spotifyLoading = ref(false)
const stravaProfile = ref<StravaProfile | null>(null)
const stravaLoading = ref(false)
const twitterProfile = ref<TwitterProfile | null>(null)
const twitterLoading = ref(false)
// const steamProfile = ref<SteamProfile | null>(null)
// const steamLoading = ref(false)
const githubProfile = ref<GitHubProfile | null>(null)
const githubLoading = ref(false)
const youtubeProfile = ref<YouTubeProfile | null>(null)
const youtubeLoading = ref(false)
const gcalProfile = ref<GCalProfile | null>(null)
const gcalLoading = ref(false)
const redditProfile = ref<RedditProfile | null>(null)
const redditLoading = ref(false)

function valenceLabel(v: number): string {
  if (v < 0.3) return 'Melancholic'
  if (v <= 0.5) return 'Bittersweet'
  if (v <= 0.7) return 'Luminous'
  return 'Euphoric'
}

const GENRE_COLORS = [
  'bg-green-500/20 text-green-300 border-green-500/40',
  'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  'bg-teal-500/20 text-teal-300 border-teal-500/40',
]

async function fetchSpotifyProfile() {
  if (spotifyProfile.value || spotifyLoading.value) return
  spotifyLoading.value = true
  try {
    spotifyProfile.value = await apiFetch<SpotifyProfile>('/api/spotify/profile')
    // If connected but no profile data, auto-sync (covers pre-ingestion connections)
    if (!spotifyProfile.value && oauthState.value.spotify.connected) {
      const result = await apiFetch<{ profile: SpotifyProfile }>('/api/spotify/sync', { method: 'POST' })
      if (result?.profile) spotifyProfile.value = result.profile
    }
  } catch { /* non-blocking */ }
  spotifyLoading.value = false
}

async function fetchStravaProfile() {
  if (stravaProfile.value || stravaLoading.value) return
  stravaLoading.value = true
  try {
    stravaProfile.value = await apiFetch<StravaProfile>('/api/strava/profile')
  } catch { /* non-blocking */ }
  stravaLoading.value = false
}

async function fetchTwitterProfile() {
  if (twitterProfile.value || twitterLoading.value) return
  twitterLoading.value = true
  try {
    twitterProfile.value = await apiFetch<TwitterProfile>('/api/twitter/profile')
  } catch { /* non-blocking */ }
  twitterLoading.value = false
}

// async function fetchSteamProfile() {
//   if (steamProfile.value || steamLoading.value) return
//   steamLoading.value = true
//   try {
//     steamProfile.value = await apiFetch<SteamProfile>('/api/steam/profile')
//   } catch { /* non-blocking */ }
//   steamLoading.value = false
// }

async function fetchGCalProfile() {
  if (gcalProfile.value || gcalLoading.value) return
  gcalLoading.value = true
  try {
    gcalProfile.value = await apiFetch<GCalProfile>('/api/gcal/profile')
  } catch { /* non-blocking */ }
  gcalLoading.value = false
}

async function fetchGitHubProfile() {
  if (githubProfile.value || githubLoading.value) return
  githubLoading.value = true
  try {
    githubProfile.value = await apiFetch<GitHubProfile>('/api/github/profile')
  } catch { /* non-blocking */ }
  githubLoading.value = false
}

async function fetchYouTubeProfile() {
  if (youtubeProfile.value || youtubeLoading.value) return
  youtubeLoading.value = true
  try {
    youtubeProfile.value = await apiFetch<YouTubeProfile>('/api/youtube/profile')
  } catch { /* non-blocking */ }
  youtubeLoading.value = false
}

async function fetchRedditProfile() {
  if (redditProfile.value || redditLoading.value) return
  redditLoading.value = true
  try {
    redditProfile.value = await apiFetch<RedditProfile>('/api/reddit/profile')
  } catch { /* non-blocking */ }
  redditLoading.value = false
}

const pendingRating = reactive<Record<string, number>>({})
const selectedTags = reactive<Record<string, string[]>>({})
const feedbackGiven = reactive<Record<string, boolean>>({})

const connectedSources = computed(() => {
  const all = [
    { key: 'spotify',    label: 'Spotify',     state: oauthState.value.spotify },
    { key: 'twitter',    label: 'X / Twitter',  state: oauthState.value.twitter },
    { key: 'strava',     label: 'Strava',       state: oauthState.value.strava },
    { key: 'google',     label: 'Google Calendar', state: oauthState.value.google },
    { key: 'costar',     label: 'Co-Star',      state: oauthState.value.costar },
    { key: 'letterboxd', label: 'Letterboxd',   state: oauthState.value.letterboxd },
    { key: 'steam',      label: 'Steam',        state: oauthState.value.steam },
    { key: 'github',     label: 'GitHub',       state: oauthState.value.github },
    { key: 'youtube',    label: 'YouTube',      state: oauthState.value.youtube },
    { key: 'reddit',     label: 'Reddit',       state: oauthState.value.reddit },
    { key: 'instagram',  label: 'Instagram',    state: oauthState.value.instagram },
    { key: 'tiktok',     label: 'TikTok',       state: oauthState.value.tiktok },
  ]
  return all
    .filter(s => s.state.connected)
    .map(s => ({ key: s.key, label: s.label, lastSync: s.state.lastSync }))
})

function setRating(provider: string, n: number) {
  pendingRating[provider] = n
  if (!selectedTags[provider]) selectedTags[provider] = []
}

function toggleTag(provider: string, tag: string) {
  if (!selectedTags[provider]) selectedTags[provider] = []
  const idx = selectedTags[provider].indexOf(tag)
  if (idx === -1) selectedTags[provider].push(tag)
  else selectedTags[provider].splice(idx, 1)
}

async function submitFeedback(provider: string) {
  const rating = pendingRating[provider]
  if (!rating) return
  feedbackGiven[provider] = true  // close immediately regardless of API result
  try {
    await submitConnectorFeedback(provider, rating, selectedTags[provider] || [])
  } catch { /* non-blocking */ }
}

watch(() => oauthState.value.spotify.connected, (connected) => {
  if (connected) fetchSpotifyProfile()
}, { immediate: true })

watch(() => oauthState.value.strava.connected, (connected) => {
  if (connected) fetchStravaProfile()
}, { immediate: true })

watch(() => oauthState.value.twitter.connected, (connected) => {
  if (connected) fetchTwitterProfile()
}, { immediate: true })

watch(() => oauthState.value.google.connected, (connected) => {
  if (connected) fetchGCalProfile()
}, { immediate: true })

// watch(() => oauthState.value.steam.connected, (connected) => {
//   if (connected) fetchSteamProfile()
// }, { immediate: true })

watch(() => oauthState.value.github.connected, (connected) => {
  if (connected) fetchGitHubProfile()
}, { immediate: true })

watch(() => oauthState.value.youtube.connected, (connected) => {
  if (connected) fetchYouTubeProfile()
}, { immediate: true })

watch(() => oauthState.value.reddit.connected, (connected) => {
  if (connected) fetchRedditProfile()
}, { immediate: true })

onMounted(() => {
  if (route.query.spotify === 'connected') {
    markConnected('spotify')
    router.replace({ path: '/calibrate/spotify' })
  }
  if (route.query.gcal === 'connected') {
    markConnected('google')
    router.replace({ path: '/calibrate/google' })
  }
  if (route.query.twitter === 'connected') {
    markConnected('twitter')
    router.replace({ path: '/calibrate/twitter' })
  }
  if (route.query.steam === 'connected') {
    markConnected('steam')
    // steam has no connectorConfig entry — /calibrate/steam renders empty
    router.replace({ path: '/calibrate' })
  }
  if (route.query.strava === 'connected') {
    markConnected('strava')
    router.replace({ path: '/calibrate/strava' })
  }
  if (route.query.github === 'connected') {
    markConnected('github')
    router.replace({ path: '/calibrate/github' })
  }
  if (route.query.youtube === 'connected') {
    markConnected('youtube')
    router.replace({ path: '/calibrate/youtube' })
  }
  if (route.query.reddit === 'connected') {
    markConnected('reddit')
    router.replace({ path: '/calibrate/reddit' })
  }
  if (route.query.instagram === 'connected') {
    markConnected('instagram')
    router.replace({ path: '/calibrate/instagram' })
  }
  if (route.query.tiktok === 'connected') {
    markConnected('tiktok')
    router.replace({ path: '/calibrate/tiktok' })
  }
})

function proceed() {
  router.push('/intake')
}
</script>

<style scoped>
/* Dark-forest palette — matches HomeView #08060e base */
.calibrate-bg { background: #08060e; }
.oracle-overlay { background: rgba(2, 1, 6, 0.95); }
.ccard-active { background: rgba(15, 10, 30, 0.9); }
.ccard-idle {
  background: rgba(15, 10, 30, 0.85);
  border-color: rgba(255, 255, 255, 0.08);
}
.ccard-coming {
  background: rgba(15, 10, 30, 0.5);
  border-color: rgba(255, 255, 255, 0.05);
}
.ccard-sources { background: rgba(15, 10, 30, 0.5); }
.skel-line { background: rgba(30, 20, 55, 0.8); }
.bar-track { background: rgba(30, 20, 55, 0.8); }

@media (prefers-reduced-motion: reduce) {
  .oracle-ping { animation: none !important; opacity: 0.4; }
}

@keyframes synth-card-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(168, 85, 247, 0.6); transform: scale(1); }
  50%  { box-shadow: 0 0 18px 4px rgba(168, 85, 247, 0.45); transform: scale(1.06); }
  100% { box-shadow: 0 0 0 0 rgba(168, 85, 247, 0); transform: scale(1); }
}
@keyframes synth-fade-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.animate-fade-in {
  animation: synth-fade-in 600ms ease-out both;
}
</style>
