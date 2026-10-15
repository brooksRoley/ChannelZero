<script setup lang="ts">
import { computed, watch, defineAsyncComponent, type Component } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { LEARN_TOPICS, type LearnTopic, type LearnAnimation } from '@/data/learn'
import { useAuthStore } from '@/composables/useAuthStore'

const ANIMATIONS: Record<LearnAnimation, Component> = {
  'enfractionation': defineAsyncComponent(() => import('@/components/learn/EnfractionationAnim.vue')),
  'binaural-entrainment': defineAsyncComponent(() => import('@/components/learn/BinauralEntrainmentAnim.vue')),
  'protocol': defineAsyncComponent(() => import('@/components/learn/ProtocolAnim.vue')),
}

const route = useRoute()
const { isAuthenticated } = useAuthStore()

const slug = computed(() => String(route.params.slug ?? ''))

const topicIndex = computed(() =>
  LEARN_TOPICS.findIndex((t) => t.slug === slug.value)
)

const topic = computed<LearnTopic | undefined>(() =>
  topicIndex.value >= 0 ? LEARN_TOPICS[topicIndex.value] : undefined
)

const prevTopic = computed<LearnTopic | undefined>(() => {
  const i = topicIndex.value
  return i > 0 ? LEARN_TOPICS[i - 1] : undefined
})

const nextTopic = computed<LearnTopic | undefined>(() => {
  const i = topicIndex.value
  return i >= 0 && i < LEARN_TOPICS.length - 1 ? LEARN_TOPICS[i + 1] : undefined
})

const animationComponent = computed<Component | undefined>(() =>
  topic.value?.animation ? ANIMATIONS[topic.value.animation] : undefined
)

// Connector articles link to /calibrate (auth-required). For guest users,
// reroute to /discovery so they land on a signup flow instead of a bare login wall.
const isConnectorArticle = computed(() =>
  topic.value?.linkedSession?.to === '/calibrate'
)

const ctaTo = computed(() =>
  isConnectorArticle.value && !isAuthenticated.value
    ? '/discovery'
    : (topic.value?.linkedSession?.to ?? '/')
)

const ctaLabel = computed(() =>
  isConnectorArticle.value && !isAuthenticated.value
    ? 'Join ChannelZero to try it'
    : (topic.value?.linkedSession?.label ?? '')
)

// Re-scroll to top when slug changes
watch(
  () => route.params.slug,
  () => {
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'auto' })
    }
  }
)
</script>

<template>
  <main class="learn-article">
    <template v-if="topic">
      <article class="article">
        <nav class="breadcrumb" aria-label="Breadcrumb">
          <RouterLink to="/learn" class="crumb-link">Learn</RouterLink>
          <span class="crumb-sep" aria-hidden="true">/</span>
          <span class="crumb-current">{{ topic.phaseName }}</span>
        </nav>

        <span class="phase-badge">
          Phase {{ topic.phase }} <span class="dot" aria-hidden="true">·</span> {{ topic.phaseName }}
        </span>

        <h1 class="title">{{ topic.title }}</h1>

        <p class="lead">{{ topic.shortDescription }}</p>

        <component :is="animationComponent" v-if="animationComponent" :key="topic.slug" />

        <section class="section">
          <h2>Definition</h2>
          <p>{{ topic.sections.definition }}</p>
        </section>

        <section class="section">
          <h2>How it works</h2>
          <p>{{ topic.sections.mechanism }}</p>
        </section>

        <section class="section">
          <h2>In practice on ChannelZero</h2>
          <p>{{ topic.sections.inPractice }}</p>
        </section>

        <div v-if="topic.linkedSession" class="cta-row">
          <RouterLink :to="ctaTo" class="cta-btn">
            {{ ctaLabel }} <span aria-hidden="true">&rarr;</span>
          </RouterLink>
        </div>
      </article>

      <nav v-if="prevTopic || nextTopic" class="article-nav" aria-label="Article navigation">
        <RouterLink
          v-if="prevTopic"
          :to="`/learn/${prevTopic.slug}`"
          class="nav-link nav-prev"
        >
          <span class="nav-label"><span aria-hidden="true">&larr;</span> Previous</span>
          <span class="nav-title">{{ prevTopic.title }}</span>
        </RouterLink>
        <span v-else class="nav-link nav-spacer" aria-hidden="true"></span>

        <RouterLink
          v-if="nextTopic"
          :to="`/learn/${nextTopic.slug}`"
          class="nav-link nav-next"
        >
          <span class="nav-label">Next <span aria-hidden="true">&rarr;</span></span>
          <span class="nav-title">{{ nextTopic.title }}</span>
        </RouterLink>
        <span v-else class="nav-link nav-spacer" aria-hidden="true"></span>
      </nav>
    </template>

    <section v-else class="not-found">
      <h1>Topic not found</h1>
      <p>We couldn't find a learn topic for "{{ slug }}".</p>
      <RouterLink to="/learn" class="cta-btn">
        <span aria-hidden="true">&larr;</span> Back to Learn
      </RouterLink>
    </section>
  </main>
