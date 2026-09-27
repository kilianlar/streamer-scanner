import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests
from requests.exceptions import RequestException


# ==========================================================
# SETTINGS
# ==========================================================

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")

KICK_CLIENT_ID = os.getenv("KICK_CLIENT_ID", "")
KICK_CLIENT_SECRET = os.getenv("KICK_CLIENT_SECRET", "")

MAX_STREAMERS_PER_PLATFORM = 10000
DATABASE_FILE = "streamers_database.csv"

# Network settings
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
MAX_RETRIES = 5
BASE_RETRY_DELAY = 3

TWITCH_PAGE_DELAY = 0.5
KICK_PAGE_DELAY = 1.0

# Twitch category: Slots
TWITCH_GAME_ID = "498566"
TWITCH_GAME_NAME = "Slots"

# Kick category: Slots & Casino
KICK_CATEGORY_ID = 28
KICK_CATEGORY_NAME = "Slots & Casino"

# Kick v2 supports up to 1000 results per page.
# A larger page reduces the number of requests and therefore the chance
# of a temporary connection reset.
KICK_PAGE_LIMIT = 1000


# ==========================================================
# TIME
# ==========================================================

RUN_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ==========================================================
# COMMON COLUMNS
# ==========================================================

STREAMER_COLUMNS = [
    "nickname",
    "normalized_nickname",
    "display_name",
    "platform",
    "category",
    "game_id",
    "language",
    "viewers",
    "title",
    "started_at",
    "mature",
    "url",
    "user_id",
    "stream_id",
    "first_seen",
    "last_seen",
]


# ==========================================================
# HELPERS
# ==========================================================

def normalize_nickname(nickname):
    if not nickname:
        return ""

    return str(nickname).strip().lower()


def empty_streamer_df():
    return pd.DataFrame(columns=STREAMER_COLUMNS)


def get_retry_delay(response, attempt):
    """
    Prefer Retry-After if the API sends it.
    Otherwise use simple exponential backoff.
    """
    if response is not None:
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except (TypeError, ValueError):
                pass

    return BASE_RETRY_DELAY * (2 ** (attempt - 1))


def request_with_retry(
    method,
    url,
    *,
    label,
    max_retries=MAX_RETRIES,
    retry_statuses=(429, 500, 502, 503, 504),
    **kwargs,
):
    """
    HTTP request with retry protection against:
    - ConnectionResetError
    - timeouts
    - temporary 429/5xx responses

    Returns the final requests.Response.
    Raises RequestException only if all network attempts fail.
    """
    kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))

    last_exception = None
    last_response = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.request(
                method,
                url,
                **kwargs,
            )

            last_response = response

            if response.status_code not in retry_statuses:
                return response

            print(
                f"{label}: тимчасовий HTTP {response.status_code} "
                f"(спроба {attempt}/{max_retries})"
            )

            if attempt == max_retries:
                return response

            delay = get_retry_delay(response, attempt)
            print(f"{label}: повтор через {delay:.0f} сек.")
            time.sleep(delay)

        except RequestException as exc:
            last_exception = exc

            print(
                f"{label}: мережева помилка "
                f"(спроба {attempt}/{max_retries}): {exc}"
            )

            if attempt == max_retries:
                break

            delay = get_retry_delay(None, attempt)
            print(f"{label}: повтор через {delay:.0f} сек.")
            time.sleep(delay)

    if last_response is not None:
        return last_response

    if last_exception is not None:
        raise last_exception

    raise RequestException(f"{label}: невідома мережева помилка")


def safe_json(response, label):
    try:
        return response.json()
    except ValueError as exc:
        preview = response.text[:500]
        raise Exception(
            f"{label}: API повернув не JSON. "
            f"HTTP {response.status_code}. "
            f"Початок відповіді: {preview}"
        ) from exc


def credentials_available(client_id, client_secret):
    return bool(client_id and client_secret)


# ==========================================================
# START LOG
# ==========================================================

