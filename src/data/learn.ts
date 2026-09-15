export type LearnAnimation = 'enfractionation' | 'binaural-entrainment' | 'protocol'

export interface LearnTopic {
  slug: string
  title: string
  phase: 1 | 2 | 3
  phaseName: string
  shortDescription: string
  sections: {
    definition: string
    mechanism: string
    inPractice: string
  }
  linkedSession?: { label: string; to: string }
  animation?: LearnAnimation
}

export const LEARN_TOPICS: LearnTopic[] = [
  // ── Phase 1 — Foundations ─────────────────────────────────────
  {
    slug: 'enfractionation',
    title: 'Enfractionation',
    phase: 1,
    phaseName: 'Foundations',
    shortDescription: 'The act of making someone more receptive — the central thread that ties every tool on this site together.',
    sections: {
      definition:
        'Enfractionation is the slow softening of the ordinary critical filter — the running internal commentator that questions, ranks, and rejects most of what reaches it. When that filter loosens, suggestions, images, and ideas have an easier path inward. The word draws on "fractionation," a long-standing hypnosis technique in which a subject is taken into and out of trance repeatedly so each return goes a little deeper.\n\nIt is not a single technique. It is a goal that can be approached through breath, sound, language, narrative, and visual repetition. The rest of this curriculum is about the specific paths.',
      mechanism:
        'Receptivity rises when attention narrows and prediction relaxes. The brain spends most of its day generating expectations and pruning incoming signal against them. When that prediction machinery is gently overloaded — by rhythm it cannot easily anticipate, by language that bypasses literal parsing, by visual fields too smooth to fixate on — the pruning loosens. Internal experience starts to feel less filtered.\n\nClassical hypnosis researchers describe this as a shift along a "suggestibility" axis. Modern accounts describe it in terms of altered prediction error and reduced top-down control from prefrontal regions. The vocabulary differs; the shape is the same. The subject becomes more willing to take a suggestion at face value rather than meeting it with reflexive doubt.\n\nEnfractionation is best understood as a direction, not a destination. There is no single deep state that is "the" trance — there is more or less of a willingness to receive.',
      inPractice:
        'Every tool on ChannelZero is a different on-ramp to the same gradient. The Reader paces text faster than the inner critic can interrupt. The Trance engine layers binaural and isochronic frequencies that nudge brainwave activity toward calmer bands. The visual sessions — Spiral, ZeroMind, Liquid Glass — give the eyes a target so steady it stops searching. Used together, they compound. Used alone, each one is a single dial.\n\nThe homepage poll exists for this reason: it suggests which on-ramp will likely fit your current state.',
    },
    linkedSession: { label: 'Start from Home', to: '/' },
    animation: 'enfractionation',
  },

  {
    slug: 'hypnotic-induction',
    title: 'Hypnotic Induction',
    phase: 1,
    phaseName: 'Foundations',
    shortDescription: 'The opening move — how a session shifts attention and lowers the threshold for everything that follows.',
    sections: {
      definition:
        'A hypnotic induction is the opening of a session: the deliberate steps that move a person from ordinary, outward-facing attention into a narrower, more inward, more accepting state. Inductions are usually short — anywhere from thirty seconds to several minutes — and are the precondition for the suggestions that follow. Without one, suggestions tend to bounce off the critical filter described in Enfractionation.\n\nInductions take many forms: progressive relaxation, eye fixation, counting down, guided breath, rapid confusion patterns, or a steady auditory rhythm. They share a single goal: to gather attention and quiet the part of the mind that argues.',
      mechanism:
        'Most inductions exploit one of three pathways. The first is fatigue: ask the eyes, the breath, or the body to do something monotonous until the brain stops attending to it actively. The second is fixation: give attention a single object — a sound, a phrase, a moving point — that is steady enough to hold but not interesting enough to analyze. The third is confusion: present a pattern just complex enough that the conscious mind disengages rather than tracking it.\n\nAll three reduce the resources available for active critical evaluation. Once that evaluation eases, suggestions made in plain language tend to be accepted as descriptions of what is true now, rather than proposals to be debated.\n\nThe depth of an induction matters less than its consistency. A reliable, repeatable induction trains the system: returning to the same opening sequence shortens the path each time, the way a well-worn trail is easier to walk.',
      inPractice:
        'The Reader is built as an induction in itself. Word-by-word presentation removes the saccadic eye movement of normal reading; the rhythm becomes its own fixation point. Open a calming text and let the pacing do the work — by the time the content arrives, the opening has already happened.\n\nThe Trance engine offers another path: layer the Drift and Alpha Flow tones at the start of a session and let them run for two or three minutes before adding anything else.',
    },
    linkedSession: { label: 'Open the Reader', to: '/reader' },
  },

  {
    slug: 'suggestion-induction',
    title: 'Suggestion Induction',
    phase: 1,
    phaseName: 'Foundations',
    shortDescription: 'What you do once attention has softened — the language that lands when the filter is down.',
    sections: {
      definition:
        'Suggestion induction is the practice of placing a desired idea, image, or response into a state that is already receptive. It is the work that follows hypnotic induction. The induction creates the opening; the suggestion is what passes through it. A suggestion can be direct ("your shoulders are heavy") or indirect ("you may notice that your shoulders feel heavier than they did a moment ago"). It can describe a sensation, an outcome, an attitude, or a future action.\n\nNot every suggestion lands. The closer it sits to what the subject actually wants — and the more it matches their internal vocabulary — the more reliably it does.',
      mechanism:
        'A suggestion in trance behaves differently from one in ordinary conversation. The same sentence that would meet skepticism at a dinner table can be received as straightforward fact when the critical filter is at rest. Researchers who study suggestibility scales have shown this empirically: subjects who would never normally report their hand floating describe exactly that when the suggestion is given inside an induction.\n\nThe mechanism is partly about belief and partly about attention. When prediction machinery is quieted, the brain has less competing signal to weigh against the suggestion. The phrase becomes a kind of lived hypothesis — tested by being inhabited rather than by being argued with.\n\nIndirect suggestions ("you may notice...") tend to outperform direct commands ("you will...") because they invite participation. They give the subject room to construct the experience themselves, which makes the resulting state feel self-generated rather than imposed. Self-generated experiences are far harder to dismiss afterward.',
      inPractice:
        'The Reader is the most direct suggestion tool here: load a script of carefully worded suggestions and let the word-by-word pace deliver them with the rhythm of an induction already built in. Pair it with an active trance layer for compounding effect.\n\nReader scripts work best when written in present tense, in the second person, and addressed to sensations or attitudes rather than abstractions.',
    },
    linkedSession: { label: 'Open the Reader', to: '/reader' },
  },

  {
    slug: 'trance-states',
    title: 'Trance States',
    phase: 1,
    phaseName: 'Foundations',
    shortDescription: 'A range, not a destination — the family of altered states where suggestion is easier to accept.',
    sections: {
      definition:
        'Trance is not a single state. It is a family of related shifts in awareness, all marked by some combination of narrowed attention, reduced self-monitoring, time distortion, and a willingness to let inner experience proceed without constant editing. Light trance can feel like the absorption of a good book or a long drive on a familiar road. Deeper states can include vivid imagery, body distortion, and complete loss of the sense of having chosen what comes next.\n\nDespite folk associations with sleep, trance is not unconsciousness. Subjects in deep trance can speak, respond, and remember. The signature is shifted volition, not absence.',
      mechanism:
        'EEG studies of trance and meditation consistently show changes in the relative power of different brainwave bands — typically more alpha (8–12 Hz) in light trance, more theta (4–8 Hz) in deeper states, and altered coupling between frontal and parietal regions. These are correlations, not explanations, but they show that trance is not imagined: the underlying electrical activity changes.\n\nFunctionally, what changes is the balance between top-down and bottom-up processing. In ordinary waking, top-down predictions dominate: the brain tells the eyes what to expect to see, the body what posture to maintain, the self what story to keep telling. In trance, the top-down voice softens. Sensations and images bubble up with less editing. Suggestions inserted at this point get treated as bottom-up data rather than as proposals to evaluate.\n\nIndividual variability is large. Roughly ten to fifteen percent of people enter deep trance very easily; another ten to fifteen percent have a hard time entering at all; most are somewhere in the middle and respond to the right combination of conditions.',
      inPractice:
        'ZeroMind is the most direct introduction here: a visual that gives the eye a steady target until the rest of the system catches up. Pair it with the Trance engine running a single layer — Alpha Flow for relaxed openness, Deep Theta for the deeper hypnagogic edge.\n\nDo not chase depth. The state arrives when the conditions are right; effort to reach it tends to push it away.',
    },
    linkedSession: { label: 'Enter ZeroMind', to: '/zeromind' },
  },

  // ── Phase 2 — Sound Mechanics ─────────────────────────────────
  {
    slug: 'binaural-entrainment',
    title: 'Binaural Entrainment',
    phase: 2,
    phaseName: 'Sound Mechanics',
    shortDescription: 'Two close tones, one in each ear — the brain hears a third pulse that does not exist outside the head.',
    sections: {
      definition:
        'A binaural beat is an auditory illusion. Play a 200 Hz sine wave in the left ear and a 210 Hz sine wave in the right ear, and the listener perceives a third tone — a 10 Hz pulse — that is not present in either ear individually. The pulse is generated inside the brainstem, where signal from the two ears first combines. Headphones are required: the trick depends on each ear receiving its own clean tone.\n\nThe perceived beat frequency equals the difference between the two carrier tones. By choosing carriers a few Hz apart, one can produce a perceived rhythm in any of the standard EEG bands.',
      mechanism:
        'Binaural beats are generated in the superior olivary complex, an early auditory structure that compares the timing of signal from both ears. The resulting low-frequency signal is propagated upward into auditory cortex and beyond. The "entrainment" claim is that this rhythmic input encourages neural populations elsewhere in the brain to oscillate at or near the same frequency — pulling alpha activity toward 10 Hz, theta toward 6 Hz, and so on.\n\nThe evidence is genuinely mixed. Some studies find measurable EEG and subjective effects; others find effects no larger than placebo. The strongest case is for relaxation and mood shifts during alpha and theta sessions; the weakest is for cognitive enhancement claims. Carrier frequency, session length, and individual neurology all seem to matter.\n\nA reasonable read of the literature is this: binaural beats are unlikely to do nothing, unlikely to do as much as their boldest marketing suggests, and most useful as a steady-state auditory anchor that supports other practices like breathwork or meditation.',
      inPractice:
        'WebAudio renders binaural beats with a visual companion, useful for first-time exploration. The Trance engine offers three binaural layers — Alpha Flow at 10 Hz for relaxed focus, Deep Theta at 6 Hz for meditation depth, and Earth Tone at 7.83 Hz tracking the Schumann resonance.\n\nUse headphones. Without them, the perceived beat does not form, and you are listening to two close tones with no entrainment effect at all.',
    },
    linkedSession: { label: 'Launch WebAudio', to: '/webaudio' },
    animation: 'binaural-entrainment',
  },

  {
    slug: 'isochronic-tones',
    title: 'Isochronic Tones',
    phase: 2,
    phaseName: 'Sound Mechanics',
    shortDescription: 'A single tone switched on and off at a precise rate — entrainment without headphones.',
    sections: {
      definition:
        'An isochronic tone is a single audio frequency turned rapidly on and off at evenly spaced intervals. Unlike binaural beats, no perceptual trick is involved: the pulse is physically present in the audio signal. A 432 Hz tone modulated at 2.4 Hz produces 2.4 audible pulses per second, regardless of whether you are wearing headphones or listening through a speaker.\n\nBecause the rhythm is in the signal itself, isochronic tones tend to feel more obvious — and to some listeners, more aggressive — than binaural beats. They are often used for shorter sessions or as a single layer beneath quieter content.',
      mechanism:
        'The brain readily synchronizes neural activity with rhythmic sensory input. This is sometimes called the frequency-following response: when an audio pulse arrives at, say, 6 Hz, populations of neurons in auditory cortex tend to fire in that rhythm, and that pattern can spread to nearby regions. Because isochronic tones present the rhythm directly rather than constructing it perceptually, the entrainment signal is stronger and the effect tends to appear faster.\n\nThe trade-off is that isochronic tones are harder to ignore. A binaural beat dissolves into the background; an isochronic pulse keeps announcing itself. For some users this is the point — a steady metronome to anchor attention. For others it becomes intrusive after a few minutes.\n\nSlower modulation rates (delta and low theta, 0.5–6 Hz) tend to support drowsiness and descent. Faster rates (alpha and beta, 8–20 Hz) tend to support alertness and focus. Mid-range modulation (6–10 Hz) sits in the ambiguous zone where the response varies most by individual.',
      inPractice:
        'The Audio mixer is a good place to layer an isochronic tone underneath ambient music, where it acts as a pulse the listener stops actively noticing. The Trance engine includes the Nerve Pulse layer — a 432 Hz carrier modulated at 2.4 Hz — and a Pulse Sync layer that fires a visual flash on every audio pulse for reinforced audiovisual entrainment.',
    },
    linkedSession: { label: 'Open Audio', to: '/audio' },
  },

  {
    slug: 'targeting-brainwave-states',
    title: 'Targeting Brainwave States',
    phase: 2,
    phaseName: 'Sound Mechanics',
    shortDescription: 'Which method, which frequency, which state — a practical guide to picking the right tool for delta, theta, alpha, or beta.',
    sections: {
      definition:
        'The previous pages introduced binaural beats and isochronic tones as separate techniques. This page is the bridge: how to choose between them, and how to choose a frequency that targets a specific brainwave state. The five EEG bands most commonly referenced are delta (0.5–4 Hz, deep sleep and unconscious processing), theta (4–8 Hz, drowsy reverie and meditation), alpha (8–12 Hz, relaxed wakefulness), beta (13–30 Hz, active thinking), and gamma (30 Hz and above, sustained focus and binding). Entrainment work usually targets delta, theta, or alpha; sometimes low beta.',
      mechanism:
        'The choice of method matters as much as the choice of frequency. Binaural beats are the gentlest option: the rhythm only exists perceptually, requires headphones, and tends to slip into the background. Isochronic tones are louder and more obvious: the rhythm is in the audio itself and works through speakers, but some listeners find them intrusive over long sessions. Monaural beats — two tones combined into one channel before reaching the ears — sit between the two. Photic stimulation (rhythmic light) bypasses audio entirely and is often the strongest entrainment signal, but is uncomfortable for many people and contraindicated for anyone with a history of seizures.\n\nFrequency choice should follow the target state, not the other way around. Delta work (1–3 Hz) is for sleep onset and deep release; sessions are usually short because the brain genuinely tries to sleep. Theta (5–7 Hz) is the workhorse of meditation and hypnotic depth — long enough to settle into, short enough to remain conscious for. Alpha (8–10 Hz) is the right band for relaxed focus, creative work, or as a settling phase before descending into theta. Low beta (13–18 Hz) is occasionally used for alertness and cognitive tasks, though plain caffeine generally does the same job with fewer caveats.\n\nA reasonable rule: gentler method for longer sessions, stronger method for short bursts.',
      inPractice:
        'The Trance engine in the navbar holds three binaural beat layers (Alpha Flow at 10 Hz, Deep Theta at 6 Hz, Earth Tone at 7.83 Hz) and two isochronic layers (Nerve Pulse at 2.4 Hz, Pulse Sync at 2.4 Hz with audiovisual lock). Pick by intention rather than by curiosity: if you want relaxed focus while reading, start with Alpha Flow alone. If you want depth for meditation, layer Deep Theta over Drift. If you want the strongest possible entrainment in a short window, use Pulse Sync.\n\nDo not stack everything. Each added layer dilutes the others.',
    },
    linkedSession: { label: 'Open Trance', to: '/trance' },
  },

  {
    slug: 'binaural-beats-protocol',
    title: 'Binaural Beats Protocol',
    phase: 2,
    phaseName: 'Sound Mechanics',
    shortDescription: 'How to actually use binaural beats — frequencies, durations, and the conditions that matter.',
    sections: {
      definition:
        'A protocol is the structure around the audio: which beat frequency to use, how long to play it, what to do before and after, and which conditions reliably produce a result. Binaural beats without a protocol tend to produce mild relaxation at best. A simple protocol turns the same audio into a repeatable practice.\n\nThis page is not a medical recommendation. It is a description of conventions used in practice, drawn from common usage and from researcher-published session designs.',
      mechanism:
        'Most working protocols share five elements. First, a carrier frequency in the comfortable midrange — between roughly 100 and 500 Hz. Tones below that range are felt more than heard; tones above feel sharp. Second, a beat frequency chosen for the target state: delta (0.5–4 Hz) for sleep onset, theta (4–8 Hz) for meditation and imagery, alpha (8–12 Hz) for relaxed focus, low beta (13–20 Hz) for alertness.\n\nThird, a session length long enough for entrainment to take hold but short enough to avoid fatigue — typically twenty to thirty minutes for relaxation work, ten to fifteen for focus work. Fourth, headphones with reasonably matched left and right channels; cheap earbuds with imbalanced output produce weak or asymmetric beats. Fifth, an environment that supports the intended state — a dim quiet room for theta work, a clear desk for alpha focus.\n\nA common pattern is a ramped session: five minutes at alpha to settle, ten to fifteen at theta to deepen, then a slow climb back to alpha before ending. Cold endings — cutting from theta straight to silence — often leave listeners disoriented for several minutes.',
      inPractice:
        'Audio is the right place to assemble a personal protocol: layer a binaural track with ambient music at the volume that lets both sit comfortably. The Trance engine handles the ramp automatically when you start a session — it sequences phases (settle, descent, deepen, coherence, joy, return) rather than holding a single frequency.\n\nIf you are new, start with twenty minutes at an alpha or low-theta beat and observe what changes. Adjust from there.',
    },
    linkedSession: { label: 'Open Audio', to: '/audio' },
    animation: 'protocol',
  },

  {
    slug: 'brainwave-entrainment-techniques',
    title: 'Brainwave Entrainment Techniques',
    phase: 2,
    phaseName: 'Sound Mechanics',
    shortDescription: 'The full toolkit — auditory, visual, and combined methods for nudging brainwave activity.',
    sections: {
      definition:
        'Brainwave entrainment is the broader category of which binaural beats and isochronic tones are subsets. It refers to any technique that uses rhythmic sensory input — sound, light, vibration, or some combination — to encourage the brain to produce activity at or near a target frequency. The shared assumption is that neural populations are easier to coax than to command, and that steady rhythm at the right tempo will, over minutes, gather some portion of cortical activity into its rhythm.',
      mechanism:
        'The phenomenon underlying every entrainment technique is the frequency-following response: when sensory input arrives in a steady rhythm, neurons in the corresponding cortical area tend to fire in that rhythm. This effect is well established for short timescales — milliseconds to seconds — in auditory and visual cortex. Whether and how it propagates to broader brain states is more contested.\n\nThe main techniques in current use are binaural beats (auditory illusion, headphones required), isochronic tones (audible pulses, no headphones needed), monaural beats (two tones combined before reaching the ears), photic stimulation (rhythmic flashing light, sometimes via dedicated goggles), audiovisual entrainment (synchronized sound and light), and bone-conducted vibration. Each has its own balance of strength and tolerability.\n\nCombined methods generally outperform single-channel methods. A 2.4 Hz isochronic pulse combined with a synchronized 2.4 Hz visual flash produces a stronger and faster response than either alone. The brain treats the two channels as confirming evidence that something rhythmic is actually happening, which makes the entrainment harder to ignore.',
      inPractice:
        'The Trance engine is the umbrella tool here — it combines binaural beats, isochronic tones, audiovisual sync, pink-noise sweeps, and the Schumann resonance into seven layers you can stack and unstack live. The depth meter shows how many layers are currently active.\n\nStart with one layer and add a second only when the first feels familiar. Stacking everything at once tends to produce noise rather than depth.',
    },
    linkedSession: { label: 'Open Trance', to: '/trance' },
  },

  // ── Phase 3 — Application ─────────────────────────────────────
  {
    slug: 'trance-induction',
    title: 'Trance Induction',
    phase: 3,
    phaseName: 'Application',
    shortDescription: 'A specific technique for entering trance — the choreography of frequency, breath, and attention.',
    sections: {
      definition:
        'Trance induction is the applied recipe: a particular sequence of audio frequencies, breathing pattern, posture, and attentional cues used to reliably enter a trance state. Hypnotic induction is the broader category; trance induction usually refers to the modern, sound-driven variants that combine binaural or isochronic content with a structured opening.\n\nA good induction is repeatable. Done several times in similar conditions, it shortens — what took eight minutes the first session takes four by the fifth. The body learns the path.',
      mechanism:
        'Most modern trance inductions follow a roughly four-stage arc. Settling: two to three minutes of slow breathing with a single audio anchor — typically an alpha-band binaural beat or a low-volume drone — to lower physiological arousal. Descent: introduction of a slower frequency (theta or low theta) along with a visual or imagined anchor, lasting four to six minutes. Deepening: a confusion or fixation element that overloads active analysis — a spiral, a swept noise, a counted-down sequence. Coherence: the destination state, where the system is settled enough to receive whatever the session is for.\n\nEach stage is structurally similar to a hypnotic induction in classical terms; the audio simply does part of the work that a live hypnotist would otherwise do with voice. The advantage is repeatability. The disadvantage is that the audio cannot adapt to the listener in the moment — it cannot slow down if the listener is fighting the descent.\n\nThis is why posture, breath, and environment matter. When the audio is fixed, the rest of the conditions have to absorb the variation.',
      inPractice:
        'The Trance engine implements this arc explicitly. Press Journey and the engine moves through phases — settle, descent, deepen, coherence, joy, return — each phase activating different layers in sequence. The phase pill in the navbar shows where the session currently is. Wind Down ends a session by returning rather than cutting.\n\nAllow at least twenty minutes for a full journey. Trying to compress it tends to leave the descent incomplete.',
    },
    linkedSession: { label: 'Open Trance', to: '/trance' },
  },

  {
    slug: 'nlp',
    title: 'Neuro-Linguistic Programming (NLP)',
    phase: 3,
    phaseName: 'Application',
    shortDescription: 'A model linking language, thought, and behavior — useful frames, contested science, worth knowing about.',
    sections: {
      definition:
        'Neuro-Linguistic Programming is a set of techniques and models developed in the 1970s by Richard Bandler and John Grinder, originally by observing successful therapists and trying to extract reproducible patterns from their work. The premise is that thought, language, and behavior are tightly coupled — that changing the language someone uses to describe an experience can change the experience itself, and that observed micro-behaviors (eye movement, breathing, word choice) reveal underlying mental processes.\n\nNLP is widely used in coaching, sales, and self-development contexts. Its scientific status is contested.',
      mechanism:
        'NLP is best understood as a collection of practical techniques rather than a unified theory. Among the most enduring are reframing (deliberately substituting one interpretation of an event for another to change its emotional charge), anchoring (associating a deliberate stimulus — a touch, a word — with a desired internal state so the stimulus can later evoke the state), pacing and leading (matching a person\'s rhythm and language before guiding them somewhere new), and the Milton model (deliberately vague language patterns drawn from Milton Erickson, designed to invite the listener to fill in meaning from their own experience).\n\nThe scientific picture is honest to acknowledge. Specific NLP claims — for example, that eye-movement direction reliably indicates which sense someone is recalling from — have not held up in controlled research. The broader set of techniques, especially reframing and Milton-model language, has a sturdier track record because it overlaps with elements of cognitive therapy and Ericksonian hypnosis that are independently supported.\n\nUseful posture: treat NLP as a vocabulary for noticing things, not as a verified science of mind.',
      inPractice:
        'The most directly applicable piece of NLP for this site is the Milton model — vague, permissive, present-tense language that works well in Reader scripts. Phrasings like "you may begin to notice" and "as you continue, you might find" invite the listener to construct the experience rather than evaluate the claim.\n\nWrite Reader scripts in this register and observe how differently they land compared to direct commands.',
    },
    linkedSession: { label: 'Open the Reader', to: '/reader' },
  },

  {
    slug: 'your-sonic-psyche',
    title: 'Your Sonic Psyche',
    phase: 3,
    phaseName: 'Application',
    shortDescription: 'What your listening history reveals about your emotional life — and why the pattern matters more than the playlist.',
    sections: {
      definition:
        'Most people treat music as taste — a preference, a mood-setter, background texture. The psychoanalytic lens turns that assumption over. Listening history is behavioral data: what you reached for at 2 a.m., which genres you return to under stress, how your energy tracks across the week. The aggregate is not a playlist. It is a record of emotional states and the strategies you use to modulate them.\n\nSonic psyche is the term ChannelZero uses for this reading — the psychological profile implicit in your listening, surfaced as a narrative rather than a chart.',
      mechanism:
        'The signal is in the texture, not the genre label. A consistent preference for minor keys in high-tempo music suggests something different from minor keys at low tempo. Listening volume — songs played at all, songs played to completion, songs skipped after twenty seconds — is as informative as the tracks themselves. When do you reach for familiar songs versus new ones? Do your listening spikes correlate with your calendar? With the time of day?\n\nSpotify stores this data. ChannelZero reads it, runs it through an LLM trained to produce psychoanalytic prose rather than algorithmic recommendations, and returns a portrait of the emotional self implicit in the pattern. The goal is not to categorize you. It is to hold up a mirror the algorithm never offered.',
      inPractice:
        'Connect Spotify on the Calibrate page and then open your connector reading at /calibrate/spotify. The reading takes two to three minutes to generate. It covers your dominant sonic mood, what your genre landscape suggests about your coping strategies, and which aspect of your listening points to something worth examining.\n\nThe reading changes as your listening changes. Run it every few weeks to track the arc.',
    },
    linkedSession: { label: 'Connect Spotify', to: '/calibrate' },
  },

  {
    slug: 'the-builders-mind',
    title: "The Builder's Mind",
    phase: 3,
    phaseName: 'Application',
    shortDescription: "What your GitHub history reveals about how you think, what you care about, and why you build what you build.",
    sections: {
      definition:
        'A repository is not neutral. Every commit is a decision about what is worth making. Every abandoned branch is a desire that ran out of energy. The ratio of side projects to maintained work, the hours you push code, the languages you gravitate toward, the density of your commit messages — each of these is behavioral data about the kind of mind you are, and the kind of maker.\n\nChannelZero reads your GitHub history as a psychological document rather than a portfolio. The question it asks is not what you built, but what your building reveals.',
      mechanism:
        'The signal that matters most is the gap between intent and follow-through. A developer with forty repositories and three stars is making a different psychological statement than one with four repositories and two hundred commits each. One pattern suggests restless curiosity; the other suggests a commitment orientation. Neither is better. Both are legible.\n\nLanguage choice is another layer. Systems-level languages suggest a preference for precision and control. Dynamic scripting often tracks with rapid experimentation. The mix tells you something about the tension between the developer\'s ideal of what code should be and the reality they build toward.\n\nTimestamps are the most underread signal. When do you code? Sustained late-night commits across months suggest something different from sporadic bursts. The rhythm is the information.',
      inPractice:
        'Connect GitHub on the Calibrate page. Your connector reading at /calibrate/github analyzes your public repository history, commit cadence, language distribution, and project completion rate. The narrative that comes back is a psychological portrait of you as a maker — your commitment style, your creative risk tolerance, and what your repository graveyard says about your relationship to completion.\n\nFor anyone considering a career move or assessing their own engineering identity, this reading tends to surface things that months of journaling would not.',
    },
    linkedSession: { label: 'Connect GitHub', to: '/calibrate' },
  },

  {
    slug: 'mirror-mode',
    title: 'Mirror Mode',
    phase: 3,
    phaseName: 'Application',
    shortDescription: 'How ChannelZero uses your own data as a psychoanalytic mirror — and what makes this different from an algorithm.',
    sections: {
      definition:
        'Most platforms that hold your data use it to build a model of what to show you next. The economic logic is engagement: keep you scrolling, keep you consuming, keep you producing signal that improves the model. ChannelZero runs the opposite direction. It takes the same data — your listening history, your commit log, your calendar, your viewing habits — and uses it to show you something about yourself, not back to you as content, but back to you as analysis.\n\nMirror Mode is the name for this orientation. The data is yours. The reading is for you. Nothing is trained on your responses. Nothing is optimized toward return visits. The value is in the clarity, not the retention.',
      mechanism:
        'The psychoanalytic frame that ChannelZero uses is interpretive, not diagnostic. It does not measure personality against a validated instrument. It reads behavioral patterns — what you do, when, how often, with what energy — and generates a narrative interpretation of what those patterns suggest about your emotional life, your coping strategies, your priorities, and your blind spots.\n\nThe approach borrows from behavioral psychoanalysis: the idea that unconscious material shows up in behavior before it shows up in language. What you reach for when stressed, what you avoid, what you do consistently versus what you only intend — these are the data. The LLM narrative is the reading.\n\nConnecting more data sources deepens the portrait. Spotify and GitHub together suggest something neither alone could surface. Add calendar or Reddit and the resolution increases again. The Portrait page synthesizes all connected sources into a single integrated reading.',
      inPractice:
        'Start by connecting one source — whichever feels most legible to you right now. Read the connector analysis at /calibrate/:provider. If the reading produces recognition, connect a second source and check the Portrait page for the integrated view.\n\nThe goal is not to collect connections. It is to find the reading that is most true — and most useful.',
    },
    linkedSession: { label: 'Start connecting', to: '/calibrate' },
  },
]
