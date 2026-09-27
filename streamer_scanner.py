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
