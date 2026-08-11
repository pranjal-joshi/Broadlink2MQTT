"""Entry point for the Broadlink2MQTT bridge."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from .bridge import Bridge
from .config import load_config
from .const import NAME, VERSION

_LOGGER = logging.getLogger("broadlink2mqtt")

LOG_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


def _setup_logging(level: str) -> None:
    """Configure logging to stdout, which the Supervisor captures."""
    logging.basicConfig(
        level=LOG_LEVELS.get(level.lower(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("aiomqtt").setLevel(logging.WARNING)


async def _async_main() -> int:
    """Run the bridge until a signal arrives."""
    try:
        config = await load_config()
    except ValueError as err:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout)
        _LOGGER.error("%s", err)
        return 1

    _setup_logging(config.log_level)
    _LOGGER.info("Starting %s %s", NAME, VERSION)

    bridge = Bridge(config)
    try:
        await bridge.async_setup()
    except RuntimeError as err:
        _LOGGER.error("%s", err)
        return 1

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    runner = asyncio.create_task(bridge.async_run(), name="bridge")
    waiter = asyncio.create_task(stop.wait(), name="signal")

    done, pending = await asyncio.wait(
        {runner, waiter}, return_when=asyncio.FIRST_COMPLETED
    )

    await bridge.async_shutdown()

    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    for task in done:
        if task is runner and (err := task.exception()):
            _LOGGER.error("The bridge stopped: %s", err)
            return 1

    return 0


def main() -> int:
    """Run the bridge."""
    try:
        return asyncio.run(_async_main())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
