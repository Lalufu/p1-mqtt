"""
This file contains the CLI script entry points
"""

import argparse
import codecs
import configparser
import logging
import multiprocessing
import os
import time
from typing import Any

from .mqtt import mqtt_main
from .p1io import p1io_main

if "INVOCATION_ID" in os.environ:
    # Running under systemd
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
else:
    logging.basicConfig(
        format="%(asctime)-15s %(levelname)s: %(message)s", level=logging.INFO
    )
LOGGER = logging.getLogger(__name__)

# Default values for command line args
DEFAULTS: dict[str, Any] = {
    "mqtt_port": 1883,
    "buffer_size": 100000,
    "mqtt_topic": "p1-mqtt/tele/%(channel)s/%(device_id)s/SENSOR",
    "mqtt_client_id": "p1-mqtt-gateway",
    "mqtt_rate": 0,
}


def load_config_file(filename: str) -> dict[str, Any]:
    """
    Load the ini style config file given by `filename`
    """

    config: dict[str, Any] = {}
    ini = configparser.ConfigParser()
    try:
        with codecs.open(filename, encoding="utf-8") as configfile:
            ini.read_file(configfile)
    except Exception as exc:
        LOGGER.error("Could not read config file %s: %s", filename, exc)
        raise SystemExit(1)  # pylint: disable=raise-missing-from

    if ini.has_option("general", "device"):
        config["device"] = ini.get("general", "device")

    if ini.has_option("general", "host"):
        config["host"] = ini.get("general", "host")

    try:
        if ini.has_option("general", "port"):
            config["port"] = ini.getint("general", "port")
    except ValueError:
        LOGGER.error(
            "%s: %s is not a valid value for port",
            filename,
            ini.get("general", "port"),
        )
        raise SystemExit(1)  # pylint: disable=raise-missing-from

    if ini.has_option("general", "mqtt-host"):
        config["mqtt_host"] = ini.get("general", "mqtt-host")

    try:
        if ini.has_option("general", "mqtt-port"):
            config["mqtt_port"] = ini.getint("general", "mqtt-port")
    except ValueError:
        LOGGER.error(
            "%s: %s is not a valid value for mqtt-port",
            filename,
            ini.get("general", "mqtt-port"),
        )
        raise SystemExit(1)  # pylint: disable=raise-missing-from

    if ini.has_option("general", "mqtt-username"):
        config["mqtt_username"] = ini.get("general", "mqtt-username")

    if ini.has_option("general", "mqtt-password"):
        config["mqtt_password"] = ini.get("general", "mqtt-password")

    if ini.has_option("general", "mqtt-topic"):
        config["mqtt_topic"] = ini.get("general", "mqtt-topic")

    if ini.has_option("general", "mqtt-client-id"):
        config["mqtt_client_id"] = ini.get("general", "mqtt-client-id")

    try:
        if ini.has_option("general", "buffer-size"):
            config["buffer_size"] = ini.getint("general", "buffer-size")
    except ValueError:
        LOGGER.error(
            "%s: %s is not a valid value for buffer-size",
            filename,
            ini.get("general", "buffer-size"),
        )
        raise SystemExit(1)  # pylint: disable=raise-missing-from

    try:
        if ini.has_option("general", "mqtt-rate"):
            config["mqtt_rate"] = ini.getint("general", "mqtt-rate")
    except ValueError:
        LOGGER.error(
            "%s: %s is not a valid value for mqtt-rate",
            filename,
            ini.get("general", "mqtt-rate"),
        )
        raise SystemExit(1)  # pylint: disable=raise-missing-from

    return config


