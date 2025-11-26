from enum import StrEnum

from tortoise import fields, Model

class Mode(StrEnum):
    KZT = 'kzt'
    SKZ = 'skz'
    VNL = 'vnl'

class User(Model):
    id = fields.IntField(primary_key=True)
    steamid64 = fields.IntField(null=True)
    mode = fields.CharEnumField(Mode, default=Mode.KZT)
