"""Asset serialization for storage-ready structures."""

from typing import Dict


def serialize_asset(asset_type: str, payload: Dict[str, object]) -> Dict[str, object]:
    return {
        "asset_type": asset_type,
        "payload": payload,
    }
