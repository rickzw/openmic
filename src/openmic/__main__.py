"""Entry point for OpenMic app: python -m openmic"""

import logging
import sys


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from openmic.app import OpenMicApp

    app = OpenMicApp()
    app.run()


if __name__ == "__main__":
    main()
