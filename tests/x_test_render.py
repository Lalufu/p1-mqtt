#!/usr/bin/python3
"""
Run config generation test cases

These tests are supposed to succeed
"""

import glob
import json
import os

import pytest

from bgpgen import MODULES, add_arguments, create_config_data, generator
from bgpgen.util.cli import load_yaml, render_jinja2

CONFIG = create_config_data(
    {"counter-start": 20, "counter-inc": 10, "explicit-deny": False,}
)


def generate_test_list():
    """
    Loop through the cross product of loaded modules and
    test cases
    """
    for module in MODULES:
        for entry in glob.glob(os.path.join("test/render/data", "test*yml")):
            if not os.path.isfile(entry):
                continue

            yield (module, entry)


@pytest.mark.parametrize("fmt,testcase", generate_test_list())
def test_render(fmt, testcase):
    """
    Run a test using `testcase` as data and pre-rendered files
    """
    CONFIG.format = fmt
    add_arguments(CONFIG)
    raw_config = load_yaml(testcase)
    try:
        with open(
            os.path.join(
                "test/render/result",
                CONFIG.format,
                os.path.basename(testcase) + ".txt",
            ),
            "r",
            encoding="utf-8",
        ) as handle:
            reference = handle.read()
    except FileNotFoundError:
        # Don't check this combination
        pytest.skip("Test %s not implemented for %s" % (testcase, fmt))

    gen = generator(CONFIG, raw_config)
    cooked_config = gen.generate()
    rendered = render_jinja2(gen.default_template(), cooked_config)
    assert rendered == reference

    # See if we can serialize to JSON. We're just interested
    # in the success, not the actual result
    json.dumps(cooked_config)
