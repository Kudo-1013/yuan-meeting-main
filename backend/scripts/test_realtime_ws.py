"""Legacy realtime test.

The /api/realtime WebSocket API is archived and not part of the current MVP.
Keep this entry point explicit and harmless when someone runs all scripts.
"""


def main() -> None:
    print("SKIP: /api/realtime WebSocket 功能当前未启用（MVP 已归档）。")


if __name__ == "__main__":
    main()
