#!/usr/bin/python3
"""
Test the P1 MQTT export
"""

import pytest

from p1_mqtt.p1.parser import P1Parser

# The test data is a list of tuples, each tuple containing
# a P1 telegram and the expected dictionary of parsed values
TESTDATA = (
    (
        b"""
/Ene5\\XS210 ESMR 5.0

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
    """,
        {
            "p1_actual_power_consuming": 0.335,
            "p1_actual_power_consuming_l1": 0.335,
            "p1_actual_power_producing": 0.0,
            "p1_actual_power_producing_l1": 0.0,
            "p1_current_l1": 1.0,
            "p1_device_type": 3.0,
            "p1_energy_consumed_tariff1": 51.775,
            "p1_energy_consumed_tariff2": 0.0,
            "p1_energy_produced_tariff1": 24.413,
            "p1_energy_produced_tariff2": 0.0,
            "p1_gas_consumed_timestamp": 1509909000,
            "p1_gas_consumed_volume": 16.713,
            "p1_long_power_failure_count": 1.0,
            "p1_power_failure_count": 3.0,
            "p1_timestamp": 1509909204,
            "p1_voltage_l1": 229.0,
            "p1_voltage_sag_l1_count": 2.0,
            "p1_voltage_swell_l1_count": 0.0,
        },
    ),
    (
        b"""
/KFM5KAIFA-METER

1-3:0.2.8(42)
0-0:1.0.0(170124213128W)
0-0:96.1.1(4530303236303030303234343934333135)
1-0:1.8.1(000306.946*kWh)
1-0:1.8.2(000210.088*kWh)
1-0:2.8.1(000000.000*kWh)
1-0:2.8.2(000000.000*kWh)
0-0:96.14.0(0001)
1-0:1.7.0(02.793*kW)
1-0:2.7.0(00.000*kW)
0-0:96.7.21(00001)
0-0:96.7.9(00001)
1-0:99.97.0(1)(0-0:96.7.19)(000101000006W)(2147483647*s)
1-0:32.32.0(00000)
1-0:52.32.0(00000)
1-0:72.32.0(00000)
1-0:32.36.0(00000)
1-0:52.36.0(00000)
1-0:72.36.0(00000)
0-0:96.13.1()
0-0:96.13.0()
1-0:31.7.0(003*A)
1-0:51.7.0(005*A)
1-0:71.7.0(005*A)
1-0:21.7.0(00.503*kW)
1-0:41.7.0(01.100*kW)
1-0:61.7.0(01.190*kW)
1-0:22.7.0(00.000*kW)
1-0:42.7.0(00.000*kW)
1-0:62.7.0(00.000*kW)
0-1:24.1.0(003)
0-1:96.1.0(4730303331303033333738373931363136)
0-1:24.2.1(170124210000W)(00671.790*m3)
!29ED
        """,
        {
            "p1_actual_power_consuming": 2.793,
            "p1_actual_power_consuming_l1": 0.503,
            "p1_actual_power_consuming_l2": 1.1,
            "p1_actual_power_consuming_l3": 1.19,
            "p1_actual_power_producing": 0.0,
            "p1_actual_power_producing_l1": 0.0,
            "p1_actual_power_producing_l2": 0.0,
            "p1_actual_power_producing_l3": 0.0,
            "p1_current_l1": 3.0,
            "p1_current_l2": 5.0,
            "p1_current_l3": 5.0,
            "p1_device_type": 3.0,
            "p1_energy_consumed_tariff1": 306.946,
            "p1_energy_consumed_tariff2": 210.088,
            "p1_energy_produced_tariff1": 0.0,
            "p1_energy_produced_tariff2": 0.0,
            "p1_gas_consumed_timestamp": 1485288000,
            "p1_gas_consumed_volume": 671.79,
            "p1_long_power_failure_count": 1.0,
            "p1_power_failure_count": 1.0,
            "p1_timestamp": 1485289888,
            "p1_voltage_sag_l1_count": 0.0,
            "p1_voltage_sag_l2_count": 0.0,
            "p1_voltage_sag_l3_count": 0.0,
            "p1_voltage_swell_l1_count": 0.0,
            "p1_voltage_swell_l2_count": 0.0,
            "p1_voltage_swell_l3_count": 0.0,
        },
    ),
)


def generate_test_list():
    """
    Generate a list of test from the test data
    """

    for testcase, expected in TESTDATA:
        yield testcase, expected


@pytest.mark.parametrize("testcase,expected", generate_test_list())
def test_p1_mqtt(testcase, expected):
    """
    Test the MQTT export by parsing a telegram and inspecting
    the output
    """
    parser = P1Parser()

    # The test data contains the "wrong" line breaks, \n instead of
    # \r\n, which the checksum calculation expects. Fix this.
    telegram = parser.feed(testcase.replace(b"\n", b"\r\n"))[0]
    assert telegram.to_mqtt() == expected

    # These telegrams should not have a time stamp, as there are two
    # channels in each
    assert telegram.timestamp is None