print("==========================================")
print("STREAMER SCANNER")
print("==========================================")
print("Час запуску UTC:", RUN_TIME)
print()


# ==========================================================
# TWITCH TOKEN
# ==========================================================

def get_twitch_token():
    token_url = "https://id.twitch.tv/oauth2/token"

    response = request_with_retry(
        "POST",
        token_url,
        label="Twitch token",
        params={
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
    )

    if response.status_code != 200:
        print("Twitch token error:")
        print(response.text)

        raise Exception(
            f"Не вдалося отримати Twitch Access Token. "
            f"HTTP {response.status_code}"
        )

    result = safe_json(response, "Twitch token")

    access_token = result.get("access_token")

    if not access_token:
        raise Exception(
            "Twitch token response не містить access_token"
        )

    return access_token


# ==========================================================
# KICK TOKEN
# ==========================================================

def get_kick_token():
    token_url = "https://id.kick.com/oauth/token"

    response = request_with_retry(
        "POST",
        token_url,
        label="Kick token",
        data={
            "client_id": KICK_CLIENT_ID,
            "client_secret": KICK_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
    )

    if response.status_code != 200:
        print("Kick token error:")
        print(response.text)

        raise Exception(
            f"Не вдалося отримати Kick Access Token. "
            f"HTTP {response.status_code}"
        )

    result = safe_json(response, "Kick token")

    access_token = result.get("access_token")

    if not access_token:
        raise Exception(
            "Kick token response не містить access_token"
        )

    return access_token


# ==========================================================
# TWITCH
# ==========================================================

def collect_twitch():
    print()
    print("==========================================")
    print("TWITCH")
    print("==========================================")

    if not credentials_available(
        TWITCH_CLIENT_ID,
        TWITCH_CLIENT_SECRET,
    ):
        raise Exception(
            "Відсутні TWITCH_CLIENT_ID або TWITCH_CLIENT_SECRET"
        )

    access_token = get_twitch_token()

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "streamer-scanner/1.0",
    }

    print("Категорія:", TWITCH_GAME_NAME)
    print("Game ID:", TWITCH_GAME_ID)

    api_url = "https://api.twitch.tv/helix/streams"

    all_streamers = []
    cursor = None
    page = 0

    while len(all_streamers) < MAX_STREAMERS_PER_PLATFORM:
        page += 1

        params = {
            "first": 100,
            "game_id": TWITCH_GAME_ID,
        }

        if cursor:
            params["after"] = cursor

        try:
            response = request_with_retry(
                "GET",
                api_url,
                label=f"Twitch сторінка {page}",
                headers=headers,
                params=params,
            )
        except RequestException as exc:
            print(
                f"Twitch: не вдалося отримати сторінку {page} "
                f"після повторних спроб: {exc}"
            )

            if all_streamers:
                print(
                    "Twitch: зберігаємо вже отримані часткові дані."
                )
                break

            raise

        print(
            f"Twitch сторінка {page} | "
            f"HTTP {response.status_code}"
        )

        if response.status_code != 200:
            print("Twitch API error:")
            print(response.text[:1000])

            if all_streamers:
                print(
                    "Twitch: API помилка після часткового збору. "
                    "Зберігаємо вже отримані дані."
                )
                break

            raise Exception(
                f"Twitch API returned HTTP {response.status_code}"
            )

        data = safe_json(
            response,
            f"Twitch сторінка {page}",
        )

        streams = data.get("data", [])

        if not streams:
            print(
                "Більше Twitch стрімів у Slots немає."
            )
            break

        for stream in streams:
            nickname = stream.get(
                "user_login",
                "",
            )

            if not nickname:
                continue

            all_streamers.append({
                "nickname": nickname,
                "normalized_nickname":
                    normalize_nickname(nickname),
                "display_name":
                    stream.get("user_name", ""),
                "platform": "Twitch",
                "category":
                    stream.get("game_name", ""),
                "game_id":
                    stream.get("game_id", ""),
                "language":
                    stream.get("language", ""),
                "viewers":
                    stream.get("viewer_count", 0),
                "title":
                    stream.get("title", ""),
                "started_at":
                    stream.get("started_at", ""),
                "mature":
                    stream.get("is_mature", False),
                "url":
                    f"https://www.twitch.tv/{nickname}",
                "user_id":
                    stream.get("user_id", ""),
                "stream_id":
                    stream.get("id", ""),
                "first_seen": RUN_TIME,
                "last_seen": RUN_TIME,
            })

            if (
                len(all_streamers)
                >= MAX_STREAMERS_PER_PLATFORM
            ):
                break

        print(
            "Зібрано Twitch:",
            len(all_streamers),
        )

        pagination = data.get(
            "pagination",
            {},
        ) or {}

        cursor = pagination.get("cursor")

        if not cursor:
            print(
                "Досягнуто кінець Twitch списку."
            )
            break

        time.sleep(TWITCH_PAGE_DELAY)

    df = pd.DataFrame(
        all_streamers,
        columns=STREAMER_COLUMNS,
    )

    if not df.empty:
        df = df.drop_duplicates(
            subset=[
                "normalized_nickname",
            ],
            keep="first",
        ).reset_index(drop=True)

    print(
        "Twitch унікальних:",
        len(df),
    )

    return df


# ==========================================================
# KICK
# ==========================================================

def collect_kick():
    print()
    print("==========================================")
    print("KICK")
    print("==========================================")

    if not credentials_available(
        KICK_CLIENT_ID,
        KICK_CLIENT_SECRET,
    ):
        raise Exception(
            "Відсутні KICK_CLIENT_ID або KICK_CLIENT_SECRET"
        )

    access_token = get_kick_token()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "streamer-scanner/1.0",
    }

    api_url = (
        "https://api.kick.com/public/v2/livestreams"
    )

    print("Категорія:", KICK_CATEGORY_NAME)
    print("Category ID:", KICK_CATEGORY_ID)

    all_streamers = []
    cursor = None
    page = 0

    while len(all_streamers) < MAX_STREAMERS_PER_PLATFORM:
        page += 1

        # IMPORTANT:
        # Kick v2 uses `category_id`, not `categoryId`.
        # With `categoryId` the API filter can be ignored,
        # which causes the scanner to crawl unrelated streams.
        params = [
            (
                "category_id",
                str(KICK_CATEGORY_ID),
            ),
            (
                "limit",
                str(KICK_PAGE_LIMIT),
            ),
        ]

        if cursor:
            params.append(
                (
                    "cursor",
                    cursor,
                )
            )

        try:
            response = request_with_retry(
                "GET",
                api_url,
                label=f"Kick сторінка {page}",
                headers=headers,
                params=params,
            )
        except RequestException as exc:
            print(
                f"Kick: не вдалося отримати сторінку {page} "
                f"після повторних спроб: {exc}"
            )

            if all_streamers:
                print(
                    "Kick: зберігаємо вже отримані часткові дані."
                )
                break

            raise

        print(
            f"Kick сторінка {page} | "
            f"HTTP {response.status_code}"
        )

        if response.status_code != 200:
            print(response.text[:1000])

            if all_streamers:
                print(
                    "Kick: API помилка після часткового збору. "
                    "Зберігаємо вже отримані дані."
                )
                break

            raise Exception(
                f"Kick API returned HTTP "
                f"{response.status_code}"
            )

        result = safe_json(
            response,
            f"Kick сторінка {page}",
        )

        streams = result.get(
            "data",
            [],
        ) or []

        print(
            f"Kick API повернув на сторінці: "
            f"{len(streams)}"
        )

        if not streams:
            print(
                "Більше Kick стрімів у категорії немає."
            )
            break

        accepted_on_page = 0

        for stream in streams:
            channel = (
                stream.get("channel")
                or {}
            )

            user = (
                stream.get(
                    "broadcaster_user"
                )
                or {}
            )

            category = (
                stream.get("category")
                or {}
            )

            category_id = category.get(
                "id"
            )

            # Secondary safety check.
            # The server request already filters by category_id,
            # but we reject unrelated records if the API ever
            # returns them unexpectedly.
            try:
                category_id_int = int(category_id)
            except (TypeError, ValueError):
                category_id_int = None

            if (
                category_id_int is not None
                and category_id_int != KICK_CATEGORY_ID
            ):
                continue

            slug = (
                channel.get("slug")
                or ""
            )

            username = (
                user.get("username")
                or slug
                or ""
            )

            if not username:
                continue

            if not slug:
                slug = username

            category_name = (
                category.get("name")
                or KICK_CATEGORY_NAME
            )

            all_streamers.append({
                "nickname":
                    username,
                "normalized_nickname":
                    normalize_nickname(
                        username
                    ),
                "display_name":
                    username,
                "platform":
                    "Kick",
                "category":
                    category_name,
                "game_id":
                    category_id
                    if category_id is not None
                    else KICK_CATEGORY_ID,
                "language":
                    stream.get(
                        "language_code",
                        "",
                    ),
                "viewers":
                    stream.get(
                        "viewer_count",
                        0,
                    ),
                "title":
                    stream.get(
                        "title",
                        "",
                    ),
                "started_at":
                    stream.get(
                        "started_at",
                        "",
                    ),
                "mature":
                    stream.get(
                        "has_mature_content",
                        False,
                    ),
                "url":
                    f"https://kick.com/{slug}",
                "user_id":
                    user.get(
                        "id",
                        "",
                    ),
                "stream_id":
                    stream.get(
                        "id",
                        "",
                    ),
                "first_seen":
                    RUN_TIME,
                "last_seen":
                    RUN_TIME,
            })

            accepted_on_page += 1

            if (
                len(all_streamers)
                >= MAX_STREAMERS_PER_PLATFORM
            ):
                break

        print(
            f"Kick прийнято зі сторінки: "
            f"{accepted_on_page}"
        )

        print(
            "Зібрано Kick:",
            len(all_streamers),
        )

        pagination = (
            result.get(
                "pagination"
            )
            or {}
        )

        next_cursor = pagination.get(
            "next_cursor"
        )

        if not next_cursor:
            print(
                "Досягнуто кінець Kick списку."
            )
            break

        # Protection against a broken API returning
        # the same cursor forever.
        if next_cursor == cursor:
            print(
                "Kick повернув той самий cursor повторно. "
                "Зупиняємо пагінацію."
            )
            break

        cursor = next_cursor

        if (
            len(all_streamers)
            >= MAX_STREAMERS_PER_PLATFORM
        ):
            break

        time.sleep(KICK_PAGE_DELAY)

    df = pd.DataFrame(
        all_streamers,
        columns=STREAMER_COLUMNS,
    )

    if not df.empty:
        df = df.drop_duplicates(
            subset=[
                "normalized_nickname",
            ],
            keep="first",
        ).reset_index(drop=True)

    print(
        "Kick унікальних:",
        len(df),
    )

    return df


