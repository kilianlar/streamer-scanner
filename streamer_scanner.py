import requests
import pandas as pd
import time
import os
from datetime import datetime, timezone


# ==========================================================
# SETTINGS
# ==========================================================

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")

KICK_CLIENT_ID = os.getenv("KICK_CLIENT_ID", "")
KICK_CLIENT_SECRET = os.getenv("KICK_CLIENT_SECRET", "")

MAX_STREAMERS_PER_PLATFORM = 10000

DATABASE_FILE = "streamers_database.csv"


# ==========================================================
# CHECK CREDENTIALS
# ==========================================================

required_credentials = {
    "TWITCH_CLIENT_ID": TWITCH_CLIENT_ID,
    "TWITCH_CLIENT_SECRET": TWITCH_CLIENT_SECRET,
    "KICK_CLIENT_ID": KICK_CLIENT_ID,
    "KICK_CLIENT_SECRET": KICK_CLIENT_SECRET
}

missing_credentials = [
    name
    for name, value in required_credentials.items()
    if not value
]

if missing_credentials:
    raise Exception(
        "Відсутні API credentials: "
        + ", ".join(missing_credentials)
    )


# ==========================================================
# TIME
# ==========================================================

RUN_TIME = datetime.now(timezone.utc).strftime(
    "%Y-%m-%d %H:%M:%S"
)

print("==========================================")
print("STREAMER SCANNER")
print("==========================================")
print("Час запуску UTC:", RUN_TIME)
print()


# ==========================================================
# NORMALIZE NICKNAME
# ==========================================================

def normalize_nickname(nickname):

    if not nickname:
        return ""

    return str(nickname).strip().lower()


# ==========================================================
# TWITCH TOKEN
# ==========================================================

def get_twitch_token():

    token_url = "https://id.twitch.tv/oauth2/token"

    response = requests.post(
        token_url,
        params={
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials"
        },
        timeout=30
    )

    if response.status_code != 200:

        print("Twitch token error:")
        print(response.text)

        raise Exception(
            "Не вдалося отримати Twitch Access Token"
        )

    return response.json()["access_token"]


# ==========================================================
# KICK TOKEN
# ==========================================================

def get_kick_token():

    token_url = "https://id.kick.com/oauth/token"

    response = requests.post(
        token_url,
        data={
            "client_id": KICK_CLIENT_ID,
            "client_secret": KICK_CLIENT_SECRET,
            "grant_type": "client_credentials"
        },
        timeout=30
    )

    if response.status_code != 200:

        print("Kick token error:")
        print(response.text)

        raise Exception(
            "Не вдалося отримати Kick Access Token"
        )

    return response.json()["access_token"]


# ==========================================================
# TWITCH
# ==========================================================

