# P1-MQTT gateway

This is a simple application that reads information from Dutch smart
power meters via the so called P1 port and sends them to an MQTT gateway.
See the website of [Netbeheer Nederland](https://www.netbeheernederland.nl/dossiers/slimme-meter-15/documenten)
for information on the protocol and message format.

Connection is possible either via direct serial connection to the meter,
or via an intermediate device that presents the P1 telegrams via a TCP
connection.

The P1 protocol supports a bus of meters, where measurements from multiple
meters can be deliviered through a single telegram. A common setup is to
report on both electricity and gas consumption.

In case multiple meters deliver data in a single telegram, multiple
separate measurements will be sent to MQTT, one for each meter.

This project uses [pyserial](https://pypi.org/project/pyserial/) to communicate
with the serial port, and [paho-mqtt](https://pypi.org/project/paho-mqtt/)
for talking to MQTT.

## Installation

Installation via pip into a venv is possible with `pip install .` from
the git checkout root, or via `pip install git+https://github.com/Lalufu/p1-mqtt`.
This will also create the executable scripts in the `bin` dir of the venv.

In case you want to do things manually, the main entry point into
the program is `p1_mqtt/cli.py:p1_mqtt()`.

## Development

This project uses [Poetry](https://python-poetry.org/) for dependency
management, and it's probably easiest to use this, Executing `poetry install
` followed by `poetry run p1-mqtt` from the git checkout root should
set up a venv, install the required dependencies into a venv and run
the main program.


## Running

`--config`
: Specify a configuration file to load. See the section `Configuration file`
  for details on the syntax. Command line options given in addition to the
  config file override settings in the config file.

`--host`
: Host name or IP of device connected to the P1 meter

`--port`
: TCP port of device connected to the P1 meter

`--device`
: Device file of the serial port connected to the P1 meter

  Config file: Section `general`, `device`

`--mqtt-host`
: The MQTT host name to connect to. This is a required parameter.

  Config file: Section `general`, `mqtt-host`

`--mqtt-port`
: The MQTT port number to connect to. Defaults to 1883.

  Config file: Section `general`, `mqtt-port`

`--buffer-size`
: The size of the buffer (in number of measurements) that can be locally
  saved when the MQTT server is unavailable. The buffer is not persistent,
  and will be lost when the program exits. Defaults to 100000.

  Config file: Section `general`, `buffer-size`

`--mqtt-topic`
: The MQTT topic to publish the information to. This is a string that is put
  through python formatting, and can contain references to the variables `device_id`
  and `channel`. `device_id` will contain the serial number of the meter, which
  is part of the P1 telegram.
  `channel` will contain the channel assigned to a meter. The main electricity
  meter will use channel 0, while other meters on the bus use channels 1
  and up.
  The default is `p1-mqtt/tele/%(channel)s/%(device_id)s/SENSOR`.

  Config file: Section `general`, `mqtt-topic`

`--mqtt-client-id`
: The client identifier used when connecting to the MQTT gateway. This needs
  to be unique for all clients connecting to the same gateway, only one
  client can be connected with the same name at a time. The default is
  `p1-mqtt-gateway`.

  Config file: Section `general`, `mqtt-client-id`

`--mqtt-rate`
: The time between mqtt messages sent to the broker in seconds.
  The default is `0` (which means as soon as a telegram is ready).

  Config file: Section `general`, `mqtt-rate`

`--dsmr-22`
: Use DSMR 2.2 compatible parameters when setting up the serial port. This
  might be needed for older meters, try this when the default settings do
  not produce any data. The default is to use DSMR 4.0 and later parameters.

`--serial-dump`
: Takes a file name, and will record all data received from the serial
  port into the given file. This is mainly useful to capture data for
  debugging.

  Config file: Section `general`, `serial-dump`

`--prefer-local-timestamp`
: Use the time from the machine running p1-mqtt as the authoritative
  time stamp on the data sent to MQTT, instead of the time stamp contained
  in the telegrams themselves.

`--time-ms`
: Send p1mqtt_\* time stamp values to MQTT in milliseconds instead of
  seconds.

## Configuration file
The program supports a configuration file to define behaviour. The
configuration file is in .ini file syntax, and can contain multiple sections.
The `[general]` section contains settings that define overall program
behaviour.

### Example configuration file

```
[general]
device = /dev/ttyUSB0
mqtt-client-id = p1-gateway-01
mqtt-host = mqtt.example.com
serial-dump = /tmp/dumpfile

```
## Data pushed to MQTT

The script pushes the data received from the P1 meter to MQTT as a JSON
string. Information received from the meter(s) are presented as values
under keys starting with `p1_`.

In addition the following fields are added:

- a `p1mqtt_telegram_timestamp` field is added, containing the time the measurement
  was taken. This information is contained in the P1 telegram, and relies
  on the clock in the meter. Note that not all meters update values at
  the same frequency that telegrams are sent, multiple subsequent telegrams
  might contain the same timestamp and readings.

- a `p1mqtt_collector_timestamp` field is added, containing the time the measurement
  was taken. This information is taken from the clock of the machine
  running p1-mqtt, and might be different from the time in `p1mqtt_telegram_timestamp`.

- a `p1mqtt_timestamp` field is added, containing either of the
  `p1mqtt_telegram_timestamp` and `p1mqtt_collector_timestamp` values.
  The value chosed depends on the `--prefer-local-timestamp` command line
  argument. For easier management this is the value that should be used
  as the authoritative time stamp in further processing of the data.

- a `p1mqtt_device_id` field is added, containing the serial number of the meter
  that this set of measurements belongs to.

- a `p1mqtt_channel` field with added, containing the channel number
  of the meter that this set of measurements belong to.


## Optimized serial reads

To minimize delay in reading and processing data, the script tries to detect
the size of a single telegram sent by the meter, and to read exactly one telegram
at once. If it succeeds in doing so, it considers itself to be 'in sync'.
Changes in telegram size, which should be rare, result in messages to the
console. These are usually harmless, and mainly for informational purposes.
Since the script does not know the telegram size at startup there will be
at least some messages about loss of sync, and resync, during startup. This
is normal.


## Example output

Using the default parameters, the telegram

```
/Ene5\XS210 ESMR 5.0

1-3:0.2.8(50)
0-0:1.0.0(171105201324W)
0-0:96.1.1(4530303437303030303037363330383137)
1-0:1.8.1(000051.775*kWh)
1-0:1.8.2(000000.000*kWh)
1-0:2.8.1(000024.413*kWh)
1-0:2.8.2(000000.000*kWh)
0-0:96.14.0(0001)
1-0:1.7.0(00.335*kW)
1-0:2.7.0(00.000*kW)
0-0:96.7.21(00003)
0-0:96.7.9(00001)
1-0:99.97.0(0)(0-0:96.7.19)
1-0:32.32.0(00002)
1-0:32.36.0(00000)
0-0:96.13.0()
1-0:32.7.0(229.0*V)
1-0:31.7.0(001*A)
1-0:21.7.0(00.335*kW)
1-0:22.7.0(00.000*kW)
0-1:24.1.0(003)
0-1:96.1.0(4730303538353330303031313633323137)
0-1:24.2.1(171105201000W)(00016.713*m3)
!8F46
```

will result in two messages being sent to MQTT.

The first message will be sent to the topic
`p1-mqtt/tele/0/E0047000007630817/SENSOR` and consist of the below
data:

```
{
    "p1mqtt_channel": 0,
    "p1mqtt_device_id": "E0047000007630817",
    "p1mqtt_timestamp": 1509909204,
    "p1_actual_power_consuming": 0.335,
    "p1_actual_power_consuming_l1": 0.335,
    "p1_actual_power_producing": 0.0,
    "p1_actual_power_producing_l1": 0.0,
    "p1_current_l1": 1.0,
    "p1_energy_consumed_tariff1": 51.775,
    "p1_energy_consumed_tariff2": 0.0,
    "p1_energy_produced_tariff1": 24.413,
    "p1_energy_produced_tariff2": 0.0,
    "p1_long_power_failure_count": 1.0,
    "p1_power_failure_count": 3.0,
    "p1_timestamp": 1509909204,
    "p1_voltage_l1": 229.0,
    "p1_voltage_sag_l1_count": 2.0,
    "p1_voltage_swell_l1_count": 0.0
}
```

The second message will be sent to the topic
`p1-mqtt/tele/1/G0058530001163217/SENSOR` and consist of the below
data:

```
{
    "p1mqtt_channel": 1,
    "p1mqtt_device_id": "G0058530001163217",
    "p1mqtt_timestamp": 1509909000,
    "p1_device_type": 3.0,
    "p1_gas_consumed_timestamp": 1509909000,
    "p1_gas_consumed_volume": 16.713
}
```