# ==========================================================
# COLLECT BOTH
# ==========================================================

platform_errors = {}

try:
    twitch_df = collect_twitch()

except Exception as exc:
    platform_errors["Twitch"] = str(exc)
    twitch_df = empty_streamer_df()

    print()
    print("==========================================")
    print("TWITCH ERROR")
    print("==========================================")
    print(exc)
    print(
        "Twitch пропущено. "
        "Переходимо до Kick."
    )


try:
    kick_df = collect_kick()

except Exception as exc:
    platform_errors["Kick"] = str(exc)
    kick_df = empty_streamer_df()

    print()
    print("==========================================")
    print("KICK ERROR")
    print("==========================================")
    print(exc)
    print(
        "Kick пропущено. "
        "Продовжуємо з доступними даними."
    )


# ==========================================================
# COMBINE
# ==========================================================

frames = []

if not twitch_df.empty:
    frames.append(twitch_df)

if not kick_df.empty:
    frames.append(kick_df)

if not frames:
    raise Exception(
        "Не знайдено жодного стрімера. "
        "Обидві платформи не повернули придатних даних."
    )

new_scan_df = pd.concat(
    frames,
    ignore_index=True,
)

# Twitch + Twitch or Kick + Kick
new_scan_df = new_scan_df.drop_duplicates(
    subset=[
        "platform",
        "normalized_nickname",
    ],
    keep="first",
).reset_index(drop=True)


