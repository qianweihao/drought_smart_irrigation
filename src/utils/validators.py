from marshmallow import Schema, fields, ValidationError
from .logger import logger

class IrrigationRequestSchema(Schema):
    field_id = fields.Str(required=True)
    soil_data = fields.Dict(required=True)
    weather_data = fields.Dict(required=True)

def validate_irrigation_request(data):
    try:
        schema = IrrigationRequestSchema()
        return schema.load(data)
    except ValidationError as e:
        logger.error(f"数据验证失败: {str(e)}")
        raise