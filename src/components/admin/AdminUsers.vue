<template>
  <div class="space-y-8">
    <PanelError :message="errors.spotify || errors.psychometrics" />
  <!-- Spotify Profiles -->
  <section v-if="spotifyProfiles.length">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
      Spotify Profiles
      <span class="ml-2 text-gray-600 normal-case text-xs font-normal">{{ spotifyTotal }} total</span>
    </h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="sp in spotifyProfiles"
        :key="sp.user_id"
        class="bg-gray-900 border border-gray-800 rounded-xl p-5"
      >
        <div class="font-medium text-white text-sm mb-1">{{ sp.display_name || sp.email }}</div>
        <div class="flex flex-wrap gap-1 mb-3">
          <span
            v-for="a in sp.top_artists.slice(0, 3)"
            :key="a"
            class="text-xs px-2 py-0.5 bg-green-900/30 text-green-400 rounded-full"
          >{{ a }}</span>
        </div>
        <div class="flex flex-wrap gap-1 mb-3">
          <span
            v-for="g in sp.genres.slice(0, 4)"
            :key="g"
            class="text-xs px-2 py-0.5 bg-gray-800 text-gray-400 rounded-full"
          >{{ g }}</span>
        </div>
        <div class="space-y-1">
          <div v-for="(val, key) in sp.audio_avg" :key="key" class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-24 truncate capitalize">{{ key }}</span>
            <div class="flex-1 h-1.5 bg-gray-800 rounded-full">
              <div
                class="h-1.5 bg-green-500 rounded-full"
                :style="{ width: `${Math.min(key === 'tempo' ? val / 200 * 100 : val * 100, 100)}%` }"
              ></div>
            </div>
            <span class="text-xs text-gray-500 w-10 text-right">{{ typeof val === 'number' ? val.toFixed(2) : val }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="spotifyTotal > spotifyPerPage" class="flex justify-center gap-2 mt-4">
      <button
        :disabled="spotifyPage <= 1"
        @click="goSpotifyPage(spotifyPage - 1)"
        class="px-3 py-1.5 rounded-lg border border-gray-800 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >Prev</button>
      <span class="px-3 py-1.5 text-sm text-gray-500">{{ spotifyPage }} / {{ Math.ceil(spotifyTotal / spotifyPerPage) }}</span>
      <button
        :disabled="spotifyPage >= Math.ceil(spotifyTotal / spotifyPerPage)"
        @click="goSpotifyPage(spotifyPage + 1)"
        class="px-3 py-1.5 rounded-lg border border-gray-800 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >Next</button>
    </div>
  </section>

  <!-- Psychometric Profiles -->
  <section v-if="psychProfiles.length">
    <h2 class="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">
      Psychometrics
      <span class="ml-2 text-gray-600 normal-case text-xs font-normal">{{ psychTotal }} total</span>
    </h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="pm in psychProfiles"
        :key="pm.user_id"
        class="bg-gray-900 border border-gray-800 rounded-xl p-5"
      >
        <div class="font-medium text-white text-sm mb-2">{{ pm.display_name || pm.email }}</div>
        <div class="flex flex-wrap gap-1 mb-3">
          <span v-if="pm.love_language" class="text-xs px-2 py-0.5 bg-pink-900/30 text-pink-400 rounded-full">{{ pm.love_language }}</span>
          <span v-if="pm.values_cluster" class="text-xs px-2 py-0.5 bg-blue-900/30 text-blue-400 rounded-full">{{ pm.values_cluster }}</span>
          <span v-if="pm.sociosexual_orientation" class="text-xs px-2 py-0.5 bg-purple-900/30 text-purple-400 rounded-full">{{ pm.sociosexual_orientation }}</span>
        </div>
        <div v-if="pm.ipip_neo_scores" class="space-y-1 mb-2">
          <div v-for="(val, trait) in pm.ipip_neo_scores" :key="trait" class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-24 truncate capitalize">{{ trait }}</span>
            <div class="flex-1 h-1.5 bg-gray-800 rounded-full">
              <div
                class="h-1.5 bg-purple-500 rounded-full"
                :style="{ width: `${Math.min(Number(val) * 100, 100)}%` }"
              ></div>
            </div>
            <span class="text-xs text-gray-500 w-10 text-right">{{ Number(val).toFixed(2) }}</span>
          </div>
        </div>
        <p v-if="pm.narrative" class="text-xs text-gray-500 leading-relaxed line-clamp-3">{{ pm.narrative }}</p>
      </div>
    </div>
    <div v-if="psychTotal > psychPerPage" class="flex justify-center gap-2 mt-4">
      <button
        :disabled="psychPage <= 1"
        @click="goPsychPage(psychPage - 1)"
        class="px-3 py-1.5 rounded-lg border border-gray-800 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >Prev</button>
      <span class="px-3 py-1.5 text-sm text-gray-500">{{ psychPage }} / {{ Math.ceil(psychTotal / psychPerPage) }}</span>
      <button
        :disabled="psychPage >= Math.ceil(psychTotal / psychPerPage)"
        @click="goPsychPage(psychPage + 1)"
        class="px-3 py-1.5 rounded-lg border border-gray-800 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >Next</button>
    </div>
  </section>

  <!-- Users Table -->
  <section>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xs font-semibold uppercase tracking-widest text-gray-500">
        Users
        <span class="ml-2 text-gray-600 normal-case text-xs font-normal">{{ usersTotal }} total</span>
      </h2>
      <div class="flex items-center gap-3">
        <input
          v-model="search"
          placeholder="Filter by email or name..."
          class="bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 w-56"
        />
      </div>
    </div>

    <PanelError :message="errors.users" />
    <div v-if="loading" class="text-center py-12 text-gray-600">Loading...</div>

    <div v-else class="overflow-x-auto rounded-xl border border-gray-800">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
            <th class="text-left px-4 py-3">User</th>
            <th class="text-left px-4 py-3">Joined</th>
            <th class="text-left px-4 py-3">Archetype</th>
            <th class="text-left px-4 py-3">Attachment</th>
            <th class="text-center px-4 py-3">Connectors</th>
            <th class="text-center px-4 py-3">Journal</th>
            <th class="text-left px-4 py-3">Providers</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/50">
          <template v-for="u in filteredUsers" :key="u.id">
            <tr
              class="hover:bg-gray-900/50 transition-colors cursor-pointer"
              :class="expandedUser === u.id ? 'bg-gray-900/70' : ''"
              @click="toggleUserDetail(u.id)"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-white">{{ u.display_name || '—' }}</div>
                <div class="text-gray-500 text-xs">{{ u.email }}</div>
              </td>
              <td class="px-4 py-3 text-gray-400 whitespace-nowrap">
                {{ formatDate(u.created_at) }}
              </td>
              <td class="px-4 py-3">
                <span v-if="u.archetype" class="text-purple-400 text-xs font-medium">{{ u.archetype }}</span>
                <span v-else class="text-gray-700">—</span>
              </td>
              <td class="px-4 py-3">
                <span v-if="u.attachment_style" class="text-blue-400 text-xs">{{ u.attachment_style }}</span>
                <span v-else class="text-gray-700">—</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span
                  class="inline-block w-6 h-6 rounded-full text-xs font-bold leading-6 text-center"
                  :class="connectorColor(u.connector_count)"
                >{{ u.connector_count }}</span>
              </td>
              <td class="px-4 py-3 text-center text-gray-400">{{ u.journal_entry_count }}</td>
              <td class="px-4 py-3">
                <div class="flex gap-1 flex-wrap">
                  <span
                    v-for="p in (u.connected_providers || [])"
                    :key="p"
                    class="text-xs px-1.5 py-0.5 rounded"
                    :class="providerPillClass(p)"
                  >{{ p }}</span>
                </div>
              </td>
            </tr>

            <!-- Expanded connector detail row -->
            <tr v-if="expandedUser === u.id">
              <td colspan="7" class="px-4 py-4 bg-gray-900/50">
                <div v-if="expandedLoading" class="text-center py-6 text-gray-600 text-xs">Loading connector data...</div>
                <div v-else-if="!expandedData || Object.values(expandedData).every(v => v === null)" class="text-center py-6 text-gray-600 text-xs">No connector data ingested yet</div>
                <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">

                  <!-- Spotify -->
                  <div v-if="expandedData.spotify" class="border border-green-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-green-400 uppercase tracking-wider mb-2">Spotify</div>
                    <div v-if="expandedData.spotify.top_artists?.length" class="mb-2">
                      <span class="text-[10px] text-gray-500 uppercase">Artists</span>
                      <div class="flex flex-wrap gap-1 mt-1">
                        <span v-for="a in expandedData.spotify.top_artists.slice(0, 5)" :key="a"
                              class="text-xs px-2 py-0.5 bg-green-900/30 text-green-300 rounded-full">{{ a }}</span>
                      </div>
                    </div>
                    <div v-if="expandedData.spotify.genres?.length" class="mb-2">
                      <span class="text-[10px] text-gray-500 uppercase">Genres</span>
                      <div class="flex flex-wrap gap-1 mt-1">
                        <span v-for="g in expandedData.spotify.genres.slice(0, 5)" :key="g"
                              class="text-xs px-2 py-0.5 bg-gray-800 text-gray-400 rounded-full">{{ g }}</span>
                      </div>
                    </div>
                    <div v-if="expandedData.spotify.audio_avg" class="space-y-1">
                      <div v-for="(val, key) in expandedData.spotify.audio_avg" :key="key" class="flex items-center gap-2">
                        <span class="text-[10px] text-gray-500 w-20 capitalize">{{ key }}</span>
                        <div class="flex-1 h-1 bg-gray-800 rounded-full">
                          <div class="h-1 bg-green-500/60 rounded-full" :style="{ width: `${Math.min(String(key) === 'tempo' ? Number(val) / 200 * 100 : Number(val) * 100, 100)}%` }"></div>
                        </div>
                        <span class="text-[10px] text-gray-500 w-8 text-right">{{ typeof val === 'number' ? val.toFixed(2) : val }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- Twitter -->
                  <div v-if="expandedData.twitter" class="border border-blue-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-2">X / Twitter</div>
                    <div v-if="expandedData.twitter.username" class="text-sm text-blue-300 mb-1">@{{ expandedData.twitter.username }}</div>
                    <div v-if="expandedData.twitter.bio" class="text-xs text-gray-400 mb-2 line-clamp-2">{{ expandedData.twitter.bio }}</div>
                    <div class="grid grid-cols-2 gap-2 text-xs">
                      <div v-if="expandedData.twitter.followers_count != null"><span class="text-gray-500">Followers</span> <span class="text-white ml-1">{{ expandedData.twitter.followers_count.toLocaleString() }}</span></div>
                      <div v-if="expandedData.twitter.following_count != null"><span class="text-gray-500">Following</span> <span class="text-white ml-1">{{ expandedData.twitter.following_count.toLocaleString() }}</span></div>
                    </div>
                  </div>

                  <!-- Strava -->
                  <div v-if="expandedData.strava" class="border border-orange-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-orange-400 uppercase tracking-wider mb-2">Strava</div>
                    <div v-if="expandedData.strava.athlete_name" class="text-sm text-orange-300 mb-1">{{ expandedData.strava.athlete_name }}</div>
                    <div v-if="expandedData.strava.activity_types" class="mb-2">
                      <div class="flex flex-wrap gap-1">
                        <span v-for="(count, type) in expandedData.strava.activity_types" :key="type"
                              class="text-xs px-2 py-0.5 bg-orange-900/30 text-orange-300 rounded-full">{{ count }} {{ type }}{{ count !== 1 ? 's' : '' }}</span>
                      </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-xs">
                      <div><span class="text-gray-500">Distance</span> <span class="text-white ml-1">{{ Math.round(expandedData.strava.total_distance_km || 0).toLocaleString() }} km</span></div>
                      <div><span class="text-gray-500">Elevation</span> <span class="text-white ml-1">{{ Math.round(expandedData.strava.total_elevation_m || 0).toLocaleString() }} m</span></div>
                      <div v-if="expandedData.strava.avg_heartrate"><span class="text-gray-500">Avg HR</span> <span class="text-white ml-1">{{ Math.round(expandedData.strava.avg_heartrate) }} bpm</span></div>
                      <div><span class="text-gray-500">Hours</span> <span class="text-white ml-1">{{ (expandedData.strava.total_moving_hours || 0).toFixed(1) }}</span></div>
                    </div>
                  </div>

                  <!-- Steam -->
                  <div v-if="expandedData.steam" class="border border-blue-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-2">Steam</div>
                    <div v-if="expandedData.steam.recent_games?.length" class="mb-2">
                      <span class="text-[10px] text-gray-500 uppercase">Recent Games</span>
                      <div class="flex flex-wrap gap-1 mt-1">
                        <span v-for="g in expandedData.steam.recent_games.slice(0, 4)" :key="g.name"
                              class="text-xs px-2 py-0.5 bg-blue-900/30 text-blue-300 rounded-full">{{ g.name }}</span>
                      </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-xs">
                      <div><span class="text-gray-500">Games</span> <span class="text-white ml-1">{{ expandedData.steam.total_games || 0 }}</span></div>
                      <div><span class="text-gray-500">Hours</span> <span class="text-white ml-1">{{ Math.round(expandedData.steam.total_hours || 0).toLocaleString() }}</span></div>
                    </div>
                  </div>

                  <!-- GitHub -->
                  <div v-if="expandedData.github" class="border border-purple-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">GitHub</div>
                    <div v-if="expandedData.github.username" class="text-sm text-purple-300 mb-1">{{ expandedData.github.username }}</div>
                    <div v-if="expandedData.github.top_languages?.length" class="mb-2">
                      <div class="flex flex-wrap gap-1">
                        <span v-for="l in expandedData.github.top_languages.slice(0, 4)" :key="l"
                              class="text-xs px-2 py-0.5 bg-purple-900/30 text-purple-300 rounded-full">{{ l }}</span>
                      </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-xs">
                      <div><span class="text-gray-500">Repos</span> <span class="text-white ml-1">{{ expandedData.github.public_repos || 0 }}</span></div>
                      <div><span class="text-gray-500">Stars</span> <span class="text-white ml-1">{{ (expandedData.github.stars || 0).toLocaleString() }}</span></div>
                    </div>
                  </div>

                  <!-- YouTube -->
                  <div v-if="expandedData.youtube" class="border border-red-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">YouTube</div>
                    <div v-if="expandedData.youtube.channel_title" class="text-sm text-red-300 mb-1">{{ expandedData.youtube.channel_title }}</div>
                    <div class="grid grid-cols-3 gap-2 text-xs mb-2">
                      <div><span class="text-gray-500">Subs</span> <span class="text-white ml-1">{{ (expandedData.youtube.subscriber_count || 0).toLocaleString() }}</span></div>
                      <div><span class="text-gray-500">Videos</span> <span class="text-white ml-1">{{ (expandedData.youtube.video_count || 0).toLocaleString() }}</span></div>
                      <div><span class="text-gray-500">Views</span> <span class="text-white ml-1">{{ (expandedData.youtube.view_count || 0).toLocaleString() }}</span></div>
                    </div>
                    <div v-if="expandedData.youtube.subscription_categories && Object.keys(expandedData.youtube.subscription_categories).length" class="flex flex-wrap gap-1">
                      <span v-for="cat in Object.keys(expandedData.youtube.subscription_categories).slice(0, 4)" :key="cat"
                            class="text-xs px-2 py-0.5 bg-red-900/30 text-red-300 rounded-full">{{ cat }}</span>
                    </div>
                  </div>

                  <!-- Reddit -->
                  <div v-if="expandedData.reddit" class="border border-orange-600/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-orange-500 uppercase tracking-wider mb-2">Reddit</div>
                    <div v-if="expandedData.reddit.username" class="text-sm text-orange-400 mb-1">u/{{ expandedData.reddit.username }}</div>
                    <div class="grid grid-cols-2 gap-2 text-xs mb-2">
                      <div><span class="text-gray-500">Karma</span> <span class="text-white ml-1">{{ (expandedData.reddit.total_karma || 0).toLocaleString() }}</span></div>
                      <div><span class="text-gray-500">Lurker</span> <span class="text-white ml-1">{{ ((expandedData.reddit.lurker_ratio || 0) * 100).toFixed(0) }}%</span></div>
                    </div>
                    <div v-if="expandedData.reddit.subreddits?.length" class="flex flex-wrap gap-1">
                      <span v-for="s in expandedData.reddit.subreddits.slice(0, 4)" :key="s"
                            class="text-xs px-2 py-0.5 bg-orange-900/30 text-orange-300 rounded-full">r/{{ s }}</span>
                    </div>
                  </div>

                  <!-- Instagram -->
                  <div v-if="expandedData.instagram" class="border border-pink-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-pink-400 uppercase tracking-wider mb-2">Instagram</div>
                    <div class="text-xs text-gray-400">
                      <template v-for="(val, key) in expandedData.instagram" :key="key">
                        <div class="flex justify-between py-0.5">
                          <span class="text-gray-500 capitalize">{{ String(key).replace(/_/g, ' ') }}</span>
                          <span class="text-white">{{ typeof val === 'object' ? JSON.stringify(val).slice(0, 40) : val }}</span>
                        </div>
                      </template>
                    </div>
                  </div>

                  <!-- TikTok -->
                  <div v-if="expandedData.tiktok" class="border border-cyan-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-cyan-400 uppercase tracking-wider mb-2">TikTok</div>
                    <div class="text-xs text-gray-400">
                      <template v-for="(val, key) in expandedData.tiktok" :key="key">
                        <div class="flex justify-between py-0.5">
                          <span class="text-gray-500 capitalize">{{ String(key).replace(/_/g, ' ') }}</span>
                          <span class="text-white">{{ typeof val === 'object' ? JSON.stringify(val).slice(0, 40) : val }}</span>
                        </div>
                      </template>
                    </div>
                  </div>

                  <!-- GCal -->
                  <div v-if="expandedData.gcal" class="border border-red-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">Google Calendar</div>
                    <div class="text-xs text-gray-400">
                      <template v-for="(val, key) in expandedData.gcal" :key="key">
                        <div class="flex justify-between py-0.5">
                          <span class="text-gray-500 capitalize">{{ String(key).replace(/_/g, ' ') }}</span>
                          <span class="text-white">{{ typeof val === 'object' ? JSON.stringify(val).slice(0, 40) : val }}</span>
                        </div>
                      </template>
                    </div>
                  </div>

                  <!-- CoStar -->
                  <div v-if="expandedData.costar" class="border border-indigo-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-2">Co-Star</div>
                    <div class="text-xs text-gray-400">
                      <template v-for="(val, key) in expandedData.costar" :key="key">
                        <div class="flex justify-between py-0.5">
                          <span class="text-gray-500 capitalize">{{ String(key).replace(/_/g, ' ') }}</span>
                          <span class="text-white">{{ typeof val === 'object' ? JSON.stringify(val).slice(0, 40) : val }}</span>
                        </div>
                      </template>
                    </div>
                  </div>

                  <!-- Letterboxd -->
                  <div v-if="expandedData.letterboxd" class="border border-emerald-500/20 rounded-lg p-4 bg-gray-950/50">
                    <div class="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-2">Letterboxd</div>
                    <div class="text-xs text-gray-400">
                      <template v-for="(val, key) in expandedData.letterboxd" :key="key">
                        <div class="flex justify-between py-0.5">
                          <span class="text-gray-500 capitalize">{{ String(key).replace(/_/g, ' ') }}</span>
                          <span class="text-white">{{ typeof val === 'object' ? JSON.stringify(val).slice(0, 40) : val }}</span>
                        </div>
                      </template>
                    </div>
                  </div>

                </div>
              </td>
            </tr>
          </template>
          <tr v-if="filteredUsers.length === 0">
            <td colspan="7" class="text-center py-8 text-gray-600">No users found</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="usersTotal > perPage" class="flex justify-center gap-2 mt-4">
      <button
        :disabled="usersPage <= 1"
        @click="goPage(usersPage - 1)"
        class="px-3 py-1.5 rounded-lg border border-gray-800 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >Prev</button>
      <span class="px-3 py-1.5 text-sm text-gray-500">
        {{ usersPage }} / {{ Math.ceil(usersTotal / perPage) }}
      </span>
      <button
        :disabled="usersPage >= Math.ceil(usersTotal / perPage)"
        @click="goPage(usersPage + 1)"
        class="px-3 py-1.5 rounded-lg border border-gray-800 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
      >Next</button>
    </div>
  </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAdminStore } from '@/composables/useAdminStore'
import PanelError from './PanelError.vue'

const { users, usersTotal, usersPage,
        spotifyProfiles, spotifyTotal, spotifyPage,
        psychProfiles, psychTotal, psychPage,
        loading, errors,
        fetchUsers, fetchSpotifyProfiles, fetchPsychProfiles,
        fetchUserConnectors } = useAdminStore()

const search = ref('')
const perPage = 50
const expandedUser = ref<string | null>(null)
const expandedData = ref<Record<string, any> | null>(null)
const expandedLoading = ref(false)

async function toggleUserDetail(userId: string) {
  if (expandedUser.value === userId) {
    expandedUser.value = null
    expandedData.value = null
    return
  }
  expandedUser.value = userId
  expandedData.value = null
  expandedLoading.value = true
  try {
    expandedData.value = await fetchUserConnectors(userId)
  } catch {
    expandedData.value = null
  } finally {
    expandedLoading.value = false
  }
}

const PROVIDER_COLORS: Record<string, string> = {
  spotify: 'bg-green-900/40 text-green-400',
  twitter: 'bg-blue-900/40 text-blue-400',
  strava: 'bg-orange-900/40 text-orange-400',
  google: 'bg-red-900/40 text-red-400',
  steam: 'bg-blue-900/40 text-blue-300',
  github: 'bg-purple-900/40 text-purple-400',
  youtube: 'bg-red-900/40 text-red-300',
  reddit: 'bg-orange-900/40 text-orange-500',
  instagram: 'bg-pink-900/40 text-pink-400',
  tiktok: 'bg-cyan-900/40 text-cyan-400',
  costar: 'bg-indigo-900/40 text-indigo-400',
  letterboxd: 'bg-emerald-900/40 text-emerald-400',
}

function providerPillClass(provider: string): string {
  return PROVIDER_COLORS[provider] || 'bg-gray-800 text-gray-400'
}

const spotifyPerPage = 12
const psychPerPage = 12

async function goSpotifyPage(page: number) { await fetchSpotifyProfiles(page, spotifyPerPage) }
async function goPsychPage(page: number) { await fetchPsychProfiles(page, psychPerPage) }

async function goPage(page: number) {
  await fetchUsers(page, perPage)
}

const filteredUsers = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return users.value
  return users.value.filter(
    u => u.email.toLowerCase().includes(q) || (u.display_name || '').toLowerCase().includes(q)
  )
})

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function connectorColor(count: number) {
  if (count === 0) return 'bg-gray-800 text-gray-600'
  if (count === 1) return 'bg-yellow-900/50 text-yellow-400'
  if (count >= 2) return 'bg-green-900/50 text-green-400'
  return 'bg-gray-800 text-gray-500'
}
</script>