print()
print("==========================================")
print("ПОТОЧНИЙ ЗБІР")
print("==========================================")

print(
    "Twitch:",
    len(twitch_df),
)

print(
    "Kick:",
    len(kick_df),
)

print(
    "Разом:",
    len(new_scan_df),
)


# ==========================================================
# LOAD EXISTING DATABASE
# ==========================================================

if os.path.exists(
    DATABASE_FILE
):
    try:
        database_df = pd.read_csv(
            DATABASE_FILE,
            dtype=str,
        )

        print()
        print(
            "Існуюча база:",
            len(database_df),
        )

    except pd.errors.EmptyDataError:
        database_df = pd.DataFrame()

        print()
        print(
            "Файл бази порожній. "
            "Створюємо базу заново."
        )

    except Exception as exc:
        raise Exception(
            f"Не вдалося прочитати "
            f"{DATABASE_FILE}: {exc}"
        ) from exc

else:
    database_df = pd.DataFrame()

    print()
    print(
        "Існуючої бази немає."
    )

    print(
        "Створюємо нову."
    )


# ==========================================================
# FIRST RUN / UPDATE DATABASE
# ==========================================================

if database_df.empty:
    database_df = new_scan_df.copy()
    new_streamers = new_scan_df.copy()

else:
    # ------------------------------------------------------
    # ENSURE COLUMNS
    # ------------------------------------------------------

    for column in new_scan_df.columns:
        if column not in database_df.columns:
            database_df[column] = ""

    for column in database_df.columns:
        if column not in new_scan_df.columns:
            new_scan_df[column] = ""

    # Backfill normalized_nickname in older databases
    # if the column was absent or contained empty values.
    if "normalized_nickname" in database_df.columns:
        missing_normalized = (
            database_df[
                "normalized_nickname"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("")
        )

        database_df.loc[
            missing_normalized,
            "normalized_nickname",
        ] = (
            database_df.loc[
                missing_normalized,
                "nickname",
            ]
            .fillna("")
            .map(
                normalize_nickname
            )
        )

    # Same column order
    new_scan_df = new_scan_df[
        database_df.columns
    ].copy()

    # ------------------------------------------------------
    # UNIQUE KEY
    # ------------------------------------------------------

    database_df["unique_key"] = (
        database_df[
            "platform"
        ]
        .fillna("")
        .astype(str)
        + "|"
        + database_df[
            "normalized_nickname"
        ]
        .fillna("")
        .astype(str)
    )

    new_scan_df["unique_key"] = (
        new_scan_df[
            "platform"
        ]
        .fillna("")
        .astype(str)
        + "|"
        + new_scan_df[
            "normalized_nickname"
        ]
        .fillna("")
        .astype(str)
    )

    database_keys = set(
        database_df[
            "unique_key"
        ]
    )

    new_streamers = new_scan_df[
        ~new_scan_df[
            "unique_key"
        ].isin(database_keys)
    ].copy()

    # ------------------------------------------------------
    # CURRENT LOOKUP
    # ------------------------------------------------------

    current_lookup = (
        new_scan_df
        .drop_duplicates(
            subset=[
                "unique_key",
            ],
            keep="first",
        )
        .set_index(
            "unique_key"
        )
    )

    # ------------------------------------------------------
    # UPDATE EXISTING
    # ------------------------------------------------------

    update_columns = [
        "display_name",
        "category",
        "game_id",
        "language",
        "viewers",
        "title",
        "started_at",
        "mature",
        "url",
        "user_id",
        "stream_id",
    ]

    for idx in database_df.index:
        key = database_df.at[
            idx,
            "unique_key",
        ]

        if key not in current_lookup.index:
            continue

        current_row = current_lookup.loc[
            key
        ]

        for column in update_columns:
            if (
                column in database_df.columns
                and column in current_lookup.columns
            ):
                database_df.at[
                    idx,
                    column,
                ] = current_row[
                    column
                ]

        database_df.at[
            idx,
            "last_seen",
        ] = RUN_TIME

    database_df = database_df.drop(
        columns=[
            "unique_key",
        ],
        errors="ignore",
    )

    # ------------------------------------------------------
    # ADD NEW
    # ------------------------------------------------------

    if not new_streamers.empty:
        new_streamers = new_streamers.drop(
            columns=[
                "unique_key",
            ],
            errors="ignore",
        )

        database_df = pd.concat(
            [
                database_df,
                new_streamers,
            ],
            ignore_index=True,
        )

    else:
        new_streamers = new_streamers.drop(
            columns=[
                "unique_key",
            ],
            errors="ignore",
        )


# ==========================================================
# FINAL CLEANUP
# ==========================================================

# Guarantee the important fields exist.
for column in STREAMER_COLUMNS:
    if column not in database_df.columns:
        database_df[column] = ""

# Backfill normalization one more time.
database_df[
    "normalized_nickname"
] = database_df.apply(
    lambda row: (
        normalize_nickname(
            row.get(
                "normalized_nickname",
                "",
            )
        )
        or normalize_nickname(
            row.get(
                "nickname",
                "",
            )
        )
    ),
    axis=1,
)

database_df = database_df.drop_duplicates(
    subset=[
        "platform",
        "normalized_nickname",
    ],
    keep="first",
)

database_df["platform"] = (
    database_df["platform"]
    .fillna("")
)

database_df["nickname"] = (
    database_df["nickname"]
    .fillna("")
)

database_df = database_df.sort_values(
    by=[
        "platform",
        "nickname",
    ],
    ascending=[
        True,
        True,
    ],
    kind="stable",
).reset_index(
    drop=True
)


# ==========================================================
# SAVE DATABASE
# ==========================================================

database_df.to_csv(
    DATABASE_FILE,
    index=False,
    encoding="utf-8-sig",
)


# ==========================================================
# RESULTS
# ==========================================================

print()
print("==========================================")
print("РЕЗУЛЬТАТ")
print("==========================================")

print(
    "Twitch у поточному зборі:",
    len(twitch_df),
)

print(
    "Kick у поточному зборі:",
    len(kick_df),
)

print(
    "Всього у базі:",
    len(database_df),
)

print(
    "НОВИХ стрімерів:",
    len(new_streamers),
)

if platform_errors:
    print()
    print("Попередження по платформах:")

    for platform, error in platform_errors.items():
        print(
            f"- {platform}: {error}"
        )

print("==========================================")


# ==========================================================
# NEW STREAMERS
# ==========================================================

if not new_streamers.empty:
    print()
    print("==========================================")
    print("НОВІ СТРІМЕРИ")
    print("==========================================")

    preview_columns = [
        "nickname",
        "platform",
        "category",
        "language",
        "viewers",
        "url",
    ]

    printable = (
        new_streamers[
            preview_columns
        ]
        .copy()
    )

    printable["_viewers_sort"] = (
        pd.to_numeric(
            printable["viewers"],
            errors="coerce",
        )
        .fillna(0)
    )

    printable = printable.sort_values(
        by="_viewers_sort",
        ascending=False,
    ).drop(
        columns=[
            "_viewers_sort",
        ]
    )

    print(
        printable.to_string(
            index=False
        )
    )

else:
    print()
    print(
        "Нових стрімерів цього разу немає."
    )


# ==========================================================
# DATABASE PREVIEW
# ==========================================================

print()
print("Перші записи бази:")

print(
    database_df.head(
        30
    ).to_string(
        index=False
    )
)

print()
print(
    "Файл бази:",
    DATABASE_FILE
)

print(
    "Сканування завершено."
)
