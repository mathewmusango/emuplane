"""ECS Container Credentials on the wire: `GET /v2/credentials/<uuid>`.

A container asks this route for its task role's temporary credentials. The
emulator serves the document from the IMDS module and does not validate the
container UUID, so the four required members are asserted rather than a
credential that a running task would have registered.
"""

from __future__ import annotations

import json
import urllib.request

UUID = "01234567-89ab-cdef-0123-456789abcdef"


def test_container_credentials_answers_a_task_role_document(endpoint):
    with urllib.request.urlopen(f"{endpoint}/v2/credentials/{UUID}", timeout=30) as response:
        assert response.status == 200
        document = json.loads(response.read())
    assert document["AccessKeyId"]
    assert document["SecretAccessKey"]
    assert document["Token"]
    assert document["Expiration"]
    assert document["RoleArn"].startswith("arn:aws:iam::")
    assert document["RoleArn"].endswith(":role/ministack-ecs-task-role")
