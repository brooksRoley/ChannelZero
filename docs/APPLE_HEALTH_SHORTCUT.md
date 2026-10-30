# Movement from Apple Health

Apple Health has no web API. A Shortcut on your iPhone reads your workouts
and sends them to ChannelZero once a day. It sends each workout's **start,
end and type**. It never sends heart rate, distance, routes or location. Movement is never shown to
the Oracle, the portrait or any AI.

If you record with the Strava app, turn on **Strava → Settings → Applications,
Services and Devices → Health** so your activities land in Apple Health. The
Shortcut reads Health, not Strava.

## 1. Make a token

ChannelZero → Calibrate → **Movement** → **Make a token**. Copy it: it's shown
once. Making a new one replaces the old one, and **Delete my movement data**
removes the workouts and the token.

## 2. Build the Shortcut

Shortcuts app → **Automation** → **+** → **Time of Day**: 9:00 PM, Daily,
**Run Immediately**. Then add these actions (names can differ slightly by iOS
version):

1. **Find Health Samples**: Type **Workouts**, filter **Start Date is in the
   last 2 days**. Two days, so a missed evening is caught the next night.
   Sending a workout twice is safe: it's stored once.
2. **Repeat with Each** item in Health Samples:
   - **Format Date**: Repeat Item → *Start Date*, Date Format **ISO 8601**,
     include time. (ISO 8601 carries your UTC offset, which sets the day.)
   - **Format Date**: Repeat Item → *End Date*, same settings.
   - **Dictionary** with three Text keys:
     `start` = first Formatted Date, `end` = second Formatted Date,
     `type` = Repeat Item → *Workout Type* (or *Type*).
3. **End Repeat**.
4. **Get Contents of URL**
   - URL: the endpoint shown on the card (`…/api/movement/workouts`)
   - Method **POST**
   - Headers: `Authorization` = `Bearer <your token>`
   - Request Body **JSON**: one key `workouts`, type **Array**, value
     **Repeat Results**.

The first run asks permission to read Workouts from Health. Allow it.

## 3. Check it

Run the automation once by hand. The card should say "Last received …" and
list today's minutes. The server's reply is `{"saved": N, "refused": [...]}`.
A workout is refused when it ends before it starts, lasts more than 24 hours,
or starts in the future.

## What's kept

- Per workout: start, end, local day, type. Keyed on start time.
- Workouts older than 400 days are dropped.
- The token is stored only as a SHA-256 hash, and it can only post workouts.
  It can't read anything.