def collect_twitch():

    print()
    print("==========================================")
    print("TWITCH")
    print("==========================================")

    access_token = get_twitch_token()

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {access_token}"
    }

    # Twitch category: Slots
    GAME_ID = "498566"
    GAME_NAME = "Slots"

    print("Категорія:", GAME_NAME)
    print("Game ID:", GAME_ID)

    api_url = "https://api.twitch.tv/helix/streams"

    all_streamers = []
    cursor = None

    while len(all_streamers) < MAX_STREAMERS_PER_PLATFORM:

        params = {
            "first": 100,
            "game_id": GAME_ID
        }

        if cursor:
            params["after"] = cursor

        response = requests.get(
            api_url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:

            print("Twitch API error:")
            print(response.text)

            raise Exception(
                f"Twitch API returned HTTP {response.status_code}"
            )

        data = response.json()

        streams = data.get("data", [])

        if not streams:

            print(
                "Більше Twitch стрімів у Slots немає."
            )

            break

        for stream in streams:

            nickname = stream.get(
                "user_login",
                ""
            )

            all_streamers.append({

                "nickname": nickname,

                "normalized_nickname":
                    normalize_nickname(nickname),

                "display_name":
                    stream.get(
                        "user_name",
                        ""
                    ),

                "platform":
                    "Twitch",

                "category":
                    stream.get(
                        "game_name",
                        ""
                    ),

                "game_id":
                    stream.get(
                        "game_id",
                        ""
                    ),

                "language":
                    stream.get(
                        "language",
                        ""
                    ),

                "viewers":
                    stream.get(
                        "viewer_count",
                        0
                    ),

                "title":
                    stream.get(
                        "title",
                        ""
                    ),

                "started_at":
                    stream.get(
                        "started_at",
                        ""
                    ),

                "mature":
                    stream.get(
                        "is_mature",
                        False
                    ),

                "url":
                    f"https://www.twitch.tv/{nickname}",

                "user_id":
                    stream.get(
                        "user_id",
                        ""
                    ),

                "stream_id":
                    stream.get(
                        "id",
                        ""
                    ),

                "first_seen":
                    RUN_TIME,

                "last_seen":
                    RUN_TIME
            })

        print(
            "Зібрано Twitch:",
            len(all_streamers)
        )

        pagination = data.get(
            "pagination",
            {}
        )

        cursor = pagination.get(
            "cursor"
        )

        if not cursor:

            print(
                "Досягнуто кінець Twitch списку."
            )

            break

        time.sleep(0.2)

    df = pd.DataFrame(
        all_streamers
    )

    if not df.empty:

        df = df.drop_duplicates(
            subset=[
                "normalized_nickname"
            ]
        )

    print(
        "Twitch унікальних:",
        len(df)
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

    access_token = get_kick_token()

    headers = {
        "Authorization":
            f"Bearer {access_token}"
    }

    API_URL = (
        "https://api.kick.com/public/v2/livestreams"
    )

    # Kick category: Slots & Casino
    CATEGORY_ID = 28
    LIMIT = 100

    all_streamers = []
    cursor = None
    page = 0

    while len(all_streamers) < MAX_STREAMERS_PER_PLATFORM:

        page += 1

        params = [
            (
                "categoryId",
                str(CATEGORY_ID)
            ),
            (
                "limit",
                str(LIMIT)
            )
        ]

        if cursor:

            params.append(
                (
                    "cursor",
                    cursor
                )
            )

        response = requests.get(
            API_URL,
            headers=headers,
            params=params,
            timeout=30
        )

        print(
            f"Kick сторінка {page} | "
            f"HTTP {response.status_code}"
        )

        if response.status_code != 200:

            print(response.text)

            raise Exception(
                f"Kick API returned HTTP "
                f"{response.status_code}"
            )

        result = response.json()

        streams = result.get(
            "data",
            []
        )

        if not streams:
            break

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

            slug = channel.get(
                "slug",
                ""
            )

            username = user.get(
                "username",
                ""
            )

            # Додатковий захист
            if category.get(
                "name"
            ) != "Slots & Casino":

                continue

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
                    category.get(
                        "name",
                        ""
                    ),

                "game_id":
                    CATEGORY_ID,

                "language":
                    stream.get(
                        "language_code",
                        ""
                    ),

                "viewers":
                    stream.get(
                        "viewer_count",
                        0
                    ),

                "title":
                    stream.get(
                        "title",
                        ""
                    ),

                "started_at":
                    stream.get(
                        "started_at",
                        ""
                    ),

                "mature":
                    "",

                "url":
                    f"https://kick.com/{slug}",

                "user_id":
                    user.get(
                        "id",
                        ""
                    ),

                "stream_id":
                    stream.get(
                        "id",
                        ""
                    ),

                "first_seen":
                    RUN_TIME,

                "last_seen":
                    RUN_TIME
            })

        print(
            "Зібрано Kick:",
            len(all_streamers)
        )

        pagination = (
            result.get(
                "pagination"
            )
            or {}
        )

        cursor = pagination.get(
            "next_cursor"
        )

        if not cursor:
            break

        if (
            len(all_streamers)
            >= MAX_STREAMERS_PER_PLATFORM
        ):
            break

        time.sleep(0.2)

    df = pd.DataFrame(
        all_streamers
    )

    if not df.empty:

        df = df.drop_duplicates(
            subset=[
                "normalized_nickname"
            ]
        )

    print(
        "Kick унікальних:",
        len(df)
    )

    return df


# ==========================================================
# COLLECT BOTH
# ==========================================================

twitch_df = collect_twitch()

kick_df = collect_kick()


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
        "Не знайдено жодного стрімера."
    )

new_scan_df = pd.concat(
    frames,
    ignore_index=True
)

# Захист від дублювання
# Twitch + Twitch або Kick + Kick
new_scan_df = new_scan_df.drop_duplicates(
    subset=[
        "platform",
        "normalized_nickname"
    ]
)

print()
print("==========================================")
print("ПОТОЧНИЙ ЗБІР")
print("==========================================")

