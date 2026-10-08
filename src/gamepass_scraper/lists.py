"""Known Game Pass lists and their Microsoft SIGL identifiers.

NOTE: these SIGL IDs are community-documented and have NOT been verified against the
live catalog endpoint. If a list comes back empty or wrong, check the ID first.
Extra IDs can be passed at runtime with ``--sigl-id``.
"""

GAME_LISTS: dict[str, str] = {
    "pc": "fdd9e2a7-0fee-49f6-ad69-4354098401ff",
    "console": "f6f1f99f-9b49-4ccd-b3bf-4d9767a77f5e",
    "cloud": "29a81209-df6f-41fd-a528-2ae6b91f719c",
    "ea-play": "b8900d09-a491-44cc-916e-32b5acae621b",
}
