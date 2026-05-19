import pytest
from pydantic import ValidationError

from specforge.validators import ApiContractModel, RouteContractModel, TaskPacketModel


def test_route_validator_rejects_invalid():
    with pytest.raises(ValidationError):
        RouteContractModel(route="no-slash", source="x")


def test_api_validator_rejects_invalid():
    with pytest.raises(ValidationError):
        ApiContractModel(method="TRACE", endpoint="/wrong", source="x")


def test_task_packet_validator_rejects_invalid():
    with pytest.raises(ValidationError):
        TaskPacketModel(task_id="bad", lane_id="", allowed_files=[], forbidden_files=[], required_gates=[], refs=[])
