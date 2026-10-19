// Starter stories for /story. Stage markers follow the fractionation arc
// (see src/story/storyBeats.ts for the markup).

export interface StorySample {
  id: string
  title: string
  text: string
}

export const STORY_SAMPLES: StorySample[] = [
  {
    id: 'lighthouse',
    title: 'The Lighthouse Stair',
    text: `[induce]
Let your hands rest wherever they are. There is nowhere else you need to be.

Somewhere ahead of you, a lighthouse stands at the edge of a quiet sea. Its door is already open.

Step inside. The air is cool, and it smells of salt and old stone.

[deepen]
A stair winds down, not up. With each step, the sound of the waves grows softer.

Ten steps. Your shoulders loosen. Twenty steps. Your breath slows on its own.

At the bottom there is a small round room, lit by a single lamp, and it feels like it was made for you.

[emerge]
For a moment, climb back up toward the light. Notice the window, the sea, the far horizon.

[reinduce]
And now return to the stair, and go down twice as easily as before.

The lamp is waiting. The room is warmer now. Every sound settles into the hum of the sea.

[pause 6]

[final]
Rest here. Whatever you brought down with you can stay on the lowest step.

[wake]
In a moment, you will climb the stair one last time, carrying only what you want to keep.

One, feeling returning to your hands. Two, a fuller breath. Three, eyes open, and awake.`,
  },
  {
    id: 'plain',
    title: 'Untagged (auto arc)',
    text: `Notice the weight of your body where it is supported.

Each breath out is a little longer than the breath in.

Thoughts can drift past like clouds. You don't need to follow them.

The quiet is wider than it was a moment ago.

When you are ready, open your eyes and bring the quiet with you.`,
  },
]
