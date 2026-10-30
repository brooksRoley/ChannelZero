// ── Connector result page configuration ──────────────────────────────────────

export interface ProviderConfig {
  key: string
  label: string
  subtitle: string
  color: string
  heroStats: { field: string; label: string; format: 'decimal' | 'integer' | 'percent' }[]
  tagFields: { field: string; label: string }[]
  physics: {
    particleSpeed: string
    colorTemp: string
    particleCount: string
    pulseRate: string
    sizeVariance?: string
  }
}

export const connectorConfigs: Record<string, ProviderConfig> = {
  spotify: {
    key: 'spotify',
    label: 'Spotify',
    subtitle: 'The Sonic Blueprint',
    color: '#1db954',
    heroStats: [
      { field: 'audio_avg.energy', label: 'Energy', format: 'percent' },
      { field: 'audio_avg.valence', label: 'Valence', format: 'percent' },
      { field: 'audio_avg.danceability', label: 'Danceability', format: 'percent' },
      { field: 'audio_avg.acousticness', label: 'Acousticness', format: 'percent' },
      { field: 'audio_avg.tempo', label: 'Avg Tempo', format: 'integer' },
    ],
    tagFields: [
      { field: 'genres', label: 'Top Genres' },
      { field: 'top_artists', label: 'Top Artists' },
    ],
    physics: {
      particleSpeed: 'audio_avg.energy',
      colorTemp: 'audio_avg.valence',
      particleCount: 'genres.length',
      pulseRate: 'audio_avg.tempo',
      sizeVariance: 'audio_avg.acousticness',
    },
  },

  twitter: {
    key: 'twitter',
    label: 'X / Twitter',
    subtitle: 'The Neurotic Imprint',
    color: '#1d9bf0',
    heroStats: [
      { field: 'followers', label: 'Followers', format: 'integer' },
      { field: 'following_count', label: 'Following', format: 'integer' },
      { field: 'tweet_count', label: 'Tweets', format: 'integer' },
      { field: 'avg_tweet_length', label: 'Avg Tweet Length', format: 'integer' },
      { field: 'engagement_avg.likes', label: 'Avg Likes', format: 'decimal' },
    ],
    tagFields: [
      { field: 'posting_hours', label: 'Active Hours' },
      { field: 'tweet_samples', label: 'Tweet Samples' },
    ],
    physics: {
      particleSpeed: 'engagement_avg.likes',
      colorTemp: 'avg_tweet_length',
      particleCount: 'tweet_count',
      pulseRate: 'engagement_avg.retweets',
    },
  },

  strava: {
    key: 'strava',
    label: 'Strava',
    subtitle: 'The Somatic Ledger',
    color: '#fc4c02',
    heroStats: [
      { field: 'total_distance_km', label: 'Total Distance (km)', format: 'integer' },
      { field: 'total_elevation_m', label: 'Total Elevation (m)', format: 'integer' },
      { field: 'total_moving_hours', label: 'Moving Hours', format: 'decimal' },
      { field: 'avg_heartrate', label: 'Avg Heart Rate', format: 'integer' },
      { field: 'all_time_runs', label: 'All-Time Runs', format: 'integer' },
    ],
    tagFields: [
      { field: 'activity_types', label: 'Activity Types' },
    ],
    physics: {
      particleSpeed: 'avg_heartrate',
      colorTemp: 'total_elevation_m',
      particleCount: 'all_time_runs',
      pulseRate: 'total_moving_hours',
      sizeVariance: 'total_distance_km',
    },
  },

  google: {
    key: 'google',
    label: 'Google Calendar',
    subtitle: 'The Temporal Grid',
    color: '#4285f4',
    heroStats: [
      { field: 'total_events_60d', label: 'Events (60d)', format: 'integer' },
      { field: 'events_per_week', label: 'Events / Week', format: 'decimal' },
      { field: 'calendar_count', label: 'Calendars', format: 'integer' },
      { field: 'recurring_ratio', label: 'Recurring Ratio', format: 'percent' },
      { field: 'evening_ratio', label: 'Evening Ratio', format: 'percent' },
    ],
    tagFields: [
      { field: 'day_distribution', label: 'Day Distribution' },
    ],
    physics: {
      particleSpeed: 'events_per_week',
      colorTemp: 'recurring_ratio',
      particleCount: 'total_events_60d',
      pulseRate: 'evening_ratio',
    },
  },

  github: {
    key: 'github',
    label: 'GitHub',
    subtitle: "The Builder's Ledger",
    color: '#8b5cf6',
    heroStats: [
      { field: 'public_repos', label: 'Public Repos', format: 'integer' },
      { field: 'followers', label: 'Followers', format: 'integer' },
      { field: 'stars_given', label: 'Stars Given', format: 'integer' },
      { field: 'owned_to_forked_ratio', label: 'Owned / Forked', format: 'decimal' },
      { field: 'account_age_years', label: 'Account Age (yrs)', format: 'decimal' },
    ],
    tagFields: [
      { field: 'top_languages', label: 'Top Languages' },
      { field: 'topics', label: 'Topics' },
    ],
    physics: {
      particleSpeed: 'public_repos',
      colorTemp: 'owned_to_forked_ratio',
      particleCount: 'top_languages.length',
      pulseRate: 'stars_given',
    },
  },

  youtube: {
    key: 'youtube',
    label: 'YouTube',
    subtitle: 'The Attention Archive',
    color: '#ff0000',
    heroStats: [
      { field: 'subscriber_count', label: 'Subscribers', format: 'integer' },
      { field: 'video_count', label: 'Videos', format: 'integer' },
      { field: 'view_count', label: 'Total Views', format: 'integer' },
      { field: 'subscription_diversity', label: 'Sub Diversity', format: 'decimal' },
    ],
    tagFields: [
      { field: 'top_subscriptions', label: 'Top Subscriptions' },
      { field: 'subscription_categories', label: 'Categories' },
    ],
    physics: {
      particleSpeed: 'subscription_diversity',
      colorTemp: 'view_count',
      particleCount: 'video_count',
      pulseRate: 'subscriber_count',
    },
  },

  reddit: {
    key: 'reddit',
    label: 'Reddit',
    subtitle: 'The Anonymous Confessional',
    color: '#ff4500',
    heroStats: [
      { field: 'total_karma', label: 'Total Karma', format: 'integer' },
      { field: 'comment_karma_ratio', label: 'Comment Karma Ratio', format: 'percent' },
      { field: 'account_age_days', label: 'Account Age (days)', format: 'integer' },
      { field: 'subreddit_diversity', label: 'Subreddit Diversity', format: 'decimal' },
    ],
    tagFields: [
      { field: 'top_subreddits', label: 'Top Subreddits' },
      { field: 'comment_subreddits', label: 'Comment Subreddits' },
    ],
    physics: {
      particleSpeed: 'subreddit_diversity',
      colorTemp: 'comment_karma_ratio',
      particleCount: 'top_subreddits.length',
      pulseRate: 'total_karma',
    },
  },

  letterboxd: {
    key: 'letterboxd',
    label: 'Letterboxd',
    subtitle: 'The Empathy Simulator',
    color: '#00e054',
    heroStats: [
      { field: 'diary_count', label: 'Diary Entries', format: 'integer' },
      { field: 'avg_rating', label: 'Avg Rating', format: 'decimal' },
      { field: 'ratings_given', label: 'Ratings Given', format: 'integer' },
    ],
    tagFields: [
      { field: 'recent_films', label: 'Recent Films' },
      { field: 'watchlist_sample', label: 'Watchlist' },
    ],
    physics: {
      particleSpeed: 'avg_rating',
      colorTemp: 'diary_count',
      particleCount: 'ratings_given',
      pulseRate: 'avg_rating',
    },
  },

  instagram: {
    key: 'instagram',
    label: 'Instagram',
    subtitle: 'The Curated Self',
    color: '#e1306c',
    heroStats: [
      { field: 'media_count', label: 'Posts', format: 'integer' },
      { field: 'avg_engagement', label: 'Avg Engagement', format: 'percent' },
      { field: 'posting_frequency', label: 'Posts / Week', format: 'decimal' },
      { field: 'caption_avg_length', label: 'Avg Caption Length', format: 'integer' },
      { field: 'video_ratio', label: 'Video Ratio', format: 'percent' },
    ],
    tagFields: [
      { field: 'hashtag_frequency', label: 'Top Hashtags' },
    ],
    physics: {
      particleSpeed: 'avg_engagement',
      colorTemp: 'video_ratio',
      particleCount: 'media_count',
      pulseRate: 'posting_frequency',
    },
  },

  tiktok: {
    key: 'tiktok',
    label: 'TikTok',
    subtitle: 'The Dopamine Map',
    color: '#00f2ea',
    heroStats: [
      { field: 'follower_count', label: 'Followers', format: 'integer' },
      { field: 'video_count', label: 'Videos', format: 'integer' },
      { field: 'avg_video_duration', label: 'Avg Duration (s)', format: 'decimal' },
      { field: 'avg_engagement_rate', label: 'Engagement Rate', format: 'percent' },
    ],
    tagFields: [
      { field: 'hashtags', label: 'Top Hashtags' },
      { field: 'posting_hours', label: 'Posting Hours' },
    ],
    physics: {
      particleSpeed: 'avg_engagement_rate',
      colorTemp: 'avg_video_duration',
      particleCount: 'video_count',
      pulseRate: 'follower_count',
    },
  },

  costar: {
    key: 'costar',
    label: 'Co-Star',
    subtitle: 'The Fatalistic Mirror',
    color: '#c084fc',
    heroStats: [],
    tagFields: [
      { field: 'sun', label: 'Sun' },
      { field: 'moon', label: 'Moon' },
      { field: 'rising', label: 'Rising' },
      { field: 'venus', label: 'Venus' },
      { field: 'mars', label: 'Mars' },
      { field: 'mercury', label: 'Mercury' },
      { field: 'jupiter', label: 'Jupiter' },
      { field: 'saturn', label: 'Saturn' },
    ],
    physics: {
      particleSpeed: 'sun',
      colorTemp: 'moon',
      particleCount: 'rising',
      pulseRate: 'venus',
    },
  },

  steam: {
    key: 'steam',
    label: 'Steam',
    subtitle: 'The Isolation Metric',
    color: '#1b2838',
    heroStats: [
      { field: 'game_count', label: 'Library Size', format: 'integer' },
      { field: 'total_lifetime_hours', label: 'Lifetime Hours', format: 'decimal' },
      { field: 'recent_2week_hours', label: 'Recent Activity (2wk)', format: 'decimal' },
      { field: 'heavy_session_hours', label: 'Deep Session Hours', format: 'decimal' },
    ],
    tagFields: [
      { field: 'recent_titles', label: 'Recently Played' },
      { field: 'top_games', label: 'Most Played' },
    ],
    physics: {
      particleSpeed: 'recent_2week_hours',
      colorTemp: 'heavy_session_hours',
      particleCount: 'game_count',
      pulseRate: 'total_lifetime_hours',
    },
  },
}

