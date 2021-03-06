#!/usr/bin/env python
# -*- encoding: utf-8 -*-

# Copyright (c) 2002-2020 "Neo4j,"
# Neo4j Sweden AB [http://neo4j.com]
#
# This file is part of Neo4j.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pytest

from neo4j import (
    GraphDatabase,
    BoltDriver,
    Version,
)
from neo4j.exceptions import (
    ServiceUnavailable,
    AuthError,
    ConfigurationError,
    ClientError,
)
from neo4j._exceptions import BoltHandshakeError


# python -m pytest tests/integration/test_bolt_driver.py -s -v

def test_bolt_uri(bolt_uri, auth):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_bolt_uri
    try:
        with GraphDatabase.driver(bolt_uri, auth=auth) as driver:
            with driver.session() as session:
                value = session.run("RETURN 1").single().value()
                assert value == 1
    except ServiceUnavailable as error:
        assert isinstance(error.__cause__, BoltHandshakeError)
        pytest.skip(error.args[0])


# def test_readonly_bolt_uri(readonly_bolt_uri, auth):
#     with GraphDatabase.driver(readonly_bolt_uri, auth=auth) as driver:
#         with driver.session() as session:
#             value = session.run("RETURN 1").single().value()
#             assert value == 1


def test_normal_use_case(bolt_driver):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_normal_use_case
    session = bolt_driver.session()
    value = session.run("RETURN 1").single().value()
    assert value == 1


def test_invalid_url_scheme(service):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_invalid_url_scheme
    address = service.addresses[0]
    uri = "x://{}:{}".format(address[0], address[1])
    try:
        with pytest.raises(ConfigurationError):
            _ = GraphDatabase.driver(uri, auth=service.auth)
    except ServiceUnavailable as error:
        if isinstance(error.__cause__, BoltHandshakeError):
            pytest.skip(error.args[0])


def test_fail_nicely_when_using_http_port(service):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_fail_nicely_when_using_http_port
    from tests.integration.conftest import NEO4J_PORTS
    address = service.addresses[0]
    uri = "bolt://{}:{}".format(address[0], NEO4J_PORTS["http"])
    with pytest.raises(ServiceUnavailable):
        _ = GraphDatabase.driver(uri, auth=service.auth)


def test_custom_resolver(service):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_custom_resolver
    _, port = service.addresses[0]

    def my_resolver(socket_address):
        assert socket_address == ("*", 7687)
        yield "99.99.99.99", port     # should be rejected as unable to connect
        yield "127.0.0.1", port       # should succeed

    try:
        with GraphDatabase.driver("bolt://*", auth=service.auth,
                                  connection_timeout=3,  # enables rapid timeout
                                  resolver=my_resolver) as driver:
            with driver.session() as session:
                summary = session.run("RETURN 1").summary()
                assert summary.server.address == ("127.0.0.1", port)
    except ServiceUnavailable as error:
        if isinstance(error.__cause__, BoltHandshakeError):
            pytest.skip(error.args[0])


def test_encrypted_set_to_false_by_default(bolt_driver):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_encrypted_set_to_false_by_default
    assert bolt_driver.encrypted is False


def test_should_fail_on_incorrect_password(bolt_uri):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_should_fail_on_incorrect_password
    with pytest.raises(AuthError):
        try:
            with GraphDatabase.driver(bolt_uri, auth=("neo4j", "wrong-password")) as driver:
                with driver.session() as session:
                    _ = session.run("RETURN 1")
        except ServiceUnavailable as error:
            if isinstance(error.__cause__, BoltHandshakeError):
                pytest.skip(error.args[0])


def test_supports_multi_db(bolt_uri, auth):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_supports_multi_db
    try:
        driver = GraphDatabase.driver(bolt_uri, auth=auth)
        assert isinstance(driver, BoltDriver)
    except ServiceUnavailable as error:
        if isinstance(error.__cause__, BoltHandshakeError):
            pytest.skip(error.args[0])

    with driver.session() as session:
        result = session.run("RETURN 1")
        value = result.single().value()  # Consumes the result
        summary = result.summary()
        server_info = summary.server

    result = driver.supports_multi_db()
    driver.close()

    if server_info.version_info() >= Version(4, 0, 0) and server_info.protocol_version >= Version(4, 0):
        assert result is True
        assert summary.database == "neo4j"  # This is the default database name if not set explicitly on the Neo4j Server
        assert summary.query_type == "r"
    else:
        assert result is False
        assert summary.database is None
        assert summary.query_type == "r"


def test_test_multi_db_specify_database(bolt_uri, auth):
    # python -m pytest tests/integration/test_bolt_driver.py -s -v -k test_test_multi_db_specify_database
    try:
        with GraphDatabase.driver(bolt_uri, auth=auth, database="test_database") as driver:
            with driver.session() as session:
                result = session.run("RETURN 1")
                assert next(result) == 1
                summary = result.summary()
                assert summary.database == "test_database"
    except ServiceUnavailable as error:
        if isinstance(error.__cause__, BoltHandshakeError):
            pytest.skip(error.args[0])
    except ConfigurationError as error:
        assert "Database name parameter for selecting database is not supported in Bolt Protocol Version(3, 0)" in error.args[0]
    except ClientError as error:
        # FAILURE {'code': 'Neo.ClientError.Database.DatabaseNotFound' - This message is sent from the server
        assert error.args[0] == "Database does not exist. Database name: 'test_database'."
