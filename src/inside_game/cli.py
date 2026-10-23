"""Start the local API; public binding requires explicit bearer-key configuration."""

import argparse
import os


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description="Inside the game analytics API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1") and (
        len(os.getenv("INSIDE_GAME_API_KEY", "")) < 32
        or os.getenv("INSIDE_GAME_LOCAL_ACCESS", "true").lower() != "false"
    ):
        parser.error(
            "Remote binding requires INSIDE_GAME_LOCAL_ACCESS=false and an API key of at least 32 characters."
        )
    uvicorn.run(
        "inside_game.api:app",
        host=args.host,
        port=args.port,
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