print(
    "Twitch:",
    len(twitch_df)
)

print(
    "Kick:",
    len(kick_df)
)

print(
    "Разом:",
    len(new_scan_df)
)


# ==========================================================
# LOAD EXISTING DATABASE
# ==========================================================

if os.path.exists(
    DATABASE_FILE
):

    database_df = pd.read_csv(
        DATABASE_FILE,
        dtype=str
    )

    print()
    print(
        "Існуюча база:",
        len(database_df)
    )

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
# FIRST RUN
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

    # Однаковий порядок колонок

    new_scan_df = new_scan_df[
        database_df.columns
    ]

    # ------------------------------------------------------
    # UNIQUE KEY
    # ------------------------------------------------------

    database_keys = set(

        database_df[
            "platform"
        ].astype(str)

        + "|"

        + database_df[
            "normalized_nickname"
        ].astype(str)

    )

    new_scan_df[
        "unique_key"
    ] = (

        new_scan_df[
            "platform"
        ].astype(str)

        + "|"

        + new_scan_df[
            "normalized_nickname"
        ].astype(str)

    )

    new_streamers = new_scan_df[
        ~new_scan_df[
            "unique_key"
        ].isin(database_keys)
    ].copy()

    new_scan_df = new_scan_df.drop(
        columns=[
            "unique_key"
        ]
    )

    # ------------------------------------------------------
    # UPDATE EXISTING
    # ------------------------------------------------------

    database_df[
        "unique_key"
    ] = (

        database_df[
            "platform"
        ].astype(str)

        + "|"

        + database_df[
            "normalized_nickname"
        ].astype(str)

    )

    current_data = new_scan_df.copy()

    current_data[
        "unique_key"
    ] = (

        current_data[
            "platform"
        ].astype(str)

        + "|"

        + current_data[
            "normalized_nickname"
        ].astype(str)

    )

    # ------------------------------------------------------
    # CURRENT LOOKUP
    # ------------------------------------------------------

    current_lookup = current_data.set_index(
        "unique_key"
    )

    # ------------------------------------------------------
    # UPDATE LAST SEEN + CURRENT DATA
    # ------------------------------------------------------

    for idx in database_df.index:

        key = database_df.at[
            idx,
            "unique_key"
        ]

        if key in current_lookup.index:

            current_row = current_lookup.loc[
                key
            ]

            database_df.at[
                idx,
                "viewers"
            ] = current_row[
                "viewers"
            ]

            database_df.at[
                idx,
                "title"
            ] = current_row[
                "title"
            ]

            database_df.at[
                idx,
                "started_at"
            ] = current_row[
                "started_at"
            ]

            database_df.at[
                idx,
                "last_seen"
            ] = RUN_TIME

            database_df.at[
                idx,
                "language"
            ] = current_row[
                "language"
            ]

            database_df.at[
                idx,
                "url"
            ] = current_row[
                "url"
            ]

    database_df = database_df.drop(
        columns=[
            "unique_key"
        ]
    )

    # ------------------------------------------------------
    # ADD NEW
    # ------------------------------------------------------

    if not new_streamers.empty:

        new_streamers = new_streamers.drop(
            columns=[
                "unique_key"
            ],
            errors="ignore"
        )

        database_df = pd.concat(
            [
                database_df,
                new_streamers
            ],
            ignore_index=True
        )


# ==========================================================
# FINAL CLEANUP
# ==========================================================

database_df = database_df.drop_duplicates(
    subset=[
        "platform",
        "normalized_nickname"
    ],
    keep="first"
)

database_df = database_df.sort_values(
    by=[
        "platform",
        "nickname"
    ],
    ascending=[
        True,
        True
    ]
).reset_index(
    drop=True
)


# ==========================================================
# SAVE DATABASE
# ==========================================================

database_df.to_csv(
    DATABASE_FILE,
    index=False,
    encoding="utf-8-sig"
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
    len(twitch_df)
)

print(
    "Kick у поточному зборі:",
    len(kick_df)
)

print(
    "Всього у базі:",
    len(database_df)
)

print(
    "НОВИХ стрімерів:",
    len(new_streamers)
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

    print(
        new_streamers[
            [
                "nickname",
                "platform",
                "category",
                "language",
                "viewers",
                "url"
            ]
        ].sort_values(
            by="viewers",
            ascending=False
        ).to_string(
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
    database_df.head(30).to_string(
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