</template>

<style scoped>
.learn-article {
  min-height: 100vh;
  background: #1a1a1a;
  color: #e2e8f0;
  padding: 3rem 1.5rem 6rem;
}

.article {
  max-width: 64ch;
  margin: 0 auto;
  line-height: 1.6;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #64748b;
  margin-bottom: 1.5rem;
}

.crumb-link {
  color: #94a3b8;
  text-decoration: none;
  transition: color 180ms ease;
}

.crumb-link:hover {
  color: #e2e8f0;
}

.crumb-sep {
  color: #3f3f3f;
}

.crumb-current {
  color: #94a3b8;
}

.phase-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.75rem;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.35);
  border-radius: 999px;
  color: #a5b4fc;
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  margin-bottom: 1.25rem;
}

.phase-badge .dot {
  color: #6366f1;
  opacity: 0.7;
}

.title {
  font-size: clamp(2rem, 4.5vw, 2.75rem);
  font-weight: 600;
  letter-spacing: -0.02em;
  margin: 0 0 1.25rem;
  line-height: 1.15;
}

.lead {
  font-size: 1.1875rem;
  line-height: 1.6;
  color: #cbd5e1;
  margin: 0 0 2.5rem;
}

.section {
  margin: 2.5rem 0;
}

.section h2 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0 0 0.875rem;
  color: #e2e8f0;
  letter-spacing: -0.01em;
}

.section p {
  margin: 0;
  font-size: 1rem;
  line-height: 1.7;
  color: #cbd5e1;
}

.cta-row {
  margin-top: 3rem;
}

.cta-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.25rem;
  background: #6366f1;
  color: #ffffff;
  text-decoration: none;
  border-radius: 8px;
  font-size: 0.9375rem;
  font-weight: 500;
  border: 1px solid #6366f1;
  transition: background 180ms ease, transform 180ms ease, border-color 180ms ease;
}

.cta-btn:hover {
  background: #4f52d6;
  border-color: #4f52d6;
  transform: translateY(-1px);
}

.article-nav {
  max-width: 64ch;
  margin: 4rem auto 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  padding-top: 2rem;
  border-top: 1px solid #2a2a2a;
}

.nav-link {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 1rem 1.125rem;
  background: #1f1f1f;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  text-decoration: none;
  color: inherit;
  transition: border-color 180ms ease, background 180ms ease;
  min-height: 4.25rem;
}

.nav-link:hover {
  border-color: #3f3f5a;
  background: #232333;
}

.nav-spacer {
  background: transparent;
  border-color: transparent;
  pointer-events: none;
}

.nav-prev {
  text-align: left;
}

.nav-next {
  text-align: right;
  align-items: flex-end;
}

.nav-label {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.nav-title {
  font-size: 0.9375rem;
  font-weight: 500;
  color: #e2e8f0;
}

.not-found {
  max-width: 36rem;
  margin: 0 auto;
  text-align: center;
  padding: 4rem 1rem;
}

.not-found h1 {
  font-size: 1.75rem;
  font-weight: 600;
  margin: 0 0 0.75rem;
}

.not-found p {
  color: #94a3b8;
  margin: 0 0 2rem;
}

@media (max-width: 540px) {
  .article-nav {
    grid-template-columns: 1fr;
  }
  .nav-next {
    text-align: left;
    align-items: flex-start;
  }
}
</style>
