# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import os

import pytest
from juju.controller import Controller
from pytest_operator.plugin import OpsTest

from .helpers import APP_NAME

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, kafka_charm):
    await asyncio.gather(
        ops_test.model.deploy(kafka_charm, application_name=APP_NAME, num_units=1, series="jammy"),
    )
    # Do not wait for idle, otherwise:
    # FAILED: kafka/0 [executing] waiting: waiting for zookeeper relation
    # await ops_test.model.wait_for_idle()

    # Assuming the current controller is the lxd controller.
    lxd_mdl = ops_test.model

    # Assuming a k8s controller is ready and its name is stored in $K8S_CONTROLLER.
    k8s_ctl = Controller()
    await k8s_ctl.connect(os.environ["K8S_CONTROLLER"])
    k8s_mdl_name = "cos"
    k8s_mdl = await k8s_ctl.add_model(k8s_mdl_name)

    await k8s_mdl.deploy("ch:prometheus-k8s", application_name="prometheus", channel="edge")
    await k8s_mdl.create_offer("prometheus:receive-remote-write")

    await lxd_mdl.consume(
        f"admin/{k8s_mdl_name}.prometheus",
        application_alias="prometheus",
        controller_name=k8s_ctl.controller_name,  # same as os.environ["K8S_CONTROLLER"]
    )
    # TODO:
    #  - Enable metallb as part of CI
    #  - Relate prom to traefik

    await asyncio.gather(
        lxd_mdl.deploy(
            "ch:grafana-agent",
            channel="edge",
            application_name="agent",
            num_units=0,
            series="jammy",
        ),
    )
    await lxd_mdl.add_relation("agent", "prometheus")
    await lxd_mdl.add_relation(f"{APP_NAME}:cos-agent", "agent")
    await lxd_mdl.wait_for_idle()

    # TODO: Assert that kafka metrics appear in prometheus
