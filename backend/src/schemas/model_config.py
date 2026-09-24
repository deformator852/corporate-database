from pydantic import ConfigDict

MODEL_CONFIG = ConfigDict(validate_assignment=True)
ORM_MODEL_CONFIG = ConfigDict(from_attributes=True, validate_assignment=True)
UPLOAD_MODEL_CONFIG = ConfigDict(
    arbitrary_types_allowed=True,
    validate_assignment=True,
)
