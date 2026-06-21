from __future__ import annotations

import uvicorn

from antenna.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run("antenna.app:create_app", factory=True, host=settings.app.host, port=settings.app.port)


if __name__ == "__main__":
    main()
