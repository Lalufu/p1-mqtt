"""
This file contains the CLI script entry points
"""

import argparse
import codecs
import configparser
import logging
import multiprocessing
import time
from typing import Any, Dict, List

from .mqtt import mqtt_main
from .p1serial import p1serial_main

logging.basicConfig(
    format="%(asctime)-15s %(levelname)s: %(message)s", level=logging.INFO
)
LOGGER = logging.getLogger(__name__)

# Default values for command line args
DEFAULTS: Dict[str, Any] = {
    "mqtt_port": 1883,
    "buffer_size": 100000,
    "mqtt_topic": "p1-mqtt/tele/%(channel)s/%(device_id)s/SENSOR",
    "mqtt_client_id": "p1-mqtt-gateway",
}


def load_config_file(filename: str) -> Dict[str, Any]:
    """
    Load the ini style config file given by `filename`
    """

    config: Dict[str, Any] = {}
    ini = configparser.ConfigParser()
    try:
        with codecs.open(filename, encoding="utf-8") as configfile:
            ini.read_file(configfile)
    except Exception as exc:
        LOGGER.error("Could not read config file %s: %s", filename, exc)
        raise SystemExit(1)

    if ini.has_option("general", "device"):
        config["device"] = ini.get("general", "device")

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
        raise SystemExit(1)

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
        raise SystemExit(1)

    return config


def p1_mqtt() -> None:
    """
    Main function for the p1-mqtt script
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", "-d", type=str, help="Serial device to use")
    parser.add_argument("--config", type=str, help="Configuration file to load")
    parser.add_argument(
        "--mqtt-topic",
        type=str,
        default=None,
        help="MQTT topic to publish to. May contain python format string "
        "references to variables `serial` (containing the serial number "
        "of the device generating the data) and `channel` (containing the "
        "channel of the device generating the data). "
        + ("(Default: %(mqtt_topic)s)" % DEFAULTS).replace("%", "%%"),
    )
    parser.add_argument("--mqtt-host", type=str, help="MQTT server to connect to")
    parser.add_argument(
        "--mqtt-port", type=int, default=None, help="MQTT port to connect to"
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
        "--serial-dump",
        type=str,
        default=None,
        help="File name to dump all data read from the serial device to. "
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

    if args.mqtt_client_id:
        config["mqtt_client_id"] = args.mqtt_client_id
    elif "mqtt_client_id" not in config:
        # Not set through config file, not set through CLI, use default
        config["mqtt_client_id"] = DEFAULTS["mqtt_client_id"]

    if args.buffer_size:
        config["buffer_size"] = args.buffer_size
    elif "buffer_size" not in config:
        # Not set through config file, not set through CLI, use default
        config["buffer_size"] = DEFAULTS["buffer_size"]

    if args.dsmr_22:
        config["dsmr"] = "2.2"
    else:
        config["dsmr"] = "4.0"

    if args.serial_dump:
        config["serial_dump"] = args.serial_dump

    LOGGER.debug("Completed config: %s", config)

    if "device" not in config:
        LOGGER.error("No serial device given")
        raise SystemExit(1)

    if "mqtt_host" not in config:
        LOGGER.error("No MQTT host given")
        raise SystemExit(1)

    p1_mqtt_queue: multiprocessing.Queue = multiprocessing.Queue(
        maxsize=config["buffer_size"]
    )

    procs: List[multiprocessing.Process] = []
    p1_proc = multiprocessing.Process(
        target=p1serial_main, name="p1", args=(p1_mqtt_queue, config)
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
