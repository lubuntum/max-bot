# School Schedule Bot (MAX)

A chat bot for the MAX messenger that shows students their class schedule.
Everything is button-driven — pick your class once, then browse the
schedule by day, without typing commands.

## How it works

1. A user opens the bot → taps their class on a button grid → it's saved
   to a local SQLite database, so they don't need to pick it again next time.
2. They tap **📅 Расписание** → pick a day → the bot returns that day's
   lessons for their class.
3. The schedule itself lives in an `.xlsx` file on Yandex.Disk with two
   sheets: **Основное** (the permanent, default schedule) and
   **Измененное** (today's overrides — substitute teachers, moved times,
   cancelled lessons). The bot merges them cell by cell: if a cell in
   Измененное is filled in, it wins; if it's empty, the value from
   Основное is used instead. The merged result is cached for a while
   (`CACHE_TTL`) so we don't re-download the file on every message.

## Project structure

```
bot.py        entry point — starts the bot and all handlers
config.py     loads settings from .env
database.py   stores which class each user picked (SQLite)
schedule.py   downloads, merges, and serves the schedule
```

---

## `bot.py`

Creates the bot (`MAX_TOKEN`) and the `Dispatcher` (`dp`), and holds all
message/button handlers.

**Keyboards** — build the button menus shown to users:
| Function | Returns |
|---|---|
| `classes_keyboard()` | grid of all class buttons (1А, 1Б, ... 11) |
| `days_keyboard()` | Сегодня / Завтра / days of the week / Неделя |
| `menu_keyboard()` | main menu: Расписание / Сменить класс / Удалить класс |

**Helpers**
| Function | Parameters | Does |
|---|---|---|
| `get_cached_schedule()` | — | calls `schedule.load_schedule()` off the event loop (it's a blocking call) |
| `build_schedule_text(day_code, user_class)` | `day_code`: `"today"`/`"tomorrow"`/`"week"`/`"ПН".."ВС"`, `user_class`: e.g. `"5А"` | formats the schedule text for one day |
| `get_user_info(user)` | a MAX user object | pulls `first_name`/`last_name`/`username` safely |

**Commands** — `cmd_start`, `cmd_myclass`, `cmd_changeclass`, `cmd_deleteclass`,
`cmd_ping`: classic `/command` handlers, kept mainly as a fallback for
anyone who types instead of tapping buttons.

**`handle_callback(event)`** — the single handler for every button tap.
Reads `event.callback.payload` and routes it:
- `class:<name>` → saves the picked class
- `day:<code>` → shows that day's schedule
- `menu:schedule` / `menu:changeclass` / `menu:deleteclass` / `menu:back` → menu navigation

**`handle_text(event)`** — fallback for typed messages: accepts a typed
class name, otherwise nudges the user back to the buttons.

---

## `config.py`

Loads configuration from `.env`:
- `MAX_TOKEN` — bot token for the MAX API
- `CACHE_TTL` — how many seconds a loaded schedule stays cached before re-downloading
- `YANDEX_SHARE_URL` — the public Yandex.Disk link to the schedule `.xlsx`
- `YANDEX_DIRECT_URL` — (if used) a direct download URL variant

---

## `database.py`

Stores each user's picked class in a local SQLite file, so it persists
between sessions.

| Function | Parameters | Does |
|---|---|---|
| `get_user_class(user_id)` | MAX user id | returns the class the user picked before, or `None` |
| `save_user(user_id, class_name, first_name, last_name, username)` | — | inserts/updates the user's saved class |
| `delete_user(user_id)` | MAX user id | removes the saved class |

---

## `schedule.py`

Downloads the schedule `.xlsx` from Yandex.Disk, reads both sheets, and
merges them into one lookup-friendly structure.

**`Lesson`** — small dataclass: `time`, `subject`.

**`Schedule`** — the merged, ready-to-query schedule.
Internally stored as `_data = {день: {класс: [Lesson, Lesson, ...]}}` —
each day maps to every class, and each class maps to its lessons for
that day, in order.

| Method | Parameters | Does |
|---|---|---|
| `get_day(day, class_name)` | `day`: e.g. `"ПН"` or `"Понедельник"`, `class_name`: e.g. `"1А"` | normalizes both, returns that class's lesson list for that day (`[]` if none) |
| `from_sheets(df_base, df_changed)` *(classmethod)* | the two sheets as DataFrames | parses both, merges cell-by-cell (Измененное wins where filled, Основное fills the gaps), and returns a ready `Schedule` |

**Module-level functions**
| Function | Parameters | Does |
|---|---|---|
| `load_schedule(public_url, ttl)` | Yandex.Disk share link, cache lifetime in seconds | downloads + parses + merges the sheets into a `Schedule`, reusing the cached one until `ttl` expires |
| `get_schedule_for_day(schedule, day_ru, class_name)` | a `Schedule` object, day, class | returns the formatted, ready-to-send schedule text |
| `get_cache_status()` | — | `(is_cached, age_in_seconds)` — used by `/ping` |
| `get_real_direct_url(public_url)` | Yandex.Disk share link | converts it into a real downloadable file URL |