def p1_mqtt() -> None:
    """
    Main function for the p1-mqtt script
    """
    parser = argparse.ArgumentParser()
    parser_input = parser.add_mutually_exclusive_group()
    parser_input.add_argument("--device", "-d", type=str, help="Serial device to use")
    parser_input.add_argument("--host", type=str, help="TCP source host to use")
    parser.add_argument("--port", type=int, help="TCP source port to use")
    parser.add_argument("--config", type=str, help="Configuration file to load")
    parser.add_argument(
        "--mqtt-topic",
        type=str,
        default=None,
        help="MQTT topic to publish to. May contain python format string "
        "references to variables `serial` (containing the serial number "
        "of the device generating the data) and `channel` (containing the "
        "channel of the device generating the data). "
        f"(Default: {DEFAULTS['mqtt_topic'].replace('%','%%')})",
    )
    parser.add_argument("--mqtt-host", type=str, help="MQTT server to connect to")
    parser.add_argument(
        "--mqtt-port", type=int, default=None, help="MQTT port to connect to"
    )
    parser.add_argument(
        "--mqtt-username", type=str, default=None, help="MQTT user name to use"
    )
    parser.add_argument(
        "--mqtt-password", type=str, default=None, help="MQTT password to use"
    )
    parser.add_argument(
        "--mqtt-client-id",
        type=str,
        default=None,
        help="MQTT client ID. Needs to be unique between all clients connecting "
        "to the same broker",
    )
    parser.add_argument(
        "--dsmr-22",
        action="store_true",
        help="Use DSMR 2.2 configuration for the serial port. The default is "
        "to use DSMR 4.0 and newer.",
    )
    parser.add_argument(
        "--source-dump",
        "--serial-dump",
        type=str,
        default=None,
        help="File name to dump all data read from the source to. "
        "This is mainly for debugging purposes.",
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=None,
        help="How many measurements to buffer if the MQTT "
        "server should be unavailable. This buffer is not "
        "persistent across program restarts.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--prefer-local-timestamp",
        action="store_true",
        help="Use the device local time as authoritative in "
        "the MQTT data instead of the timestamp from the P1 "
        "telegram",
    )
    parser.add_argument(
        "--time-ms",
        action="store_true",
        help="Send timestamps to MQTT in milliseconds instead of seconds. "
        "This will only affect p1mqtt* timestamp values",
    )
    parser.add_argument(
        "--mqtt-rate",
        type=int,
        help="Time between messages sent to the broker in seconds.",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.config:
        config = load_config_file(args.config)
    else:
        config = {}

    LOGGER.debug("Config after loading config file: %s", config)

    if args.device:
        config["device"] = args.device

    if args.host:
        config["host"] = args.host

    if args.port:
        config["port"] = args.port

    if args.mqtt_topic:
        config["mqtt_topic"] = args.mqtt_topic
    elif "mqtt_topic" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_topic"] = DEFAULTS["mqtt_topic"]

    if args.mqtt_host:
        config["mqtt_host"] = args.mqtt_host

    if args.mqtt_port:
        config["mqtt_port"] = args.mqtt_port
    elif "mqtt_port" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_port"] = DEFAULTS["mqtt_port"]

    if args.mqtt_username:
        config["mqtt_username"] = args.mqtt_username
    elif "mqtt_username" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_username"] = None

    if args.mqtt_password:
        config["mqtt_password"] = args.mqtt_password
    elif "mqtt_password" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_password"] = None

    if args.mqtt_client_id:
        config["mqtt_client_id"] = args.mqtt_client_id
    elif "mqtt_client_id" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_client_id"] = DEFAULTS["mqtt_client_id"]

    if args.mqtt_rate:
        config["mqtt_rate"] = args.mqtt_rate
    elif "mqtt_rate" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_rate"] = DEFAULTS["mqtt_rate"]
    # mqtt_rate sanity check
    if config["mqtt_rate"] < 0:
        config["mqtt_rate"] = 0

    if args.buffer_size:
        config["buffer_size"] = args.buffer_size
    elif "buffer_size" not in config:
        # Not set through config file, not set through CLI, use default
        config["buffer_size"] = DEFAULTS["buffer_size"]

    if args.dsmr_22:
        config["dsmr"] = "2.2"
    else:
        config["dsmr"] = "4.0"

    if args.source_dump:
        config["source_dump"] = args.source_dump

    config["prefer_local_timestamp"] = args.prefer_local_timestamp

    config["time_ms"] = args.time_ms

    LOGGER.debug("Completed config: %s", config)

    if not ("device" in config or ("host" in config and "port" in config)):
        LOGGER.error("No serial device or no host/port given as data source")
        raise SystemExit(1)

    if "mqtt_host" not in config:
        LOGGER.error("No MQTT host given")
        raise SystemExit(1)

    p1_mqtt_queue: multiprocessing.Queue = multiprocessing.Queue(
        maxsize=config["buffer_size"]
    )

    procs: list[multiprocessing.Process] = []
    p1_proc = multiprocessing.Process(
        target=p1io_main, name="p1", args=(p1_mqtt_queue, config)
    )
    p1_proc.start()
    procs.append(p1_proc)

    mqtt_proc = multiprocessing.Process(
        target=mqtt_main, name="mqtt", args=(p1_mqtt_queue, config)
    )
    mqtt_proc.start()
    procs.append(mqtt_proc)

    # Wait forever for one of the processes to die. If that happens,
    # kill the whole program.
    run = True
    while run:
        try:
            for proc in procs:
                if not proc.is_alive():
                    LOGGER.error("Child process died, terminating program")
                    run = False

            time.sleep(1)
        except KeyboardInterrupt:
            LOGGER.info("Caught keyboard interrupt, exiting")
            run = False

    for proc in procs:
        proc.terminate()
    raise SystemExit(1)
