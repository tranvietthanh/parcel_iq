import decimal
from pydantic import BaseModel

class MyModel(BaseModel):
    val: float

try:
    m = MyModel(val=decimal.Decimal("0.0"))
    print("Success:", m)
except Exception as e:
    print("Error:", repr(e))