/** Resolve a dot-path value from an object, e.g. "audio_avg.energy" */
export function resolveField(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split('.')
  let cur: unknown = obj
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[p]
  }
  return cur
}

/** Map provider key to its API profile endpoint */
export function profileEndpoint(provider: string): string {
  const map: Record<string, string> = {
    spotify: '/api/spotify/profile',
    twitter: '/api/twitter/profile',
    strava: '/api/strava/profile',
    google: '/api/gcal/profile',
    github: '/api/github/profile',
    youtube: '/api/youtube/profile',
    reddit: '/api/reddit/profile',
    letterboxd: '/api/letterboxd/profile',
    instagram: '/api/instagram/profile',
    tiktok: '/api/tiktok/profile',
    costar: '/api/costar/profile',
  }
  return map[provider] || `/api/${provider}/profile`
}

/** Map provider key to its LLM analysis endpoint */
export function analyzeEndpoint(provider: string): string {
  const map: Record<string, string> = {
    google: '/api/gcal/analyze',
  }
  return map[provider] || `/api/${provider}/analyze`
}

/** Providers ChannelZero no longer connects to (mirrors server/app/providers.py). */
export const RETIRED_PROVIDERS: Record<string, string> = {
  strava:
    "Strava's API now needs a paid subscription and forbids any AI use of its data, " +
    'so ChannelZero no longer connects to it.',
}
